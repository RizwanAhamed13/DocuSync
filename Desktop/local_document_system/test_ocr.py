import os
import unittest
from PIL import Image, ImageDraw
from parser import extract_text_by_pages

class TestOCRParser(unittest.TestCase):
    
    def setUp(self):
        self.pdf_filename = "temp_synthetic_scanned.pdf"
        
        # 1. Create a synthetic image of text using PIL
        # Tesseract performs best with clear black text on a white background
        img = Image.new('RGB', (800, 200), color='white')
        d = ImageDraw.Draw(img)
        
        # Draw a clear textual phrase using Pillow's default bitmap font
        d.text((50, 80), "Machine Learning Syllabus Course 998", fill='black')
        
        # 2. Save the image directly as a PDF (image-only / scanned PDF representation)
        img.save(self.pdf_filename, "PDF")
        print(f"Generated synthetic scanned PDF: {self.pdf_filename}")

    def tearDown(self):
        if os.path.exists(self.pdf_filename):
            os.remove(self.pdf_filename)
            print(f"Cleaned up {self.pdf_filename}")

    def test_scanned_pdf_ocr_extraction(self):
        """
        Verify that our parser detects the lack of electronic text on the synthetic PDF,
        falls back to page-level OCR rendering, and successfully extracts the text.
        """
        print("Starting parser OCR extraction test...")
        pages_content = extract_text_by_pages(self.pdf_filename)
        
        self.assertEqual(len(pages_content), 1)
        self.assertEqual(pages_content[0]["page"], 1)
        
        extracted_text = pages_content[0]["text"].lower()
        print(f"OCR Extracted Text:\n{extracted_text}\n")
        
        # Assert that key terms drawn in the image are found in the OCR-extracted text
        self.assertIn("machine", extracted_text)
        self.assertIn("learning", extracted_text)
        self.assertIn("syllabus", extracted_text)
        self.assertIn("998", extracted_text)
        print("Success! Tesseract OCR successfully extracted the text from the scanned PDF image.")

if __name__ == "__main__":
    unittest.main()
