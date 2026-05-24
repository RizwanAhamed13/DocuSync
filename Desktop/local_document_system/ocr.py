import io
import numpy as np
from PIL import Image

# ── PaddleOCR v3 (preferred) → Tesseract (fallback) ───────────────────────────
# PaddleOCR v3 broke the v2 API:
#   - __init__: no lang/use_gpu/show_log kwargs
#   - input:    numpy.ndarray or file path — NOT raw bytes
#   - output:   result[0].rec_texts  (list of text lines)
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    _ocr_engine = _PaddleOCR()          # uses PP-OCRv5_server by default
    _using_paddle = True
except Exception as _import_err:
    print(f"PaddleOCR import failed ({_import_err}); falling back to Tesseract.")
    _using_paddle = False
    import pytesseract


def _bytes_to_numpy(image_bytes: bytes) -> np.ndarray:
    """Convert raw image bytes → RGB numpy array for PaddleOCR."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def ocr_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes.

    Returns extracted text (empty string on failure).
    Primary: PaddleOCR v3 (PP-OCRv5_server).
    Fallback: Tesseract 5.
    """
    if _using_paddle:
        try:
            img_np = _bytes_to_numpy(image_bytes)
            results = _ocr_engine.predict(img_np)
            if results:
                # rec_texts is a flat list of recognised line strings
                lines = results[0].rec_texts or []
                return "\n".join(lines).strip()
            return ""
        except Exception as e:
            print(f"PaddleOCR image OCR error: {e}")
            return ""
    else:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img).strip()
        except Exception as e:
            print(f"Tesseract fallback OCR error: {e}")
            return ""


def ocr_pdf_page(page, dpi: int = 150) -> str:
    """Render a PDF page to a PNG and run OCR via the active engine."""
    try:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        return ocr_image_bytes(img_bytes)
    except Exception as e:
        print(f"Error rendering PDF page for OCR: {e}")
        return ""
