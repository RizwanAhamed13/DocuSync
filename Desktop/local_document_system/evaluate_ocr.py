import os
import time
import difflib
import fitz  # PyMuPDF
from parser import ocr_pdf_page

TEST_FILES = [
    "1. Syllabus 2023.pdf",
    "2023_Chem122_syllabus.pdf",
    "101-f22-syll.pdf"
]

DATASET_DIR = "./dataset"

def calculate_word_jaccard(original: str, ocr: str) -> float:
    orig_words = set(original.lower().split())
    ocr_words = set(ocr.lower().split())
    if not orig_words and not ocr_words:
        return 1.0
    if not orig_words or not ocr_words:
        return 0.0
    return len(orig_words & ocr_words) / len(orig_words | ocr_words)

def calculate_char_similarity(original: str, ocr: str) -> float:
    # Limit character lengths to prevent SequenceMatcher from taking too long on huge texts
    limit = 5000
    orig_trunc = original[:limit]
    ocr_trunc = ocr[:limit]
    return difflib.SequenceMatcher(None, orig_trunc, ocr_trunc).ratio()

def evaluate():
    print("=" * 60)
    print("DocuSync OCR Pipeline Accuracy & Speed Evaluation")
    print("=" * 60)
    
    results = []
    
    for filename in TEST_FILES:
        filepath = os.path.join(DATASET_DIR, filename)
        if not os.path.exists(filepath):
            print(f"Skipping {filename}: File not found in dataset folder.")
            continue
            
        print(f"\nEvaluating: {filename}...")
        try:
            doc = fitz.open(filepath)
            total_pages = len(doc)
            print(f"Total Pages to process: {total_pages}")
            
            orig_text_all = ""
            ocr_text_all = ""
            
            start_time = time.time()
            
            for page_idx, page in enumerate(doc):
                # 1. Extract ground truth electronic text
                orig_page_text = page.get_text("text").strip()
                orig_text_all += "\n" + orig_page_text
                
                # 2. Render page and run OCR (simulating scanned page)
                page_start = time.time()
                ocr_page_text = ocr_pdf_page(page, dpi=150)
                ocr_text_all += "\n" + ocr_page_text
                
                page_duration = time.time() - page_start
                print(f"  Page {page_idx + 1}/{total_pages} processed in {page_duration:.2f}s")
                
            total_duration = time.time() - start_time
            avg_page_time = total_duration / total_pages
            
            # Compute accuracy metrics
            char_sim = calculate_char_similarity(orig_text_all, ocr_text_all)
            word_sim = calculate_word_jaccard(orig_text_all, ocr_text_all)
            
            results.append({
                "filename": filename,
                "pages": total_pages,
                "duration_sec": total_duration,
                "avg_page_time": avg_page_time,
                "char_similarity": char_sim,
                "word_jaccard": word_sim
            })
            
            print(f"Evaluation complete for {filename}:")
            print(f"  Total Time: {total_duration:.2f}s | Avg Page Time: {avg_page_time:.2f}s")
            print(f"  Character-Level Similarity: {char_sim * 100:.1f}%")
            print(f"  Word-Level Jaccard Index: {word_sim * 100:.1f}%")
            
        except Exception as e:
            print(f"Failed to evaluate {filename}: {e}")
            
    # Print consolidated summary table
    print("\n" + "=" * 60)
    print("OCR Pipeline Evaluation Summary")
    print("=" * 60)
    print(f"{'Filename':<30} | {'Pages':<5} | {'Avg Sec/Page':<12} | {'Char Sim':<8} | {'Word Jaccard':<12}")
    print("-" * 75)
    for r in results:
        print(f"{r['filename'][:30]:<30} | {r['pages']:<5} | {r['avg_page_time']:<12.2f} | {r['char_similarity']*100:<7.1f}% | {r['word_jaccard']*100:<11.1f}%")
    print("=" * 75)

if __name__ == "__main__":
    evaluate()
