import os
import re
from app.ai.ingest import SUPPORTED_EXTENSIONS

def extract_all_code(extracted_path: str) -> str:
    """
    Walk the extracted project directory.
    Collect all source file contents (same SUPPORTED_EXTENSIONS as ingest.py).
    Normalize: lowercase, remove comments (simple regex for // and #),
    strip blank lines, strip string literals (replace with "STR").
    Return concatenated normalized text.
    """
    all_texts = []
    abs_extracted_path = os.path.abspath(extracted_path)
    if not os.path.exists(abs_extracted_path):
        return ""
        
    for root, _, filenames in os.walk(abs_extracted_path):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Normalize text:
                # 1. Lowercase
                text = content.lower()
                
                # 2. Remove comments
                # Multi-line /* ... */
                text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
                # Multi-line """ ... """ or ''' ... '''
                text = re.sub(r'""".*?"""', '', text, flags=re.DOTALL)
                text = re.sub(r"'''.*?'''", '', text, flags=re.DOTALL)
                # Single-line // ... or # ...
                text = re.sub(r'//.*', '', text)
                text = re.sub(r'#.*', '', text)
                
                # 3. Replace string literals with "STR"
                text = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', 'STR', text)
                text = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", 'STR', text)
                
                # 4. Strip blank lines and whitespace
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                all_texts.append("\n".join(lines))
            except Exception:
                pass
    return "\n".join(all_texts)

def compute_similarity_matrix(
    submissions: list[dict]
) -> dict[str, dict[str, float]]:
    """
    submissions: list of { submission_id, extracted_path }
    1. For each: extract_all_code → normalized text
    2. Fit TfidfVectorizer on all texts
    3. Compute cosine similarity matrix (sklearn cosine_similarity)
    4. Return nested dict:
       { submission_id: { other_submission_id: float } }
       Only include pairs where similarity > 0.3 (ignore unrelated).
       Do NOT include self-similarity.
    """
    if not submissions:
        return {}
        
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    texts = []
    ids = []
    for sub in submissions:
        code_str = extract_all_code(sub["extracted_path"])
        texts.append(code_str)
        ids.append(sub["submission_id"])
        
    # Check if there's any non-empty code
    if not any(texts):
        return {id_: {} for id_ in ids}
        
    vectorizer = TfidfVectorizer()
    try:
        tfidf = vectorizer.fit_transform(texts)
        sim_matrix = cosine_similarity(tfidf, tfidf)
    except Exception:
        return {id_: {} for id_ in ids}
        
    nested_res = {}
    for i, id_a in enumerate(ids):
        nested_res[id_a] = {}
        for j, id_b in enumerate(ids):
            if i == j:
                continue
            score = float(sim_matrix[i, j])
            if score > 0.3:
                nested_res[id_a][id_b] = score
                
    return nested_res

def flag_plagiarism(similarity_matrix: dict,
                    threshold: float = 0.75) -> list[dict]:
    """
    Find all pairs where similarity >= threshold.
    Return list of:
    { submission_a, submission_b, similarity, flag: "HIGH"|"MEDIUM" }
    HIGH if similarity >= 0.90
    MEDIUM if 0.75 <= similarity < 0.90
    Sort by similarity descending.
    """
    flags = []
    seen_pairs = set()
    for id_a, matches in similarity_matrix.items():
        for id_b, score in matches.items():
            if score >= threshold:
                pair = tuple(sorted([id_a, id_b]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    flag_val = "HIGH" if score >= 0.90 else "MEDIUM"
                    flags.append({
                        "submission_a": id_a,
                        "submission_b": id_b,
                        "similarity": score,
                        "flag": flag_val
                    })
    flags.sort(key=lambda x: x["similarity"], reverse=True)
    return flags
