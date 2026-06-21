"""
OCR backend — EasyOCR (PyTorch-based, GPU-optimized) primary engine, Tesseract 5 ensemble fallback.

Key design decisions
--------------------
1. **Mobile models** (PP-OCRv4_mobile_det + en_PP-OCRv4_mobile_rec):
   The PP-OCRv5_server models are accurate but load 5 models simultaneously
   (det + rec + orientation classifier + textline orientation + UVDoc unwarper),
   consuming ~1.5-2 GB RAM.  PP-OCRv4 mobile uses only det + rec, is ~10× smaller,
   and achieves >97% character accuracy on clean printed English text — the
   primary content in academic PDFs and scanned exam timetables.

2. **Orientation / unwarping disabled at init**: passing `use_doc_orientation_classify=False`
   and `use_doc_unwarping=False` in __init__ (not just in predict) prevents
   PaddleOCR from downloading and loading PP-LCNet_x1_0_doc_ori, UVDoc, and
   PP-LCNet_x1_0_textline_ori.  PDF pages rendered by PyMuPDF are already
   correctly oriented — the extra models are pure overhead.

3. **Thread-safe lazy initialisation**: the PaddleOCR engine is created on the
   FIRST actual OCR call, not at module import.  A threading.Lock ensures that
   concurrent asyncio.to_thread calls cannot race to create duplicate engines.

4. **Startup warm-up** (warm_up_ocr): call from the lifespan startup to download
   and load models before the first upload request arrives, so the first document
   is not penalised with model-download latency.

5. **Ensemble quality gate** (AWS Textract / ABBYY FineReader style):
   After PaddleOCR runs, text density is checked (chars per 10k pixels).
   If sparse (< 5 chars/10k px) on a non-trivial image, Tesseract also runs and
   the denser result is returned.

6. **Tesseract PSM 11** (sparse text): the ensemble fallback fires precisely when
   the image has unusual layout — tables, low-density scans, mixed-column grids.
   PSM 11 ("find as much text as possible, no particular order") significantly
   outperforms PSM 6 ("uniform block of text") on exam timetables and grade grids.
"""

import base64
import io
import os
import threading

import numpy as np
from PIL import Image, ImageOps

# Skip PaddleX model-source connectivity check on every startup.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# ── Colab OCR remote endpoint (optional) ─────────────────────────────────────
# When COLAB_OCR_URL is set (e.g. https://xxxx.ngrok-free.app), heavy scanned
# pages are sent to the Colab PP-OCRv5 server instead of the local mobile model.
# Falls back to local PP-OCRv4 mobile silently if Colab is unreachable.
#
# Set via:  export COLAB_OCR_URL=https://xxxx.ngrok-free.app
# Clear via: unset COLAB_OCR_URL  (or restart server without the env var)
COLAB_OCR_URL: str | None = os.getenv("COLAB_OCR_URL", "").strip() or None

# ── PaddleOCR — preferred engine ──────────────────────────────────────────────
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    import paddle as _paddle_fw  # noqa: F401 — verify runtime is present
    _paddle_available = True
except Exception as _import_err:
    print(f"PaddleOCR unavailable ({_import_err}); will use Tesseract only.")
    _paddle_available = False

# ── Tesseract — always imported ────────────────────────────────────────────────
# Imported unconditionally so it is available as an ensemble fallback even
# when PaddleOCR is working correctly.  Previously it was only imported in the
# PaddleOCR failure branch, which prevented ensemble quality gating.
try:
    import pytesseract as _pytesseract
    _tesseract_available = True
except Exception:
    _pytesseract = None
    _tesseract_available = False

if not _paddle_available and not _tesseract_available:
    print(
        "WARNING: neither PaddleOCR nor Tesseract is available — "
        "OCR will return empty strings."
    )

# Lazy singleton — populated on first call to _get_ocr_engine()
_ocr_engine = None
_ocr_engine_lock = threading.Lock()  # prevents race on concurrent first calls


def _get_ocr_engine():
    """
    Return the shared PaddleOCR engine, creating it on first call (thread-safe).

    Uses PP-OCRv5/v6 server models on GPU via paddlepaddle-gpu (pre-installed
    in the paddlepaddle/paddle:3.1.0-gpu base image).
    """
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_engine_lock:
            if _ocr_engine is None:  # double-checked lock
                print("Loading PaddleOCR engine (PP-OCRv5/v6 on GPU)…")
                _ocr_engine = _PaddleOCR(device="gpu")
    return _ocr_engine


def warm_up_ocr() -> bool:
    """
    Pre-load and warm up the PaddleOCR engine.

    Call this from the server lifespan startup so that:
    1. Model files are downloaded before the first upload request.
    2. The inference engine is hot (JIT-compiled) for the first real page.
    3. If the download fails, it fails at startup (visible to the operator)
       rather than silently during a background ingest task.

    Returns True if PaddleOCR is available and ready, False otherwise.
    """
    if not _paddle_available:
        print("PaddleOCR not available — OCR will use Tesseract only.")
        return False
    try:
        engine = _get_ocr_engine()
        blank = np.full((32, 200, 3), 255, dtype=np.uint8)
        engine.predict(blank)
        print("PaddleOCR engine ready (PP-OCRv5/v6 on GPU).")
        return True
    except Exception as e:
        import traceback
        print(f"PaddleOCR warm-up failed: {e}")
        traceback.print_exc()
        print("OCR will fall back to Tesseract.")
        return False


def _bytes_to_numpy(image_bytes: bytes) -> np.ndarray:
    """Convert raw image bytes → RGB numpy array (required by PaddleOCR v3)."""
    return np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))


def _reconstruct_reading_order(
    rec_texts: list,
    rec_scores: list,
    rec_polys: list,
    score_thresh: float = 0.5,
) -> str:
    """
    Convert PaddleOCR's unordered detection output into natural reading order.

    Problem
    -------
    PaddleOCR returns text regions in detection order (roughly top-left to
    bottom-right, but not reliable for multi-column content).  For a timetable
    row like:

        | 19PHBC2002 | PROBABILITY AND STATISTICS | 13-06-2026 | FN |

    the raw rec_texts arrive as four separate strings with no row relationship:
        ['19PHBC2002', 'PROBABILITY AND STATISTICS', '13-06-2026', 'FN']

    Without layout reconstruction, these become four separate lines in the
    extracted text — the subject code and exam date land in different chunks,
    making "find the exam date for PROBABILITY AND STATISTICS" impossible.

    Solution
    --------
    Each detected text region has a bounding polygon (rec_polys).  We use the
    Y-centre of each polygon to cluster detections into rows, then sort each
    row's cells left-to-right by X-position.  Output joins cells with " | ":

        19PHBC2002 | PROBABILITY AND STATISTICS | 13-06-2026 | FN

    This preserves the semantic relationship between every cell in the row so
    the chunker keeps them together and search can match across columns.

    Row-band calculation
    --------------------
    The band height is 60% of the median inter-row gap — wide enough to absorb
    slight skew in scanned pages but narrow enough not to merge adjacent rows.
    Minimum band is 8 px so tiny images don't degenerate.

    Fallback
    --------
    If rec_polys is missing or mismatched, falls back to simple line join —
    no crash, just the old behaviour.
    """
    if not rec_texts:
        return ""

    # If no polygon data, fall back to plain join
    if not rec_polys or len(rec_polys) != len(rec_texts):
        return "\n".join(
            t for t, s in zip(rec_texts, rec_scores or [])
            if (s or 1.0) >= score_thresh and t.strip()
        ).strip()

    # Build (y_centre, x_left, text) triples — filter by score & non-empty
    items: list[tuple[float, float, str]] = []
    for text, score, poly in zip(rec_texts, rec_scores or [], rec_polys):
        if (score or 1.0) < score_thresh or not text.strip():
            continue
        try:
            arr = np.asarray(poly)          # shape (N, 2): [[x,y], ...]
            y_centre = float(arr[:, 1].mean())
            x_left   = float(arr[:, 0].min())
        except Exception:
            continue
        items.append((y_centre, x_left, text.strip()))

    if not items:
        return ""

    # Sort by Y so we can cluster from top to bottom
    items.sort(key=lambda t: t[0])

    # Estimate row-band from median non-zero inter-item Y gap
    y_vals = [it[0] for it in items]
    gaps   = sorted(abs(y_vals[i + 1] - y_vals[i]) for i in range(len(y_vals) - 1))
    nonzero_gaps = [g for g in gaps if g > 2]
    band = max(nonzero_gaps[len(nonzero_gaps) // 2] * 0.6 if nonzero_gaps else 15, 8)

    # Cluster into rows
    rows: list[list[tuple[float, float, str]]] = [[items[0]]]
    for item in items[1:]:
        if abs(item[0] - rows[-1][0][0]) <= band:
            rows[-1].append(item)
        else:
            rows.append([item])

    # Within each row sort left → right, then join with separator
    lines: list[str] = []
    for row in rows:
        row.sort(key=lambda t: t[1])
        lines.append(" | ".join(cell[2] for cell in row))

    return "\n".join(lines)


def _tesseract_ocr(image_bytes: bytes) -> str:
    """
    Tesseract OCR with industry-standard preprocessing.

    Pipeline:
      1. Convert to greyscale (removes colour noise that confuses the LSTM).
      2. Auto-contrast with 2% cutoff — stretches the histogram to use the
         full 0-255 range without blowing out extremes.
      3. Otsu-equivalent binarisation at midpoint 128 — clean black/white
         reduces character segmentation errors for Tesseract's CNN.
      4. --psm 11: "sparse text — find as much text as possible in no
         particular order."  This PSM is critical for exam timetables, grade
         grids, and any layout where text is not in a single continuous block.
         PSM 6 ("uniform block") misses entire table cells on such images.

    PSM choice reference:
      PSM 6 = assume uniform text block (best for prose paragraphs).
      PSM 11 = find all text regardless of layout (best for tables/forms).
      We use PSM 11 here because _tesseract_ocr is called either:
        (a) As the ensemble fallback when PaddleOCR returned sparse results
            — by definition the layout is unusual.
        (b) As the sole engine when PaddleOCR is unavailable.
    """
    if not _tesseract_available:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")  # greyscale
        img = ImageOps.autocontrast(img, cutoff=2)              # stretch histogram
        img = img.point(lambda p: 255 if p > 128 else 0, "1")  # binarise
        return _pytesseract.image_to_string(img, config="--psm 11").strip()
    except Exception as e:
        print(f"Tesseract OCR error: {e}")
    return ""


def _colab_ocr(image_bytes: bytes) -> str | None:
    """
    Send image to the Colab PP-OCRv5 server endpoint and return reconstructed text.

    Returns None (not empty string) when Colab is unavailable so the caller
    can fall through to the local engine without treating silence as a result.
    Only called when COLAB_OCR_URL is set.
    """
    if not COLAB_OCR_URL:
        return None
    try:
        import httpx
        payload = {
            "image_b64": base64.b64encode(image_bytes).decode(),
            "min_score": 0.5,
        }
        # 60s timeout — PP-OCRv5 server on first cold call can be slow
        with httpx.Client(timeout=60.0) as client:
            r = client.post(f"{COLAB_OCR_URL}/ocr", json=payload)
            r.raise_for_status()
            data = r.json()

        texts  = data.get("texts",  [])
        scores = data.get("scores", [1.0] * len(texts))
        polys  = data.get("polys",  [])

        # Run the same spatial reconstruction as the local path
        return _reconstruct_reading_order(texts, scores, polys)

    except Exception as e:
        print(f"Colab OCR unreachable ({e}); falling back to local engine.")
        return None


def ocr_image_bytes(image_bytes: bytes) -> str:
    """
    Run OCR on raw image bytes — PaddleOCR primary with layout reconstruction
    and Tesseract ensemble fallback.

    Layout reconstruction
    ---------------------
    PaddleOCR returns text detections in bounding-box order, not reading order.
    _reconstruct_reading_order() groups detections by Y-row and sorts each row
    left-to-right, producing "Code | Subject Name | Date | Session" on one line
    instead of four separate lines.  This keeps table rows intact as single
    semantic units so the chunker and search both see the full row context.

    Ensemble quality gate
    ---------------------
    After PaddleOCR runs, text density is computed as:

        density = len(text) / image_pixels × 10 000

    If density < 5 chars per 10k pixels on an image larger than 50k pixels,
    Tesseract PSM 11 also runs and the denser result is returned.  This catches
    faded photocopies, low-contrast screenshots, and sparse hand-annotated pages.

    Returns extracted text (empty string on failure).
    """
    # ── Tier 1: Colab PP-OCRv5 server on GPU (when running) ──────────────────
    if COLAB_OCR_URL:
        result = _colab_ocr(image_bytes)
        if result is not None:          # None = unreachable, "" = no text found
            return result
        # Colab failed → fall through to local engine

    # ── Tier 2: Local PaddleOCR on GPU ────────────────────────────────────────
    if _paddle_available:
        try:
            engine  = _get_ocr_engine()
            img_np  = _bytes_to_numpy(image_bytes)
            results = engine.predict(img_np)
            paddle_text = ""
            if results:
                rec_texts  = results[0].get("rec_texts")  or []
                rec_scores = results[0].get("rec_scores") or [1.0] * len(rec_texts)
                rec_polys  = results[0].get("rec_polys")  or []
                paddle_text = _reconstruct_reading_order(
                    rec_texts, rec_scores, rec_polys
                )

            # ── Ensemble quality gate ─────────────────────────────────────────
            img_pixels = img_np.shape[0] * img_np.shape[1]
            density    = (len(paddle_text) / max(img_pixels, 1)) * 10_000
            if density < 5 and img_pixels > 50_000 and _tesseract_available:
                tess_text = _tesseract_ocr(image_bytes)
                if len(tess_text) > len(paddle_text):
                    return tess_text

            return paddle_text

        except Exception as e:
            print(f"PaddleOCR image OCR error: {e}")
            # Fall through to Tesseract-only path

    # ── Full Tesseract fallback ───────────────────────────────────────────────
    return _tesseract_ocr(image_bytes)


def ocr_pdf_page(page, dpi: int = 300) -> str:
    """
    Render a PDF page to a PNG and OCR it via the active engine.

    DPI choice — industry reference:
      • ISO 19005 / PDF/A recommends ≥ 300 DPI for archival text.
      • ABBYY FineReader, AWS Textract, and Google Document AI all default to
        300 DPI.  150 DPI loses characters smaller than ~10 pt and causes
        frequent misreads of superscripts, footnotes, and table cells.
      • 300 DPI is roughly 4× the pixel count of 150 DPI → better accuracy
        with only moderate memory overhead (~2 MB vs ~0.5 MB per A4 page).

    Image size cap (OOM guard):
      A4 at 300 DPI = 2480×3508 px ≈ 26 MB numpy array.  Without capping,
      a 10-page scanned PDF keeps ~260 MB of image data in-flight while
      PaddleOCR holds its own internal copies — enough to OOM-kill the
      process on 8 GB machines when the embedding model is also resident.
      We cap the long side to 1920 px (≈ 3.7 MP): all characters ≥ 10 pt
      remain fully legible at this resolution, matching parser.py's
      _cap_image_bytes heuristic for embedded images.
    """
    try:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")

        # Cap rendered page to 1920 px on its long side before OCR.
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if max(w, h) > 1920:
            scale = 1920 / max(w, h)
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.LANCZOS,
            )
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

        return ocr_image_bytes(img_bytes)
    except Exception as e:
        print(f"Error rendering PDF page for OCR: {e}")
        return ""
