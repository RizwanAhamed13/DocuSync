"""
OCR backend — PP-OCRv5 server models on local GPU (primary), Tesseract 5 fallback.

GPU server version: uses paddlepaddle-gpu so PaddleOCR automatically runs on CUDA.
PP-OCRv5 server models (det + rec) achieve ~0.3 s/page on a 16 GB GPU vs
4-8 s/page for PP-OCRv4 mobile on CPU.
"""

import io
import logging
import os
import threading

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# OCR runs on CPU by default — it is a background batch task (fires only during
# document upload, never during search queries) so GPU is not needed for it.
# Keeping OCR on CPU frees the ~1 GB + activation headroom that would otherwise
# push peak VRAM over 16 GB when embedding + Ollama layers are also resident.
# Override with OCR_DEVICE=gpu if you have a second GPU or more VRAM to spare.
_OCR_DEVICE = os.getenv("OCR_DEVICE", "cpu")

try:
    from paddleocr import PaddleOCR as _PaddleOCR
    import paddle as _paddle_fw  # noqa: F401
    _paddle_available = True
except Exception as _import_err:
    logger.warning(f"PaddleOCR unavailable ({_import_err}); will use Tesseract only.")
    _paddle_available = False

try:
    import pytesseract as _pytesseract
    _tesseract_available = True
except Exception:
    _pytesseract = None
    _tesseract_available = False

if not _paddle_available and not _tesseract_available:
    logger.error(
        "Neither PaddleOCR nor Tesseract is available — OCR will return empty strings."
    )

_ocr_engine = None
_ocr_engine_lock = threading.Lock()


def _get_ocr_engine():
    """Return the shared PP-OCRv5 server engine on GPU (thread-safe lazy init)."""
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_engine_lock:
            if _ocr_engine is None:
                logger.info(f"Loading PaddleOCR PP-OCRv5 server engine on {_OCR_DEVICE}…")
                _ocr_engine = _PaddleOCR(
                    ocr_version="PP-OCRv5",
                    lang="en",
                    device=_OCR_DEVICE,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
    return _ocr_engine


def warm_up_ocr() -> bool:
    """Pre-load and warm up the PP-OCRv5 server engine at startup."""
    if not _paddle_available:
        logger.warning("PaddleOCR not available — OCR will use Tesseract only.")
        return False
    try:
        engine = _get_ocr_engine()
        blank = np.full((32, 200, 3), 255, dtype=np.uint8)
        engine.predict(
            blank,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )
        logger.info("PaddleOCR engine ready (PP-OCRv5 server, GPU).")
        return True
    except Exception as e:
        logger.warning(f"PaddleOCR warm-up failed ({e}); OCR will fall back to Tesseract.")
        return False


def _bytes_to_numpy(image_bytes: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))


def _reconstruct_reading_order(
    rec_texts: list,
    rec_scores: list,
    rec_polys: list,
    score_thresh: float = 0.5,
) -> str:
    """Group detections into rows by Y-centre and sort left-to-right within each row."""
    if not rec_texts:
        return ""

    if not rec_polys or len(rec_polys) != len(rec_texts):
        return "\n".join(
            t for t, s in zip(rec_texts, rec_scores or [])
            if (s or 1.0) >= score_thresh and t.strip()
        ).strip()

    items: list[tuple[float, float, str]] = []
    for text, score, poly in zip(rec_texts, rec_scores or [], rec_polys):
        if (score or 1.0) < score_thresh or not text.strip():
            continue
        try:
            arr = np.asarray(poly)
            y_centre = float(arr[:, 1].mean())
            x_left   = float(arr[:, 0].min())
        except Exception:
            continue
        items.append((y_centre, x_left, text.strip()))

    if not items:
        return ""

    items.sort(key=lambda t: t[0])

    y_vals = [it[0] for it in items]
    gaps   = sorted(abs(y_vals[i + 1] - y_vals[i]) for i in range(len(y_vals) - 1))
    nonzero_gaps = [g for g in gaps if g > 2]
    band = max(nonzero_gaps[len(nonzero_gaps) // 2] * 0.6 if nonzero_gaps else 15, 8)

    rows: list[list[tuple[float, float, str]]] = [[items[0]]]
    for item in items[1:]:
        if abs(item[0] - rows[-1][0][0]) <= band:
            rows[-1].append(item)
        else:
            rows.append([item])

    lines: list[str] = []
    for row in rows:
        row.sort(key=lambda t: t[1])
        lines.append(" | ".join(cell[2] for cell in row))

    return "\n".join(lines)


def _tesseract_ocr(image_bytes: bytes) -> str:
    if not _tesseract_available:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        img = ImageOps.autocontrast(img, cutoff=2)
        img = img.point(lambda p: 255 if p > 128 else 0, "1")
        return _pytesseract.image_to_string(img, config="--psm 11").strip()
    except Exception as e:
        logger.warning(f"Tesseract OCR error: {e}")
    return ""


def ocr_image_bytes(image_bytes: bytes) -> str:
    """
    Run OCR on raw image bytes — PP-OCRv5 server on GPU (primary), Tesseract fallback.
    """
    # ── Primary: PP-OCRv5 server on GPU ──────────────────────────────────────
    if _paddle_available:
        try:
            engine  = _get_ocr_engine()
            img_np  = _bytes_to_numpy(image_bytes)
            results = engine.predict(
                img_np,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            paddle_text = ""
            if results:
                rec_texts  = results[0].get("rec_texts")  or []
                rec_scores = results[0].get("rec_scores") or [1.0] * len(rec_texts)
                rec_polys  = results[0].get("rec_polys")  or []
                paddle_text = _reconstruct_reading_order(rec_texts, rec_scores, rec_polys)

            # Ensemble quality gate: if PaddleOCR result is sparse, try Tesseract
            img_pixels = img_np.shape[0] * img_np.shape[1]
            density    = (len(paddle_text) / max(img_pixels, 1)) * 10_000
            if density < 5 and img_pixels > 50_000 and _tesseract_available:
                tess_text = _tesseract_ocr(image_bytes)
                if len(tess_text) > len(paddle_text):
                    return tess_text

            return paddle_text

        except Exception as e:
            logger.warning(f"PaddleOCR image OCR error: {e}")

    # ── Fallback: Tesseract ───────────────────────────────────────────────────
    return _tesseract_ocr(image_bytes)


def ocr_pdf_page(page, dpi: int = 300) -> str:
    """Render a PDF page to PNG and OCR it via the active engine."""
    try:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")

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
        logger.error(f"Error rendering PDF page for OCR: {e}")
        return ""
