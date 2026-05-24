"""
OCR backend — PaddleOCR v3 (PP-OCRv5_server) preferred, Tesseract fallback.

Key design decisions
--------------------
1. **Lazy initialisation**: the PaddleOCR engine is created on the FIRST
   actual OCR call, not at module import.  This keeps import time < 1 ms
   regardless of which backend is installed.

2. **Preprocessing disabled**: PDF pages rendered at 150 DPI are clean,
   upright images — doc-orientation classification and geometric unwarping
   are unnecessary overhead.  Skipping them removes two of the five models
   that PaddleOCR v3 would otherwise load.

3. **v3 API**: PaddleOCR 3.x broke v2 completely —
   - __init__: no lang / use_gpu / show_log kwargs
   - input:    numpy.ndarray or file path (NOT raw bytes)
   - output:   result[0].rec_texts  (list of str, one per text line)
"""

import io
import numpy as np
from PIL import Image

# Check availability at import (fast — no model loading)
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    _paddle_available = True
except Exception as _import_err:
    print(f"PaddleOCR import failed ({_import_err}); falling back to Tesseract.")
    _paddle_available = False
    try:
        import pytesseract as _pytesseract
    except Exception:
        _pytesseract = None  # both unavailable — ocr_image_bytes returns ""

# Lazy singleton — populated on first call to _get_ocr_engine()
_ocr_engine = None


def _get_ocr_engine():
    """Return the shared PaddleOCR engine, creating it on first call."""
    global _ocr_engine
    if _ocr_engine is None:
        # doc_orientation_classify and doc_unwarping not needed for PDF pages
        _ocr_engine = _PaddleOCR(
            doc_orientation_classify_model_name=None,
            doc_unwarping_model_name=None,
        )
    return _ocr_engine


def _bytes_to_numpy(image_bytes: bytes) -> np.ndarray:
    """Convert raw image bytes → RGB numpy array (required by PaddleOCR v3)."""
    return np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))


def ocr_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes.

    Returns extracted text (empty string on failure).
    Primary: PaddleOCR v3 (PP-OCRv5_server, lazy-loaded on first call).
    Fallback: Tesseract 5.
    """
    if _paddle_available:
        try:
            engine = _get_ocr_engine()
            img_np = _bytes_to_numpy(image_bytes)
            results = engine.predict(
                img_np,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            if results:
                lines = results[0].get("rec_texts") or []
                return "\n".join(lines).strip()
            return ""
        except Exception as e:
            print(f"PaddleOCR image OCR error: {e}")
            return ""

    # ── Tesseract fallback ────────────────────────────────────────────────────
    if _pytesseract is not None:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return _pytesseract.image_to_string(img).strip()
        except Exception as e:
            print(f"Tesseract fallback OCR error: {e}")
    return ""


def ocr_pdf_page(page, dpi: int = 150) -> str:
    """Render a PDF page to a PNG and OCR it via the active engine."""
    try:
        pix = page.get_pixmap(dpi=dpi)
        return ocr_image_bytes(pix.tobytes("png"))
    except Exception as e:
        print(f"Error rendering PDF page for OCR: {e}")
        return ""
