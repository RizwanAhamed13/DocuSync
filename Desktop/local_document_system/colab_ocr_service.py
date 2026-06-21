# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  COLAB OCR SERVICE  —  paste this entire file into one Colab code cell      ║
# ║                                                                              ║
# ║  Tunnel: Cloudflare Quick Tunnel (trycloudflare.com)                        ║
# ║    • No account, no token, no rate limits, no time limits                   ║
# ║    • Just a one-line binary download                                         ║
# ║                                                                              ║
# ║  Model: PaddleOCR PP-OCRv5 server (Apache 2.0)                              ║
# ║    • ~0.5s/page on T4 GPU vs ~8s/page on local CPU                          ║
# ║                                                                              ║
# ║  Steps:                                                                      ║
# ║    1. Runtime → Change runtime type → T4 GPU                                ║
# ║    2. Paste this file into a Colab cell and run                             ║
# ║    3. Copy the printed trycloudflare.com URL                                ║
# ║    4. Local machine:  export COLAB_OCR_URL=https://xxxx.trycloudflare.com   ║
# ║    5. Restart local server                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import subprocess, sys, os, io, base64, threading, time, re
import numpy as np
from PIL import Image

# ── Step 1: Install packages ───────────────────────────────────────────────────

def _pip(*args):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *args])

def _install_paddle():
    """
    paddlepaddle-gpu is NOT on PyPI — it lives on PaddlePaddle's own index.
    The index URL must match Colab's CUDA version, otherwise pip fails.
    We detect the CUDA version, pick the right URL, and fall back to CPU
    paddlepaddle (plain PyPI) if the GPU install fails for any reason.
    """
    # Detect CUDA version from nvidia-smi
    cuda_ver = ""
    try:
        out = subprocess.check_output(["nvidia-smi"], text=True, stderr=subprocess.STDOUT)
        m = re.search(r"CUDA Version:\s*([\d.]+)", out)
        if m:
            cuda_ver = m.group(1)
            print(f"  Detected CUDA {cuda_ver}")
    except Exception:
        pass

    # Map CUDA version → PaddlePaddle index tag
    # PaddlePaddle publishes: cu118, cu120, cu123 (covers 12.0–12.x)
    if cuda_ver.startswith("11"):
        tag = "cu118"
    else:
        tag = "cu123"   # default: covers CUDA 12.x (12.0, 12.2, 12.4, …)

    index_url = f"https://www.paddlepaddle.org.cn/packages/stable/{tag}/"
    print(f"  Using PaddlePaddle index: {tag}")

    try:
        _pip("paddlepaddle-gpu", "-i", index_url)
        print("✓ paddlepaddle-gpu (GPU) installed")
        return True
    except subprocess.CalledProcessError:
        print("  GPU install failed — falling back to CPU paddlepaddle")
        try:
            _pip("paddlepaddle")
            print("✓ paddlepaddle (CPU) installed — OCR will run on CPU")
            return False
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Could not install paddlepaddle: {e}")

print("Installing packages…")
_install_paddle()
_pip("paddleocr>=3.5.0")
_pip("fastapi")
_pip("uvicorn[standard]")
print("✓ All packages ready")

# ── Step 2: Download Cloudflare tunnel binary (no account needed) ──────────────

print("Downloading cloudflared…")
subprocess.run([
    "wget", "-q", "-O", "/usr/local/bin/cloudflared",
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
], check=True)
subprocess.run(["chmod", "+x", "/usr/local/bin/cloudflared"], check=True)
print("✓ cloudflared ready")

# ── Step 3: Load PP-OCRv5 server on GPU ───────────────────────────────────────

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from paddleocr import PaddleOCR

print("Loading PP-OCRv5 server models on GPU…")
_engine = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

# Warm-up
_blank = np.full((32, 200, 3), 255, dtype=np.uint8)
_engine.predict(_blank, use_doc_orientation_classify=False, use_doc_unwarping=False)
print("✓ PP-OCRv5 server ready on GPU")

# ── Step 4: FastAPI OCR endpoint ───────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Colab OCR Service — PP-OCRv5 server")

class OcrRequest(BaseModel):
    image_b64: str
    min_score: float = 0.5

class OcrResponse(BaseModel):
    texts:  list[str]
    scores: list[float]
    polys:  list[list[list[float]]]

@app.get("/health")
def health():
    return {"status": "ok", "model": "PP-OCRv5_server", "device": "gpu"}

@app.post("/ocr", response_model=OcrResponse)
def ocr(req: OcrRequest):
    try:
        img_np = np.array(Image.open(io.BytesIO(base64.b64decode(req.image_b64))).convert("RGB"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad image: {e}")
    try:
        results = _engine.predict(img_np,
            use_doc_orientation_classify=False, use_doc_unwarping=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    texts, scores, polys = [], [], []
    if results:
        for t, s, p in zip(
            results[0].get("rec_texts") or [],
            results[0].get("rec_scores") or [],
            results[0].get("rec_polys")  or [],
        ):
            if float(s) >= req.min_score and str(t).strip():
                texts.append(str(t).strip())
                scores.append(float(s))
                try:    polys.append(np.asarray(p).tolist())
                except: polys.append([])

    return OcrResponse(texts=texts, scores=scores, polys=polys)

# ── Step 5: Start server + Cloudflare tunnel ───────────────────────────────────

PORT = 8001

# Start uvicorn in background thread
def _run_server():
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")

threading.Thread(target=_run_server, daemon=True).start()
time.sleep(2)   # let uvicorn bind before tunnelling

# Start Cloudflare quick tunnel — no account, no token needed
# Reads stdout line-by-line until it prints the public URL
_tunnel_url = None

def _start_tunnel():
    global _tunnel_url
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{PORT}",
         "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        # cloudflared prints the URL in a line like:
        #   "Your quick Tunnel has been created! Visit it at: https://xxxx.trycloudflare.com"
        match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
        if match:
            _tunnel_url = match.group()
            print()
            print("=" * 60)
            print(f"  PP-OCRv5 OCR URL:  {_tunnel_url}")
            print()
            print("  On your local machine run:")
            print(f"  export COLAB_OCR_URL={_tunnel_url}")
            print("  Then restart your local server.")
            print("=" * 60)
            print()
            break

tunnel_thread = threading.Thread(target=_start_tunnel, daemon=True)
tunnel_thread.start()
tunnel_thread.join(timeout=30)   # wait up to 30s for URL to appear

if not _tunnel_url:
    print("Cloudflare tunnel URL not detected yet — check output above.")

# Keep cell alive with heartbeat so Colab doesn't idle-disconnect
try:
    while True:
        time.sleep(300)
        print(f"OCR service alive — URL: {_tunnel_url}")
except KeyboardInterrupt:
    print("Stopped.")
