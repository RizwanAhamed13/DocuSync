from __future__ import annotations
import asyncio
import json
import os
import re
import sqlite3

def _get_system_setting(key: str, default_val=None):
    from core.db import get_db_connection
    import json
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
        if row:
            return json.loads(row["value"])
        return default_val
    except Exception:
        return default_val
    finally:
        conn.close()

import threading
import time

from core.db import get_db_connection
from core.config import (
    CLASSIFIER_MODEL_NAME,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SUMMARIZER_MODEL_NAME,
    USE_OLLAMA_TAGGING,
)
from services.embeddings import EMBEDDING_MODEL_NAME, _best_device, get_chroma_collection, get_embedding_model

# ── Abstractive summarization ─────────────────────────────────────────────────
import threading as _threading

_BART_MODEL      = None
_BART_LOCK       = _threading.Lock()
_DEBERTA_LOCK    = _threading.Lock()

def get_bart_model():
    """Lazy-load the configured summarization model — thread-safe."""
    global _BART_MODEL
    if _BART_MODEL is not None:
        return _BART_MODEL if _BART_MODEL is not False else None
    with _BART_LOCK:
        if _BART_MODEL is not None:          # double-checked locking
            return _BART_MODEL if _BART_MODEL is not False else None
        try:
            from transformers import pipeline
            device = _best_device()
            _BART_MODEL = pipeline(
                "summarization",
                model=SUMMARIZER_MODEL_NAME,
                device=device,
            )
            print(f"Summarizer loaded ({SUMMARIZER_MODEL_NAME}) on {device.upper()}.")
        except Exception as e:
            print(f"Summarizer load failed: {e} — using lead-3 fallback.")
            _BART_MODEL = False
    return _BART_MODEL if _BART_MODEL is not False else None


# ── Zero-shot classification ──────────────────────────────────────────────────
_DEBERTA_MODEL = None

def get_deberta_classifier():
    """Lazy-load DeBERTa zero-shot classifier — thread-safe."""
    global _DEBERTA_MODEL
    if _DEBERTA_MODEL is not None:
        return _DEBERTA_MODEL if _DEBERTA_MODEL is not False else None
    with _DEBERTA_LOCK:
        if _DEBERTA_MODEL is not None:       # double-checked locking
            return _DEBERTA_MODEL if _DEBERTA_MODEL is not False else None
        try:
            from transformers import pipeline
            device = _best_device()
            _DEBERTA_MODEL = pipeline(
                "zero-shot-classification",
                model=CLASSIFIER_MODEL_NAME,
                device=device,
            )
            print(f"Classifier loaded ({CLASSIFIER_MODEL_NAME}) on {device.upper()}.")
        except Exception as e:
            print(f"DeBERTa load failed: {e} — falling back to embedding-based classification.")
            _DEBERTA_MODEL = False
    return _DEBERTA_MODEL if _DEBERTA_MODEL is not False else None

_DEFAULT_METADATA = {
    "summary": "",
    "tags": ["Academic Document"],
    "key_findings": [],
    "entities": {"Companies": [], "Dates": [], "Project_Names": []},
}

# ── Junk tags that provide zero value ────────────────────────────────────────


# ── Words to skip during TF keyword extraction ───────────────────────────────


# ── Course-code prefix → academic subject ────────────────────────────────────


# ── Subject labels — specific academic/scientific topics ──────────────────────
# Used by DeBERTa zero-shot classification (primary) and BGE cosine (fallback).
# Labels must be SHORT (1-3 words) so they appear cleanly in the UI as
# classification items. No "and", no conjunctions — each label is unique.


# ── Field labels — broad domain (derived from subject) ────────────────────────


# ── Methodology labels ─────────────────────────────────────────────────────────


# Keyword patterns for fast rule-based methodology detection (high recall fallback)






def _extract_overview_sentence(text: str) -> str | None:
    """
    Pull the first useful sentence from a Course Overview / Description section.
    Returns None if nothing found.
    """
    clean = re.sub(r"<[^>]+>", " ", text or "")
    # Find section header
    section = re.search(
        r"(?:course\s+(?:overview|description|summary|introduction)|about\s+this\s+course)"
        r"[:\s\n]+(.{40,350}?)(?:\n\n|\.\s+[A-Z]|goals|objectives|topics|materials|\Z)",
        clean[:3000], re.IGNORECASE | re.DOTALL,
    )
    if section:
        snippet = re.sub(r"\s+", " ", section.group(1)).strip()
        # Take first sentence only
        sentence = re.split(r"(?<=[.!?])\s+(?=[A-Z])", snippet)[0]
        if 20 < len(sentence) < 200:
            return sentence.rstrip(".")
    return None


def _extract_content_keywords(text: str, n: int = 3) -> list[str]:

    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    english_stopwords = frozenset(ENGLISH_STOP_WORDS)

    body = re.sub(r"<[^>]+>", " ", text or "")[:4000]
    body_lower = body.lower()

    collected: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        key = phrase.lower().strip()
        if (key not in seen
                and len(key) >= 4
                and not re.match(r"^\d", key)):
            seen.add(key)
            collected.append(phrase.strip().title())

    # ── 1. YAKE — multi-word statistical keyphrases ───────────────────────────
    try:
        import yake
        _kw = yake.KeywordExtractor(
            lan="en",
            n=2,           # max 2-word phrases (bigrams keep tags readable)
            dedupLim=0.7,  # 70% Levenshtein similarity → deduplicate variants
            top=n * 3,     # extract extra, we'll filter
            features=None,
        )
        for phrase, _score in _kw.extract_keywords(body):
            # Filter generic domain noise
            if not any(skip in phrase.lower() for skip in english_stopwords):
                _add(phrase)
    except Exception as _yake_err:
        pass  # YAKE unavailable or failed — continue to next method

    # ── 2. mini-KeyBERT — semantic candidate scoring ──────────────────────────
    # Only run if YAKE produced fewer than n results (saves compute when YAKE
    # already found good keyphrases, since both share the same output goal).
    if len(collected) < n:
        try:
            from services.embeddings import get_embedding_model
            import numpy as np

            model = get_embedding_model()

            # Candidate generation: unigrams (5+ chars) + bigrams
            words = re.findall(r"\b[A-Za-z][a-z]{3,}\b", body)
            unigrams = [w for w in set(words) if w.lower() not in english_stopwords]
            bigrams = [
                f"{words[i]} {words[i + 1]}"
                for i in range(len(words) - 1)
                if words[i].lower() not in english_stopwords
                and words[i + 1].lower() not in english_stopwords
            ]
            candidates = list(dict.fromkeys(unigrams + bigrams))[:150]  # dedup, cap

            if candidates:
                # Embed document summary (first 400 chars) — fast, captures topic
                doc_emb = model.encode(
                    body[:400], normalize_embeddings=True, show_progress_bar=False
                )
                cand_embs = model.encode(
                    candidates, normalize_embeddings=True,
                    batch_size=64, show_progress_bar=False
                )
                scores = (cand_embs @ doc_emb).tolist()

                for phrase, score in sorted(
                    zip(candidates, scores), key=lambda x: -x[1]
                ):
                    if score > 0.45 and len(collected) < n * 2:
                        _add(phrase)
        except Exception as _kb_err:
            pass  # embedding model unavailable — continue to TF-IDF

    # ── 3. TF-IDF (sklearn) — IDF-weighted unigrams ───────────────────────────
    # Only run if we still need more keywords
    if len(collected) < n:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import numpy as np

            vect = TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=50,
                stop_words="english",
                sublinear_tf=True,   # log(1+tf) — dampens very common terms
                min_df=1,
            )
            X = vect.fit_transform([body_lower])
            names = vect.get_feature_names_out()
            scores = X.toarray()[0]
            for term, score in sorted(zip(names, scores), key=lambda x: -x[1]):
                if score > 0 and len(collected) < n * 2:
                    _add(term)
        except Exception as _tfidf_err:
            pass

    # ── 4. Raw TF fallback (original method) ─────────────────────────────────
    if len(collected) < n:
        words = re.findall(r"\b[a-z]{5,}\b", body_lower)
        filtered = [w for w in words if w not in english_stopwords]
        counter = Counter(filtered)
        for w, c in counter.most_common(30):
            if c >= 2 and len(collected) < n * 2:
                _add(w)

    return collected[:n]


def _lead_based_summary(text: str, max_words: int = 20) -> str:
    """
    Extract first N words from text as summary (Lead-3 strategy).
    Speed: <1ms. Accuracy: ~80% as good as LLM for academic/news text.
    Best for: Academic papers, news, technical docs where first sentences are key.
    """
    sentences = re.split(r'[.!?]+', text.strip())
    summary_parts = []
    word_count = 0
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 5 or sent.lower().startswith(('abstract:', 'summary:', 'contents:')):
            continue
        words = sent.split()
        if word_count + len(words) <= max_words:
            summary_parts.append(sent)
            word_count += len(words)
        else:
            break
    result = '. '.join(summary_parts).strip()
    return (result + '.') if result else text[:100]


def _rule_based_summary(filename: str, text: str) -> str:
    """Domain-agnostic fallback summary taking the first few meaningful sentences."""
    import re
    snippet = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', snippet) if len(s.strip()) > 15]
    if sentences:
        return " ".join(sentences[:3])
    return snippet[:300] + "..." if len(snippet) > 300 else snippet


def _is_syllabus(filename: str, text: str) -> bool:
    combined = (filename + " " + (text or "")[:300]).lower()
    return "syllabus" in combined or "course overview" in combined or "course description" in combined


def _rule_based_tags(filename: str, text: str) -> list[str]:
    """Generic rule-based tag fallback using top keywords."""
    tags = _extract_content_keywords(text, n=3)
    if "syllabus" in filename.lower() or "syllabus" in text[:500].lower():
        tags.append("Syllabus")
    return list(set(tags))


def _clean_llm_tags(raw_tags: list, filename: str, text: str) -> list[str]:
    """
    Sanitise LLM-produced tags:
    - Remove generic/useless tags
    - Strip whitespace / capitalise properly
    - If fewer than 2 real tags remain, supplement with rule-based ones
    """
    cleaned: list[str] = []
    for t in (raw_tags or []):
        tag = str(t).strip()
        if not tag or tag.lower() in _GENERIC_TAGS:
            continue
        cleaned.append(tag)

    if len(cleaned) < 2:
        # LLM produced garbage — use rule-based tags instead
        return _rule_based_tags(filename, text)

    # Supplement with rule-based tags if we got too few
    if len(cleaned) < 3:
        for rb_tag in _rule_based_tags(filename, text):
            if rb_tag not in cleaned:
                cleaned.append(rb_tag)
            if len(cleaned) >= 5:
                break

    return cleaned[:6]


def _is_tabular_text(text: str) -> bool:
    """
    Detect whether page text is structured table rows rather than prose.

    A sentence-boundary chunker is wrong for table data — table rows have no
    `.!?` endings, so the entire page becomes one "sentence" that then gets
    character-split mid-row, destroying column alignment.

    Criteria (ALL must hold):
      1. At least 6 non-blank lines  (fewer = not enough signal)
      2. Average line length < 100 chars  (table rows are shorter than paragraphs)
      3. Fewer than 15% of lines end with sentence-terminating punctuation
      4. At least 30% of lines start with a SHORT token  (sem numbers, subject
         codes, dates, batch years — anything 1–8 chars before a space)

    Real-world cases where this fires:
      • Exam timetables  (Sem | Batch | Code | Subject | Date | Session)
      • Grade scales     (A: 93-100 | B: 83-92 | …)
      • Weekly schedules (Week 1 | Topic | Reading | Due)
      • Course rosters   (Student ID | Name | Section | Grade)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 6:
        return False
    avg_len = sum(len(l) for l in lines) / len(lines)
    if avg_len >= 100:
        return False
    sentence_ends = sum(1 for l in lines if re.search(r"[.!?]\s*$", l))
    if sentence_ends / len(lines) >= 0.15:
        return False
    short_start = sum(1 for l in lines if re.match(r"^[A-Z0-9]{1,8}\b", l))
    return (short_start / len(lines)) >= 0.30


def chunk_document(
    pages_content: list[dict],
    chunk_size: int = 900,
    overlap_sentences: int = 2,
) -> list[dict]:
    """
    Sentence-boundary-aware chunking with sentence-level sliding overlap.

    Industry standard (LangChain RecursiveCharacterTextSplitter behaviour):
      • Split at natural sentence boundaries instead of arbitrary character
        positions — preserves semantic coherence so the embedding model
        receives complete thoughts rather than truncated fragments.
      • Overlap is measured in sentences (not bytes) so the last N sentences
        of each chunk always appear at the start of the next chunk, giving
        the retrieval model full context without double-counting large spans.
      • Paragraph breaks (\\n\\n) are treated as hard sentence boundaries so
        section headers and bullet lists are never merged mid-paragraph.

    Fallback for super-long sentences (e.g. a PDF table extracted as one line):
      Character-level split at chunk_size so the chunk cap is never exceeded.
    """
    # Regex: split at sentence-ending punctuation followed by whitespace+capital,
    # OR at two-or-more consecutive newlines (paragraph / section break).
    _SENT_RE = re.compile(
        r"(?<=[.!?])\s+(?=[A-Z\"\'])"   # "sentence. Next sentence"
        r"|\n{2,}",                       # paragraph break
        re.MULTILINE,
    )

    chunks: list[dict] = []

    for page in pages_content:
        raw_text = page["text"]
        page_num  = page["page"]

        # ── Table-row chunking path ───────────────────────────────────────────
        # Exam timetables, grade scales, schedule grids — any page whose text
        # is clearly structured rows rather than prose — are chunked by grouping
        # N lines together instead of splitting at sentence boundaries.
        # This preserves each row as a coherent semantic unit (all columns of
        # one exam entry stay in the same chunk) rather than cutting mid-row.
        if _is_tabular_text(raw_text):
            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            ROWS_PER_CHUNK = 15   # ~15 table rows per chunk ≈ 500-700 chars
            OVERLAP_ROWS   = 2    # 2-row overlap preserves context at boundaries
            for start in range(0, len(lines), ROWS_PER_CHUNK - OVERLAP_ROWS):
                group = lines[start : start + ROWS_PER_CHUNK]
                chunk_text = "\n".join(group).strip()
                if len(chunk_text) >= 20:
                    chunks.append({"page": page_num, "text": chunk_text})
            continue  # skip sentence-aware path for this page

        sentences = [s.strip() for s in _SENT_RE.split(raw_text) if s.strip()]
        if not sentences:
            continue

        current: list[str] = []
        current_len: int = 0

        for sent in sentences:
            sent_len = len(sent)

            # Hard cap: a single sentence longer than 1.5× chunk_size
            # is split character-wise so we never produce a giant chunk
            if sent_len > chunk_size * 1.5:
                # Flush what we have first
                if current:
                    chunks.append({"page": page_num, "text": " ".join(current)})
                    current = current[-overlap_sentences:]
                    current_len = sum(len(s) for s in current)
                # Character-split the giant sentence
                for start in range(0, sent_len, chunk_size - 100):
                    part = sent[start : start + chunk_size].strip()
                    if part:
                        chunks.append({"page": page_num, "text": part})
                continue

            # Would adding this sentence overflow the target size?
            if current_len + sent_len > chunk_size and current:
                chunks.append({"page": page_num, "text": " ".join(current)})
                # Sentence-level overlap: carry the last N sentences forward
                current = current[-overlap_sentences:]
                current_len = sum(len(s) for s in current)

            current.append(sent)
            current_len += sent_len

        if current:
            chunks.append({"page": page_num, "text": " ".join(current)})

    # Final safety pass: drop chunks that are too short to produce a meaningful
    # embedding (< 20 chars after stripping whitespace).  These arise from
    # pages that contain only headers, page numbers, or decorative elements.
    return [c for c in chunks if len(c["text"].strip()) >= 20]


import httpx
import json

def check_ollama_availability() -> dict:
    try:
        if not USE_OLLAMA_TAGGING:
            return {"available": False, "models": [], "has_supported_model": False, "warning": None}
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"available": True, "models": models, "has_supported_model": len(models) > 0, "warning": None}
    except Exception:
        pass
    return {"available": False, "models": [], "has_supported_model": False, "warning": None}

def call_ollama(prompt: str, model: str = "") -> str:
    try:
        selected_model = model or OLLAMA_MODEL
        if not USE_OLLAMA_TAGGING or not selected_model:
            return ""
        r = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json={
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=30.0)
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception as e:
        print(f"Ollama generation failed: {e}")
    return ""



def check_model_version_match() -> bool:
    """
    Returns True if the configured embedding model matches what was used for
    existing vectors.  Saves the model name on first run.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                "SELECT value FROM db_meta WHERE key = 'embedding_model'"
            ).fetchone()
        except sqlite3.OperationalError:
            return True
        stored = row["value"] if row else None
        if stored is None:
            cursor.execute(
                "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('embedding_model', ?)",
                (EMBEDDING_MODEL_NAME,),
            )
            conn.commit()
            return True
        return stored == EMBEDDING_MODEL_NAME
    finally:
        conn.close()


# Classifier signature — bump this string whenever you change model names or thresholds
# Format: <deberta_model>|subj=<thr>|meth=<thr>|dtype=<thr>
_CLASSIFIER_SIGNATURE = (
    f"{CLASSIFIER_MODEL_NAME}|subj=0.35|meth=0.28|dtype=0.40|kw-fallback=v1"
)


def get_classifier_signature() -> str:
    """Return stored classifier signature from DB (empty string if not set)."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT value FROM db_meta WHERE key = 'classifier_signature'"
        ).fetchone()
        return row["value"] if row else ""
    except Exception:
        return ""
    finally:
        conn.close()


def save_classifier_signature() -> None:
    """Persist current classifier signature to DB."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('classifier_signature', ?)",
        (_CLASSIFIER_SIGNATURE,),
    )
    conn.commit()
    conn.close()


def classifier_needs_reindex() -> bool:
    """True if the stored signature differs from the current one."""
    stored = get_classifier_signature()
    return stored != "" and stored != _CLASSIFIER_SIGNATURE


def save_model_version():
    """Persists the current model name into db_meta. Call after /reset."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('embedding_model', ?)",
        (EMBEDDING_MODEL_NAME,),
    )
    conn.commit()
    conn.close()


def _distilbart_summary(text_sample: str) -> str | None:
    """
    Run DistilBART-CNN-12-6 on the text sample and return a one-sentence summary.
    Returns None if the model is unavailable — caller falls back to rule-based.
    Input is capped at 1024 tokens (~800 words) which is DistilBART's max context.
    """
    bart = get_bart_model()
    if bart is None:
        return None
    try:
        # DistilBART max_length=1024 tokens; we pass ~600 words to stay safe
        snippet = " ".join(text_sample.split()[:600])
        if not snippet.strip():
            return None
        out = bart(
            snippet,
            max_length=60,
            min_length=15,
            do_sample=False,
            truncation=True,
        )
        summary = out[0]["summary_text"].strip()
        # Cap to first sentence and 180 chars
        first_sent = re.split(r"(?<=[.!?])\s", summary)[0]
        return first_sent[:180] if first_sent else None
    except Exception as e:
        print(f"DistilBART summarization failed: {e}")
        return None


def _get_dynamic_taxonomy() -> tuple[list[dict], frozenset[str]]:
    conn = get_db_connection()
    try:
        dims = conn.execute("SELECT id, display_name, is_multi_label FROM taxonomy_dimensions ORDER BY dim_order").fetchall()
        
        dimensions = []
        all_labels = set()
        
        for d in dims:
            cats = conn.execute("SELECT name FROM taxonomy_categories WHERE dimension_id=?", (d["id"],)).fetchall()
            labels = [c["name"] for c in cats]
            dimensions.append({
                "id": d["id"],
                "display_name": d["display_name"],
                "is_multi_label": bool(d["is_multi_label"]),
                "labels": labels
            })
            all_labels.update(labels)
            
        all_labels.update([
            "Course Syllabus", "Syllabus", "Lecture Notes", "Lab Report", "Lab Notes",
            "Assignment", "Homework", "Final Exam", "Midterm Exam", "Exam / Quiz",
            "Report", "Question Bank", "Graduate Level", "Undergraduate Level", "Doctoral Level",
            "Writing-Intensive", "Discussion-Based", "Has Prerequisites",
            "Academic Document", "Document", "General", "Science", "Research",
        ])
        
        return dimensions, frozenset(all_labels)
    finally:
        conn.close()


def _classify_dimensions(text_sample: str, filename: str) -> dict:
    from core.db import get_db_connection
    dims_labels, _ = _get_dynamic_taxonomy()
    
    assigned = {}
    
    ollama_status = check_ollama_availability()
    if ollama_status["available"] and ollama_status["models"]:
        # Unsupervised Taxonomy Generation via LLM
        model = OLLAMA_MODEL or ollama_status["models"][0]
        
        # Build prompt showing existing taxonomy
        existing_tax = []
        for dim in dims_labels:
            existing_tax.append(f"Dimension: '{dim['id']}' | Categories: {', '.join(dim['labels'])}")
            
        tax_context = "\\n".join(existing_tax) if existing_tax else "No existing dimensions or categories. You must invent them."
        
        prompt = f"""You are an expert document taxonomy system. Analyze the following document snippet.
Your task is to classify this document by assigning it to a broad 'Dimension' (e.g., 'department', 'industry', 'document_type', 'subject') and a specific 'Category' within that dimension.

Existing Taxonomy Database:
{tax_context}

If the document strongly fits an EXISTING Dimension and Category, use those. 
If it does NOT fit, you must INVENT a NEW Dimension and a NEW Category. Keep names short (1-3 words).

Respond ONLY with a valid JSON object in this exact format, with no markdown, no backticks, and no extra text:
{{
  "dimension_id": "the_dimension_name_in_lowercase",
  "category_name": "The Category Name"
}}

Document Snippet:
{text_sample[:2500]}
"""
        response = call_ollama(prompt, model=model)
        
        # Clean response in case LLM added markdown block
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        try:
            import json
            import uuid
            result = json.loads(response)
            dim_id = result.get("dimension_id", "").strip().lower().replace(" ", "_")
            cat_name = result.get("category_name", "").strip()
            
            if dim_id and cat_name:
                conn = get_db_connection()
                try:
                    # Check if dimension exists
                    row = conn.execute("SELECT id FROM taxonomy_dimensions WHERE id = ?", (dim_id,)).fetchone()
                    if not row:
                        import random
                        colors = ['#0A84FF', '#BF5AF2', '#30D158', '#FF9F0A', '#FF453A', '#32ADE6']
                        bg_colors = ['#e8f2ff', '#f7eefe', '#e8f9ed', '#fff4e0', '#ffe8e6', '#e6f5ff']
                        c_idx = random.randint(0, len(colors)-1)
                        conn.execute(
                            "INSERT INTO taxonomy_dimensions (id, display_name, ui_color, ui_dim_color, ui_icon) VALUES (?, ?, ?, ?, ?)",
                            (dim_id, dim_id.replace("_", " ").title(), colors[c_idx], bg_colors[c_idx], 'ti-tag')
                        )
                    
                    # Check if category exists
                    row = conn.execute("SELECT id FROM taxonomy_categories WHERE dimension_id = ? AND name = ?", (dim_id, cat_name)).fetchone()
                    if not row:
                        conn.execute("INSERT INTO taxonomy_categories (dimension_id, name) VALUES (?, ?)", (dim_id, cat_name))
                        
                    conn.commit()
                except Exception as db_e:
                    print("DB Insert error during dynamic taxonomy:", db_e)
                finally:
                    conn.close()
                
                assigned[dim_id] = [cat_name]
                return assigned
        except Exception as e:
            print(f"Ollama taxonomy generation failed or returned invalid JSON: {e} -> {response}")
            # Fall back to DeBERTa if Ollama fails
            pass

    # Fallback to DeBERTa if Ollama is not available or fails
    classifier = get_deberta_classifier()
    
    for dim_info in dims_labels:
        dim_id = dim_info["id"]
        labels = dim_info["labels"]
        is_multi = dim_info["is_multi_label"]
        
        if not labels:
            continue
            
        try:
            if classifier is not None:
                result = classifier(text_sample[:1500], labels, multi_label=is_multi)
                if is_multi:
                    valid_labels = [label for label, score in zip(result["labels"], result["scores"]) if score > 0.4]
                    if valid_labels:
                        assigned[dim_id] = valid_labels
                else:
                    if result["scores"][0] > 0.35:
                        assigned[dim_id] = [result["labels"][0]]
            else:
                import numpy as np
                from services.embeddings import get_embedding_model
                model = get_embedding_model()
                label_embeddings = model.encode(labels, normalize_embeddings=True, show_progress_bar=False)
                doc_emb = model.encode(text_sample[:1500], normalize_embeddings=True, show_progress_bar=False)
                similarities = (label_embeddings @ doc_emb).tolist()
                
                if is_multi:
                    valid_labels = [labels[i] for i, s in enumerate(similarities) if s > 0.4]
                    if valid_labels:
                        assigned[dim_id] = valid_labels
                else:
                    best_idx = int(np.argmax(similarities))
                    if float(similarities[best_idx]) > 0.35:
                        assigned[dim_id] = [labels[best_idx]]
        except Exception as e:
            print(f"Classification failed for {dim_id}: {e}")
            
    return assigned


def _deberta_tags(text_sample: str, filename: str) -> list[str]:
    return _extract_keyword_tags(text_sample, filename)


def _extract_keyword_tags(text_sample: str, filename: str) -> list[str]:
    _, _SIDEBAR_LABELS = _get_dynamic_taxonomy()
    _SIDEBAR_LOWER = frozenset(s.lower() for s in _SIDEBAR_LABELS)

    raw = _extract_content_keywords(text_sample, n=10)

    keyword_tags: list[str] = []
    for kw in raw:
        if kw.lower() not in _SIDEBAR_LOWER and kw not in _SIDEBAR_LABELS:
            keyword_tags.append(kw)
        if len(keyword_tags) >= 8:
            break

    return keyword_tags


def _extract_key_findings(text_sample: str) -> list[str]:
    """
    Extract 3 key sentences from the document using heuristic importance signals.
    Targets: policy statements, deadlines, requirements, grading criteria.
    Falls back to first 3 meaningful sentences if no high-signal content found.
    """
    HIGH_SIGNAL = re.compile(
        r"\b(required|must|deadline|due|grading|policy|percent|%|credit|prerequisite"
        r"|attendance|submission|penalty|weight|points|late|exam|final|objective"
        r"|will be|students (must|are required|should))\b",
        re.IGNORECASE,
    )
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text_sample[:3000]).strip())
    high = [s.strip() for s in sentences if len(s.strip()) > 30 and HIGH_SIGNAL.search(s)]
    fallback = [s.strip() for s in sentences if len(s.strip()) > 40]
    pool = high[:3] if high else fallback[:3]
    # Truncate each to 120 chars
    return [s[:120] + ("…" if len(s) > 120 else "") for s in pool]


def extract_key_insights(text: str, n: int = 4) -> list[str]:
    """
    Extract key insight sentences from any document.

    Prioritises sentences with scientific/analytical signal words
    (found, showed, demonstrated, conclude, result, evidence, suggest,
    increase, decrease, associated, significant, etc.).
    Falls back to the first substantive sentences for non-research docs.
    """
    SCIENTIFIC = re.compile(
        r"\b(found|show(ed|s)?|demonstrat(ed|es)?|conclud(ed|es)?|result(s|ed)?|"
        r"suggest(s|ed)?|indicat(ed|es)?|reveal(ed|s)?|associat(ed|es)?|"
        r"signific(ant|antly)|evidence|effect|increas(ed|es)?|decreas(ed|es)?|"
        r"higher|lower|greater|reduc(ed|es)?|improv(ed|es)?|inhibit(ed|s)?|"
        r"activat(ed|es)?|promot(ed|es)?|suppress(ed|es)?|correlat(ed|es)?|"
        r"compared|analysis|measur(ed|es)?|observ(ed|es)?)\b",
        re.IGNORECASE,
    )
    POLICY = re.compile(
        r"\b(required|must|deadline|objective|goal|purpose|key|important|"
        r"critical|essential|primary|main|focus)\b",
        re.IGNORECASE,
    )

    body = re.sub(r"\s+", " ", (text or "")[:5000]).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.strip()) > 40]

    scored: list[tuple[int, str]] = []
    for s in sentences:
        sci   = len(SCIENTIFIC.findall(s))
        pol   = len(POLICY.findall(s))
        score = sci * 2 + pol
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    pool = [s for _, s in scored[:n]] if scored else sentences[:n]

    return [s[:300] + ("…" if len(s) > 300 else "") for s in pool]


async def extract_ai_metadata(text_sample: str, filename: str = "") -> dict:
    """
    GPU-powered metadata extraction — no Ollama, no external services.

    Pipeline:
      Summary        → configured abstractive summarizer
      Classifications → configured NLI classifier → dynamic taxonomy dimensions
      Tags (keywords) → YAKE + TF-IDF → specific per-document terms (Tags page only)
      Findings       → heuristic sentence extraction
      Entities       → regex date extraction
    """
    loop = asyncio.get_event_loop()

    summary = await loop.run_in_executor(None, _distilbart_summary, text_sample)
    if not summary:
        summary = _rule_based_summary(filename, text_sample)

    # Full multi-perspective dimension classification
    classifications = await loop.run_in_executor(
        None, _classify_dimensions, text_sample, filename
    )

    # Keyword tags (shown on Tags page) — content-specific terms only
    tags = _extract_keyword_tags(text_sample, filename)

    key_findings = _extract_key_findings(text_sample)

    dates = []

    return {
        "summary": summary,
        "tags": tags,
        "classifications": classifications,
        "key_findings": key_findings,
        "entities": {
            "Companies": [],
            "Dates": dates,
            "Project_Names": [],
        },
    }
