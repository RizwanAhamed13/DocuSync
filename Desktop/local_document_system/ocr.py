import os
from typing import Optional

# Try to import PaddleOCR; if unavailable, fall back to Tesseract
try:
    from paddleocr import PaddleOCR
    # Initialize PaddleOCR engine (English model, CPU mode). Adjust parameters as needed.
    _ocr_engine = PaddleOCR(lang='en', use_gpu=False, show_log=False)
    _using_paddle = True
except Exception as import_err:
    print(f"PaddleOCR import failed ({import_err}); falling back to Tesseract.")
    _using_paddle = False
    import pytesseract
    from PIL import Image
    import io

def ocr_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes.

    Returns the extracted text (empty string on failure).
    Uses PaddleOCR if available, otherwise Tesseract.
    """
    if _using_paddle:
        try:
            # PaddleOCR expects image bytes; it returns a list of results per page.
            result = _ocr_engine.ocr(image_bytes, cls=False)
            # result[0] is a list of lines; each line: [bbox, (text, confidence)]
            if result and isinstance(result, list) and len(result) > 0:
                lines = result[0]
                text = "\n".join(line[1][0] for line in lines if line and isinstance(line, list) and len(line) > 1)
                return text.strip()
            return ""
        except Exception as e:
            print(f"PaddleOCR image OCR error: {e}")
            return ""
    else:
        # Tesseract fallback – retain original behaviour
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img).strip()
        except Exception as e:
            print(f"Tesseract fallback OCR error: {e}")
            return ""

def ocr_pdf_page(page, dpi: int = 150) -> str:
    """Render a PDF page to an image (PNG) and run OCR.

    Utilises the same OCR backend as `ocr_image_bytes`.
    """
    try:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        return ocr_image_bytes(img_bytes)
    except Exception as e:
        print(f"Error rendering PDF page for OCR: {e}")
        return ""
