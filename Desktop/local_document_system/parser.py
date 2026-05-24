import os

import docx
import fitz  # PyMuPDF

from ocr import ocr_image_bytes, ocr_pdf_page


def _extract_page_text_reading_order(page) -> str:
    """
    Extract text from a PDF page in natural reading order.

    PyMuPDF's default get_text("text") reads strictly top-to-bottom which
    mangles two-column academic papers.  By sorting text blocks into horizontal
    bands (sized to ~75% of the average line height) and then left-to-right
    within each band, we recover correct column order for single, double, and
    triple-column layouts without needing explicit column detection.
    """
    blocks = page.get_text("blocks")
    if not blocks:
        return ""

    # Keep only text blocks (type 0); skip image placeholders (type 1)
    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
    if not text_blocks:
        return ""

    heights = [max(1.0, b[3] - b[1]) for b in text_blocks]
    avg_height = sum(heights) / len(heights)
    band_size = max(5.0, avg_height * 0.75)

    # Primary sort: vertical band; secondary: x-position (left → right)
    text_blocks.sort(key=lambda b: (int(b[1] / band_size), b[0]))
    return "\n".join(b[4].strip() for b in text_blocks)


def _iter_docx_blocks(document):
    """
    Yield text strings for paragraphs AND table rows in document-body order.

    python-docx's document.paragraphs skips every table cell, losing grade
    scales, schedules, and policy grids common in syllabi.  Walking the XML
    body directly preserves the interleaved order of prose and tables.
    """
    for child in document.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            from docx.text.paragraph import Paragraph

            text = Paragraph(child, document).text.strip()
            if text:
                yield text

        elif tag == "tbl":
            from docx.table import Table

            table = Table(child, document)
            for row in table.rows:
                seen: set[str] = set()
                cells: list[str] = []
                for cell in row.cells:
                    ct = cell.text.strip()
                    # DOCX merged cells appear multiple times — deduplicate
                    if ct and ct not in seen:
                        cells.append(ct)
                        seen.add(ct)
                if cells:
                    yield " | ".join(cells)


def extract_text_by_pages(file_path: str) -> list[dict]:
    """
    Extracts text from PDF, DOCX, or plain-text files, structured by page/section.
    Returns: [{"page": int, "text": str}]
    """
    _, ext = os.path.splitext(file_path.lower())
    pages_content = []

    if ext == ".pdf":
        try:
            doc = fitz.open(file_path)

            # Detect password-protected PDFs before iterating pages
            if doc.is_encrypted:
                if not doc.authenticate(""):
                    raise ValueError(
                        "PDF is password-protected. "
                        "Please provide an unprotected copy."
                    )

            for page_idx in range(doc.page_count):
                page_num = page_idx + 1

                # Per-page error handling — a single corrupt page should not
                # abort the entire document
                try:
                    page = doc.load_page(page_idx)
                except Exception as load_err:
                    print(f"Skipping page {page_num} (failed to load: {load_err})")
                    continue

                text = _extract_page_text_reading_order(page)

                ocr_texts: list[str] = []
                image_list = page.get_images(full=True)

                if image_list:
                    print(
                        f"Page {page_num}: {len(image_list)} embedded image(s) found, running OCR…"
                    )
                    for img_idx, img in enumerate(image_list):
                        try:
                            xref = img[0]
                            base_image = doc.extract_image(xref)

                            # Skip small decorative images (logos, rules, icons)
                            if (
                                base_image.get("width", 0) < 100
                                or base_image.get("height", 0) < 100
                            ):
                                continue

                            img_text = ocr_image_bytes(base_image["image"])
                            if img_text:
                                ocr_texts.append(
                                    f"\n[Image {img_idx + 1} OCR:\n{img_text}\n]"
                                )
                        except Exception as img_err:
                            print(
                                f"OCR failed for image {img_idx} on page {page_num}: {img_err}"
                            )

                # Fallback: no selectable text → OCR the whole rendered page
                if not text:
                    print(
                        f"Page {page_num}: no selectable text, running page-level OCR…"
                    )
                    try:
                        text = ocr_pdf_page(page)
                    except Exception as ocr_err:
                        print(f"Page-level OCR failed on page {page_num}: {ocr_err}")

                if ocr_texts:
                    text += "\n" + "\n".join(ocr_texts)

                if text.strip():
                    pages_content.append({"page": page_num, "text": text.strip()})

        except ValueError:
            raise  # Re-raise password/format errors with their original message
        except Exception as exc:
            print(f"Error parsing PDF {file_path}: {exc}")
            raise

    elif ext == ".docx":
        try:
            document = docx.Document(file_path)
            current_page = 1
            word_count = 0
            page_text: list[str] = []
            TARGET_WORDS_PER_PAGE = 300

            for text in _iter_docx_blocks(document):
                page_text.append(text)
                word_count += len(text.split())

                if word_count >= TARGET_WORDS_PER_PAGE:
                    pages_content.append(
                        {"page": current_page, "text": "\n".join(page_text)}
                    )
                    page_text = []
                    word_count = 0
                    current_page += 1

            if page_text:
                pages_content.append(
                    {"page": current_page, "text": "\n".join(page_text)}
                )
        except Exception as exc:
            print(f"Error parsing DOCX {file_path}: {exc}")
            raise

    elif ext in [".txt", ".md", ".json", ".csv"]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()
            char_limit = 2000
            for page_idx, start in enumerate(range(0, len(text), char_limit)):
                chunk = text[start : start + char_limit].strip()
                if chunk:
                    pages_content.append({"page": page_idx + 1, "text": chunk})
        except Exception as exc:
            print(f"Error parsing text file {file_path}: {exc}")
            raise
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    return pages_content
