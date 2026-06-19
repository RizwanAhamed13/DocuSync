import asyncio
import json
import logging
import os
import re
import sqlite3
import threading

import httpx

logger = logging.getLogger(__name__)

from embeddings import EMBEDDING_MODEL_NAME, get_chroma_collection, get_embedding_model

_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_URL = f"{_OLLAMA_HOST}/api/generate"
OLLAMA_BASE_URL = _OLLAMA_HOST

# Primary tagging model — configurable via env var.
# llama3.1:8b is the right fit: JSON extraction/classification at 4.7 GB GPU,
# 3–5 s per doc. Fallback list tried in order if primary fails or is not pulled.
_PRIMARY_MODEL  = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
_FALLBACK_MODELS = ["llama3", "phi3"]

ollama_lock = asyncio.Lock()

_DEFAULT_METADATA = {
    "summary": "AI summary unavailable (is Ollama running?)",
    "tags": ["Uncategorized"],
    "key_findings": ["Could not extract findings automatically."],
    "entities": {"Companies": [], "Dates": [], "Project_Names": []},
}

# ── Junk tags that provide zero value ────────────────────────────────────────
_GENERIC_TAGS: frozenset[str] = frozenset({
    "uncategorized", "general", "document", "text", "file", "content",
    "information", "data", "unknown", "other", "misc", "miscellaneous",
    "n/a", "none", "na", "untitled",
})

# ── Words to skip during TF keyword extraction ───────────────────────────────
_TF_SKIP: frozenset[str] = frozenset({
    "course", "class", "classes", "student", "students", "grade", "grades",
    "grading", "assignment", "assignments", "exam", "exams", "lecture",
    "lectures", "week", "weeks", "reading", "readings", "paper", "papers",
    "points", "semester", "syllabus", "instructor", "professor", "university",
    "college", "department", "credit", "credits", "hours", "office", "policy",
    "policies", "schedule", "attendance", "academic", "final", "midterm",
    "quiz", "homework", "textbook", "required", "optional", "section",
    "chapter", "material", "submission", "deadline", "project", "report",
    "writing", "participation", "percent", "percentage", "total", "include",
    "included", "including", "following", "students", "listed", "complete",
    "please", "email", "contact", "available", "provide", "course",
    "based", "first", "second", "third", "general", "special", "specific",
    "additional", "important", "number", "different", "program", "monday",
    "tuesday", "wednesday", "thursday", "friday", "january", "february",
    "march", "april", "august", "september", "october", "november", "december",
    "spring", "summer", "fall", "winter", "syllabus", "office", "hours",
    "make", "work", "time", "class", "will", "able", "learn", "complete",
    "expect", "review", "submit", "receive", "topics", "topic", "cover",
    "covered", "areas", "apply", "applied", "using", "used", "understand",
    "level", "online", "format", "three", "four", "five", "six", "seven",
    "eight", "nine", "zero", "each", "every", "other", "these", "those",
    "their", "there", "where", "when", "what", "which", "while", "whether",
})

# ── Course-code prefix → academic subject ────────────────────────────────────
_DEPT_MAP: dict[str, str] = {
    "CS": "Computer Science", "CSCI": "Computer Science", "CSCE": "Computer Science",
    "COMS": "Computer Science", "CIS": "Computer Science", "CIT": "Computer Science",
    "ECE": "Electrical Engineering", "EE": "Electrical Engineering",
    "ME":  "Mechanical Engineering", "MIE": "Mechanical & Industrial Engineering",
    "CE":  "Civil Engineering", "CHE": "Chemical Engineering",
    "BIOL": "Biology", "BIO": "Biology", "BIOC": "Biology",
    "BIOCHEM": "Biochemistry", "BCH": "Biochemistry",
    "CHEM": "Chemistry", "CHЕМ": "Chemistry",
    "PHYS": "Physics", "PHY": "Physics", "PH": "Physics",
    "MATH": "Mathematics", "MTH": "Mathematics", "STAT": "Statistics",
    "PSYCH": "Psychology", "PSY": "Psychology",
    "ECON": "Economics", "EC": "Economics",
    "FIN": "Finance", "FINC": "Finance",
    "ACCT": "Accounting", "ACC": "Accounting",
    "MKTG": "Marketing", "MKT": "Marketing",
    "MGMT": "Management", "MGMNT": "Management", "MGT": "Management",
    "ENGL": "English Literature", "ENG": "English", "WRIT": "Writing",
    "HIST": "History", "HIS": "History",
    "PHIL": "Philosophy",
    "SOC":  "Sociology", "SOCL": "Sociology",
    "ANTH": "Anthropology",
    "POLS": "Political Science", "POL": "Political Science", "GOVT": "Political Science",
    "GEOG": "Geography", "GEO": "Geography",
    "GEOL": "Geology",
    "ENVS": "Environmental Science", "ENV": "Environmental Science",
    "NUTR": "Nutrition", "NUT": "Nutrition", "FOOD": "Food Science",
    "FS":   "Food Science",
    "NURS": "Nursing", "NUR": "Nursing",
    "PUBH": "Public Health", "PH2": "Public Health",
    "MED":  "Medicine",
    "BIOL": "Biology",
    "COMM": "Communications", "COM": "Communications",
    "JOUR": "Journalism", "JOURNAL": "Journalism",
    "MDIA": "Media Studies", "MEDIA": "Media Studies",
    "ART":  "Art", "ARTS": "Arts",
    "MUSC": "Music", "MUS": "Music", "MUSIC": "Music",
    "THTR": "Theatre", "THEA": "Theatre",
    "FILM": "Film Studies",
    "EDUC": "Education", "EDU": "Education", "EME": "Educational Technology",
    "LIBR": "Library Science",
    "LAW":  "Law", "LEGAL": "Law", "LEG": "Law",
    "BUSN": "Business", "BUS": "Business", "BA": "Business Administration",
    "MBA":  "Business Administration",
    "ARCH": "Architecture",
    "AGRN": "Agriculture", "AGRO": "Agriculture",
    "HONORS": "Honors Program",
}

# ── Zero-shot semantic topic labels ───────────────────────────────────────────
# Used by _get_zero_shot_label() when no department code is found in the text.
# Labels are encoded once with the BGE model and cached in _label_embeddings.
#
# Industry reference: Azure Cognitive Services Text Analytics and Cohere
# Classify both perform embedding-based zero-shot label matching.  Using our
# already-loaded BGE model avoids the 1.6 GB facebook/bart-large-mnli download
# while achieving comparable results for clearly-structured academic documents.
_ZERO_SHOT_LABELS: list[str] = [
    "Computer Science and Programming",
    "Mathematics and Statistics",
    "Biology and Life Sciences",
    "Chemistry",
    "Physics",
    "Electrical and Computer Engineering",
    "Mechanical and Civil Engineering",
    "Economics and Finance",
    "Business Administration and Management",
    "Accounting and Auditing",
    "Marketing and Communications",
    "Psychology and Cognitive Science",
    "Sociology and Anthropology",
    "History and Political Science",
    "English Literature and Writing",
    "Journalism and Media Studies",
    "Art History and Fine Arts",
    "Music and Performing Arts",
    "Education and Instructional Design",
    "Public Health and Epidemiology",
    "Nutrition and Food Science",
    "Environmental Science and Geography",
    "Law and Legal Studies",
    "Architecture and Urban Planning",
    "Agriculture and Life Sciences",
    "Library and Information Science",
]

# Thread-safe cache for label embeddings (computed once, reused forever)
_label_embeddings = None
_label_embeddings_lock = threading.Lock()


def _get_zero_shot_label(text: str) -> str | None:
    """
    Classify document text into a high-level topic via BGE semantic label matching.

    Method
    ------
    1. Encode the first 600 characters of document text with the BGE model.
    2. Compute cosine similarity against pre-encoded label strings.
    3. Return the label with the highest similarity if it exceeds 0.35.
       Below that threshold the text is too generic or ambiguous to classify.

    Label embeddings are cached globally after the first call — subsequent
    calls pay only the document-snippet encoding cost (~2 ms on CPU).

    Similarity threshold 0.35
    -------------------------
    BGE cosine space: same-topic text pairs typically score 0.45–0.85.
    Cross-topic pairs score 0.10–0.30.  0.35 is a conservative gate that
    avoids false positives on boilerplate administrative text while still
    classifying clear subject matter correctly.
    """
    global _label_embeddings
    try:
        import numpy as np
        from embeddings import get_embedding_model

        model = get_embedding_model()

        # Encode label strings once, then cache (thread-safe double-check lock)
        if _label_embeddings is None:
            with _label_embeddings_lock:
                if _label_embeddings is None:
                    _label_embeddings = model.encode(
                        _ZERO_SHOT_LABELS,
                        normalize_embeddings=True,
                        batch_size=32,
                        show_progress_bar=False,
                    )

        # Encode document snippet (first 600 chars captures title + course code)
        snippet = re.sub(r"<[^>]+>", " ", text or "")[:600]
        if not snippet.strip():
            return None

        doc_emb = model.encode(
            snippet, normalize_embeddings=True, show_progress_bar=False
        )
        similarities = (_label_embeddings @ doc_emb).tolist()
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])

        if best_score > 0.35:
            return _ZERO_SHOT_LABELS[best_idx]
    except Exception:
        pass
    return None


# ── Keyword clusters → topic tags ─────────────────────────────────────────────
_TOPIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Machine Learning",    ["machine learning", "deep learning", "neural network", "tensorflow", "pytorch"]),
    ("Data Science",        ["data science", "data analysis", "pandas", "matplotlib", "jupyter"]),
    ("Algorithms",          ["algorithm", "data structure", "complexity", "sorting", "graph theory"]),
    ("Programming",         ["python", "java", "c++", "javascript", "programming", "software development"]),
    ("Networks",            ["networking", "tcp/ip", "socket", "protocol", "internet"]),
    ("Databases",           ["database", "sql", "nosql", "mongodb", "relational"]),
    ("Cybersecurity",       ["cybersecurity", "cryptography", "security", "vulnerability", "firewall"]),
    ("Statistics",          ["statistics", "regression analysis", "hypothesis testing", "probability distribution", "anova"]),
    ("Research Methods",    ["research methods", "research design", "qualitative research", "quantitative research", "literature review"]),
    ("Lab Work",            ["lab report", "lab section", "lab manual", "laboratory assignment", "lab activity"]),
    ("Group Projects",      ["group project", "team project", "group assignment", "collaborative project"]),
    ("Attendance Policy",   ["attendance policy", "mandatory attendance", "absences allowed", "attendance will be taken"]),
    ("Late Work Policy",    ["late submission", "late penalty", "late work policy", "points deducted for late"]),
    ("Cell Biology",        ["cell biology", "mitosis", "meiosis", "dna replication", "protein synthesis"]),
    ("Ecology",             ["ecology", "ecosystem", "biodiversity", "population dynamics", "habitat"]),
    ("Organic Chemistry",   ["organic chemistry", "reaction mechanism", "functional group", "organic synthesis"]),
    ("Calculus",            ["calculus", "differential equation", "multivariable calculus", "integration techniques"]),
    ("Linear Algebra",      ["linear algebra", "vector space", "eigenvalue", "matrix multiplication"]),
    ("Financial Analysis",  ["financial analysis", "financial statement", "balance sheet", "cash flow analysis"]),
    ("Marketing Strategy",  ["marketing strategy", "market segmentation", "consumer behavior", "brand management"]),
    ("Supply Chain",        ["supply chain", "logistics management", "inventory management", "operations management"]),
    ("World History",       ["world history", "ancient civilizations", "medieval history", "colonial history"]),
    ("American Politics",   ["american politics", "u.s. congress", "u.s. constitution", "american government", "electoral"]),
    ("Nutrition Science",   ["nutrition science", "dietary", "macronutrient", "micronutrient", "metabolism", "dietetics"]),
    ("Food Chemistry",      ["food chemistry", "food science", "food preservation", "food fermentation"]),
    ("Public Health",       ["public health", "epidemiology", "disease prevention", "global health", "health disparities"]),
    ("GIS",                 ["geographic information system", "gis analysis", "spatial analysis", "remote sensing", "arcgis"]),
    ("IoT",                 ["internet of things", "iot device", "sensor network", "embedded system", "microcontroller"]),
    ("Journalism",          ["journalism", "news writing", "news reporting", "media ethics", "investigative reporting"]),
    ("Media Studies",       ["media studies", "mass media", "pop culture analysis", "media representation"]),
    ("Music Theory",        ["music theory", "music harmony", "counterpoint", "music composition", "musical notation"]),
    ("Education Technology",["educational technology", "e-learning", "instructional design", "learning management system"]),
    ("Accounting",          ["accounting principles", "financial reporting", "gaap", "audit", "tax accounting"]),
]


def _course_level(number_str: str) -> str | None:
    """Map a course number string to its academic level label."""
    try:
        n = int(re.sub(r"\D", "", number_str)[:4])
    except (ValueError, TypeError):
        return None
    if n < 200:   return "Introductory Level"
    if n < 300:   return "Sophomore Level"
    if n < 400:   return "Upper Division"
    if n < 500:   return "Advanced Undergraduate"
    if n < 700:   return "Graduate Level"
    return "Doctoral Level"


# Words that look like course-code prefixes but aren't departments
_NOT_COURSE_PREFIX: frozenset[str] = frozenset({
    "SPRING", "FALL", "SUMMER", "WINTER", "MOST", "RECENT", "HONORS",
    "FINAL", "EXAM", "QUIZ", "UNIT", "WEEK", "INTRO", "NOTES", "REVIEW",
    "LAST", "NEXT", "THIS", "THAT", "FROM", "WITH", "INTO", "OVER", "UNDER",
    "AFTER", "JUST", "ALSO", "ONLY", "BOTH", "EACH", "MANY", "SOME", "SUCH",
    "WHEN", "THAN", "THEN", "THEY", "HAVE", "WILL", "BEEN", "WERE", "WHAT",
    "WHICH", "WHERE", "WHILE", "THESE", "THOSE", "OTHER", "ABOUT", "ABOVE",
    "BELOW", "REPORT", "SYLLAB", "MW", "TR", "TTH", "MWF", "TH",
})

# Lines that are not course titles (schedule / credentials / location)
_TITLE_SKIP_PAT = re.compile(
    r"^(\d|/|[A-Z]\d{2,}|MW\b|TTh\b|MWF\b|Section|Office|Fall |Spring |Summer |Winter "
    r"|Monday|Tuesday|Wednesday|Thursday|Friday"
    r"|Ph\.?D|Dr\.|Professor:|Instructor:|Credit|Room\s?\d"
    r"|Please |After class|Schedule your|TA\s*:|Note\s*:|Tel\s*:|Fax\s*:"
    r"|Course\s+(Goals|Objectives|Outcomes|Policies|Materials|Requirements)\s*:"
    r"|Learning\s+(Goals|Objectives|Outcomes)\s*:"
    r"|This\s+course\b|The\s+course\b|Students\s+will\b|You\s+will\b)",
    re.IGNORECASE,
)
_TITLE_NOISE_PAT = re.compile(
    r"(\d{1,2}:\d{2}|[AP]M\b|Office Hours|@|\.edu|https?://|prerequisites|credit hours"
    r"|timeslot|book a |subject to change|is subject|this syllabus"
    r"|phone:|fax:|email\b|location:|classroom:|building|room\s*\d|floor\s*\d"
    r"|amherst|massachusetts|university of|college of|school of"
    r"|isenberg|islington|business school"
    r"|ph\.?d\.?|m\.?s\.?|m\.?ed\.?|instructor:|professor:|faculty|prof\b"
    r"|lecture:|section\b|syllabus is|reading for this"
    r"|prereq|zoom\s*link|department of|\bta\b\s*:?"
    r"|after class|schedule your|contact info"
    r"|graduate\s+ta|graduate\s+stu"
    r"|student\s+learning|information\s+on\s+how"
    r"|instructor\s+info|blackboard\s+learn|\bblackboard\b"
    r"|lab\s+section|management\s+system"
    r"|ILC\s+[A-Z]\d|SOM\s+[A-Z]\d|LGRT|DUBOIS|GOESS"
    r"|[A-Z][a-z]+\s+\d{3,4}\b(?!\s*:))",   # room codes like "Thompson 828", "ISB 135"
    re.IGNORECASE,
)


def _find_course_code(text: str, search_zone: int = 250) -> tuple[re.Match | None, str | None]:
    """
    Find the most likely course code in `text[:search_zone]`.
    Returns (match, dept_name). Prefers longest known dept prefix.
    """
    zone = text[:search_zone]
    for prefix in sorted(_DEPT_MAP.keys(), key=len, reverse=True):
        m = re.search(
            rf"\b({re.escape(prefix)}[\s\-]?\d{{2,4}}[A-Z]{{0,2}})\b",
            zone, re.IGNORECASE,
        )
        if m:
            return m, _DEPT_MAP[prefix]
    return None, None


def _is_good_title(line: str) -> bool:
    """Return True if this line looks like a course title (not noise)."""
    if not line or len(line) < 8 or len(line) > 90:
        return False
    # Reject lines ending with colon (section headers like "Course Description:")
    if line.rstrip().endswith(":"):
        return False
    # Reject lines containing tab characters (TA contact blocks, schedule tables)
    if "\t" in line:
        return False
    # Reject scanned/garbled text: "C o u r s e I n f o r m a t i o n"
    # or partial OCR artifacts like "Sum m ary De sc ript ion"
    words = line.split()
    single_char_ratio = sum(1 for w in words if len(w) == 1) / max(len(words), 1)
    if single_char_ratio > 0.45:
        return False
    # Also reject partial-spaced text by average word length
    # Real course titles (5+ words) have avg word len ≥ 3.5; garbled text is shorter
    if len(words) >= 5:
        avg_len = sum(len(w) for w in words) / len(words)
        if avg_len < 3.5:
            return False
    # Reject lines with 3+ consecutive spaces (garbled / extracted OCR noise)
    if "   " in line:
        return False
    if _TITLE_SKIP_PAT.match(line):
        return False
    if _TITLE_NOISE_PAT.search(line):
        return False
    if re.search(r"\d{4,}|@|\.edu|\(4\d{4}\)|TYOF|, Ph\.", line, re.IGNORECASE):
        return False
    # Skip lines that start with lowercase (likely mid-sentence fragments)
    if line[0].islower():
        return False
    # Skip lines that are mostly punctuation / symbols
    alpha_ratio = sum(c.isalpha() or c.isspace() for c in line) / max(len(line), 1)
    if alpha_ratio < 0.6:
        return False
    # Skip lines that are just one word unless it looks like a proper noun/acronym
    if len(words) == 1 and not line.isupper():
        return False
    # Skip generic section headers that made it this far
    generic_headers = {
        "course outline", "course information", "course overview",
        "course description", "course summary", "course details",
        "course syllabus", "syllabus", "notes", "schedule",
        "table of contents", "class schedule", "class information",
    }
    if line.lower().strip() in generic_headers:
        return False
    return True


def _extract_course_info(filename: str, text: str) -> dict:
    """
    Parse course code, title, and term from the document.
    Priority: filename (most reliable) → first 250 chars of text → wider text.
    """
    clean = re.sub(r"<[^>]+>", " ", text or "")
    info  = {"code": None, "title": None, "term": None, "dept": None, "level": None}

    fn_clean = re.sub(r"\.(pdf|docx?|txt|md)$", "", filename, flags=re.IGNORECASE)
    fn_upper = re.sub(r"[_\-.]", " ", fn_clean).upper()

    # ── 1. Course code (filename first, then text header) ─────────────────────
    code_m, dept = _find_course_code(fn_upper + " " + clean, search_zone=len(fn_upper) + 300)

    # Re-search: try filename alone first for accuracy
    fn_m, fn_dept = _find_course_code(fn_upper)
    if fn_m:
        code_m, dept = fn_m, fn_dept
        # Re-do in actual text to get position for title extraction
        text_m, _ = _find_course_code(clean, search_zone=400)
        title_ref = text_m or code_m
    else:
        text_m, _ = _find_course_code(clean, search_zone=300)
        code_m    = text_m or code_m
        title_ref = code_m

    if code_m:
        raw = re.sub(r"\s+", " ", code_m.group(0).strip().upper())
        info["code"] = raw
        if dept:
            info["dept"] = dept
        num_m = re.search(r"\d{2,4}", raw)
        if num_m:
            info["level"] = _course_level(num_m.group())

    # ── 2. Course title ───────────────────────────────────────────────────────
    if title_ref and title_ref.end() < len(clean):
        after = clean[title_ref.end(): title_ref.end() + 400]

        # Same line: "CS 568: Machine Learning" or "BIOL 151 – Intro Biology"
        same = re.match(r"[\s:–—()\-]+([A-Z][^\n]{6,80})", after)
        if same and _is_good_title(same.group(1).strip()):
            info["title"] = same.group(1).strip()[:80]

        # Next meaningful lines
        if not info["title"]:
            for line in after.split("\n"):
                line = line.strip()
                if _is_good_title(line):
                    info["title"] = line[:80]
                    break

    # ── 3. Academic term ──────────────────────────────────────────────────────
    term_m = re.search(
        r"(spring|fall|summer|winter)\s+(20\d{2})",
        re.sub(r"[_\-.]", " ", fn_clean).lower() + " " + clean[:600].lower(),
    )
    if term_m:
        info["term"] = f"{term_m.group(1).title()} {term_m.group(2)}"

    return info


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
    """
    Industry-grade keyword extraction: YAKE → mini-KeyBERT → TF-IDF cascade.

    Runs all three methods and merges results, deduplicating by lowercase key.
    Each method targets a different weakness of the others:

      YAKE (Yet Another Keyword Extractor — Campos et al. 2020)
        Statistical, position-weighted, co-occurrence-aware.
        Extracts multi-word keyphrases (e.g. "machine learning").
        Lower YAKE score = more important (inverse).
        Advantage: no ML model, fast, handles technical jargon well.

      mini-KeyBERT (subset of KeyBERT — Grootendorst 2020)
        Uses our already-loaded BGE embedding model.
        Embeds candidate n-grams and picks those most similar to the
        document embedding.  Catches semantically central terms that low-TF
        words like "quantum", "epistemology", "econometric" represent well.
        Advantage: semantic relevance, not just frequency.

      TF-IDF (sklearn)
        IDF-weighted term frequency on the document alone (no corpus needed
        for the TF side; IDF is approximated using sklearn's sublinear_tf).
        Advantage: reliable fallback, handles very short texts where YAKE
        and KeyBERT have too few candidates.

    Returns a deduplicated list of properly-capitalised tag strings.
    """
    from collections import Counter

    body = re.sub(r"<[^>]+>", " ", text or "")[:4000]
    body_lower = body.lower()

    collected: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        key = phrase.lower().strip()
        if (key not in seen
                and key not in _TF_SKIP
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
            if not any(skip in phrase.lower() for skip in _TF_SKIP):
                _add(phrase)
    except Exception as _yake_err:
        pass  # YAKE unavailable or failed — continue to next method

    # ── 2. mini-KeyBERT — semantic candidate scoring ──────────────────────────
    # Only run if YAKE produced fewer than n results (saves compute when YAKE
    # already found good keyphrases, since both share the same output goal).
    if len(collected) < n:
        try:
            from embeddings import get_embedding_model
            import numpy as np

            model = get_embedding_model()

            # Candidate generation: unigrams (5+ chars) + bigrams
            words = re.findall(r"\b[A-Za-z][a-z]{3,}\b", body)
            unigrams = [w for w in set(words) if w.lower() not in _TF_SKIP]
            bigrams = [
                f"{words[i]} {words[i + 1]}"
                for i in range(len(words) - 1)
                if words[i].lower() not in _TF_SKIP
                and words[i + 1].lower() not in _TF_SKIP
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
        filtered = [w for w in words if w not in _TF_SKIP]
        counter = Counter(filtered)
        for w, c in counter.most_common(30):
            if c >= 2 and len(collected) < n * 2:
                _add(w)

    return collected[:n]


def _rule_based_summary(filename: str, text: str) -> str:
    """
    Generate a one-sentence summary from document structure without any LLM.
    Strategy: course_code + title + term + first sentence of overview.
    """
    info = _extract_course_info(filename, text)
    overview = _extract_overview_sentence(text)

    parts: list[str] = []

    # Build the label: "BIOL 151: Introductory Biology" or just the title
    # Sanity check: discard extracted title if it's a noise artifact
    title = info["title"]
    if title and (title.endswith(":") or "   " in title or len(title.split()) == 1):
        title = None

    if info["code"] and title:
        label = f"{info['code']}: {title}"
    elif info["code"]:
        label = info["code"]
        if info["dept"]:
            label = f"{info['code']} ({info['dept']})"
    elif title:
        label = title
    else:
        # Fallback: clean filename
        label = re.sub(r"\.(pdf|docx?|txt)$", "", filename, flags=re.IGNORECASE)
        label = re.sub(r"[_\-]", " ", label)
        label = re.sub(r"\s+", " ", label).strip()  # collapse " - " → " " → " "

    term_str = f" — {info['term']}" if info["term"] else ""
    level_str = f" {info['level'].lower()}" if info["level"] else ""
    doc_type = "course syllabus" if _is_syllabus(filename, text) else "academic document"

    base = f"{label}{term_str}{level_str} {doc_type}"

    if overview:
        # Append overview sentence, lowercased continuation
        ov_lower = overview[0].lower() + overview[1:]
        summary = f"{base.rstrip('.')} covering {ov_lower}."
    else:
        summary = f"{base.rstrip('.')}."

    # Hard cap at 180 chars for display
    if len(summary) > 180:
        summary = summary[:177] + "…"

    return summary


def _is_syllabus(filename: str, text: str) -> bool:
    combined = (filename + " " + (text or "")[:300]).lower()
    return "syllabus" in combined or "course overview" in combined or "course description" in combined


def _rule_based_tags(filename: str, text: str) -> list[str]:
    """
    Multi-layer zero-LLM tag extractor.
    Layer 1  — Structured info: course code, dept, title, level, term
    Layer 2  — Document type detection
    Layer 3  — Predefined topic keyword clusters
    Layer 4  — TF-based keyword extraction (document-specific topics)
    Layer 5  — Structural signals: grading style, format, prerequisites
    """
    tags: list[str] = []
    text_lower = (text or "")[:4000].lower()
    combined   = (re.sub(r"[_\-.]", " ", filename) + " " + text_lower[:400]).lower()

    # ── Layer 1: Structured course info ──────────────────────────────────────
    info = _extract_course_info(filename, text)

    if info["dept"]:
        tags.append(info["dept"])
    else:
        # Layer 0: Semantic zero-shot classification — fires only when the
        # course-code dept lookup fails (e.g. non-course documents or unknown
        # dept prefixes).  Uses BGE cosine similarity against human-readable
        # topic labels — no external model needed, reuses the loaded embedder.
        zs_label = _get_zero_shot_label(text)
        if zs_label:
            tags.append(zs_label)

    if info["code"]:
        # Add the course code itself as a searchable tag (e.g. "BIOL 151")
        tags.append(info["code"].upper())

    if info["level"]:
        tags.append(info["level"])

    if info["term"]:
        tags.append(info["term"])

    # ── Layer 2: Document type ────────────────────────────────────────────────
    if _is_syllabus(filename, text):
        tags.append("Course Syllabus")
    elif "exam" in combined and "final" in combined:
        tags.append("Final Exam")
    elif "midterm" in combined:
        tags.append("Midterm Exam")
    elif "question bank" in combined or ("question" in combined and "bank" in combined):
        tags.append("Question Bank")
    elif "exam" in combined or "quiz" in combined:
        tags.append("Exam / Quiz")
    elif "lab report" in combined or "lab manual" in combined:
        tags.append("Lab Report")
    elif "assignment" in combined or "homework" in combined:
        tags.append("Assignment")
    elif "lecture" in combined or "lecture notes" in combined:
        tags.append("Lecture Notes")
    elif "report" in combined:
        tags.append("Report")

    # ── Layer 3: Predefined topic keyword clusters ────────────────────────────
    topic_slots = max(0, 6 - len(tags))  # fill remaining slots
    added = 0
    for topic_tag, keywords in _TOPIC_KEYWORDS:
        if added >= topic_slots:
            break
        if topic_tag not in tags and any(kw in text_lower for kw in keywords):
            tags.append(topic_tag)
            added += 1

    # ── Layer 4: YAKE + mini-KeyBERT + TF-IDF keyword extraction ────────────────
    if len(tags) < 5:
        tf_kws = _extract_content_keywords(text, n=max(1, 5 - len(tags)))
        for kw in tf_kws:
            if kw.lower() not in [t.lower() for t in tags]:
                tags.append(kw)

    # ── Layer 5: Structural signals ───────────────────────────────────────────
    if "writing intensive" in text_lower or "writing-intensive" in text_lower:
        if "Writing-Intensive" not in tags:
            tags.append("Writing-Intensive")
    if ("discussion" in text_lower and "discussion section" in text_lower):
        if "Discussion-Based" not in tags and len(tags) < 7:
            tags.append("Discussion-Based")
    if re.search(r"prerequisite", text_lower):
        if "Has Prerequisites" not in tags and len(tags) < 7:
            tags.append("Has Prerequisites")

    # ── Fallback ──────────────────────────────────────────────────────────────
    if not tags:
        tags = ["Academic Document"]

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique[:7]


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


def get_db_connection():
    # timeout=30: SQLite will retry for up to 30 s on "database is locked" instead of failing fast
    conn = sqlite3.connect("document_metadata.db", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


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
    chunk_size: int = 1800,
    overlap_sentences: int = 3,
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


async def check_ollama_availability() -> dict:
    """Checks if Ollama is running and which models are available."""
    supported_prefixes = ("llama3", "phi3", "llama2", "mistral", "gemma", "qwen")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                has_supported = any(
                    m.startswith(p) for m in models for p in supported_prefixes
                )
                return {
                    "available": True,
                    "models": models,
                    "has_supported_model": has_supported,
                    "warning": (
                        None
                        if has_supported
                        else "No supported model found. Run: ollama pull llama3"
                    ),
                }
    except Exception:
        pass
    return {
        "available": False,
        "models": [],
        "has_supported_model": False,
        "warning": (
            "Ollama unreachable at localhost:11434. "
            "Install from https://ollama.ai then run: ollama pull llama3"
        ),
    }


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
            # db_meta not yet created (init_db hasn't run yet)
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


def save_model_version():
    """Persists the current model name into db_meta. Call after /reset."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('embedding_model', ?)",
        (EMBEDDING_MODEL_NAME,),
    )
    conn.commit()
    conn.close()


async def _call_ollama(model: str, payload: dict) -> dict | None:
    """Single Ollama call with up to 3 retries on timeout (exponential backoff)."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(OLLAMA_URL, json=payload)
                if response.status_code == 200:
                    return json.loads(response.json().get("response", "{}"))
                logger.warning(f"Ollama {model} returned HTTP {response.status_code}")
                return None
        except httpx.TimeoutException:
            wait = 2**attempt
            logger.warning(
                f"Ollama {model} timeout (attempt {attempt + 1}/3). Retrying in {wait}s…"
            )
            if attempt < 2:
                await asyncio.sleep(wait)
        except json.JSONDecodeError as exc:
            logger.warning(f"Ollama {model} returned invalid JSON: {exc}")
            return None
        except Exception as exc:
            logger.error(f"Ollama {model} unexpected error: {exc}")
            return None
    return None


async def extract_ai_metadata(text_sample: str, filename: str = "") -> dict:
    """
    Calls Ollama (llama3 → phi3 fallback) under a global asyncio lock.
    Rule-based tags are used as fallback AND to clean up weak LLM output.
    """
    # Pre-compute rule-based tags so we can use them as fallback immediately
    rb_tags = _rule_based_tags(filename, text_sample)

    prompt = f"""You are an expert academic document librarian. Analyze the document excerpt below.

FILENAME: {filename or "unknown"}

YOUR TASK — return ONLY a single valid JSON object, no markdown, no preamble, no explanation.

TAG RULES (critical):
- Generate exactly 4-6 tags
- NEVER use: "Uncategorized", "General", "Document", "Text", "Content", "Unknown", "Other", "N/A"
- Tags must be SPECIFIC and USEFUL for searching
- Use a mix of these categories:
  • Subject area: e.g. "Computer Science", "Biology", "Finance", "Psychology"
  • Document type: e.g. "Course Syllabus", "Lab Report", "Lecture Notes", "Question Bank"
  • Core topics: e.g. "Machine Learning", "Organic Chemistry", "Financial Markets"
  • Policies: e.g. "Attendance Policy", "Late Work Policy", "Group Projects"
  • Academic term: e.g. "Spring 2023", "Fall 2022"

SUMMARY RULE:
- Exactly ONE sentence, maximum 20 words
- Must say what the document IS, e.g. "Spring 2023 syllabus for CS 568 covering machine learning algorithms."

Return this exact JSON shape:
{{
  "summary": "One sentence, max 20 words.",
  "tags": ["Tag1", "Tag2", "Tag3", "Tag4"],
  "key_findings": ["Key policy or requirement 1", "Key policy or requirement 2", "Key policy or requirement 3"],
  "entities": {{
    "Companies": [],
    "Dates": [],
    "Project_Names": []
  }}
}}

Document excerpt:
{text_sample[:3500]}
"""
    base_payload = {"prompt": prompt, "format": "json", "stream": False}

    # Acquire lock with a 5-minute deadline to prevent indefinite queuing
    try:
        await asyncio.wait_for(ollama_lock.acquire(), timeout=300.0)
    except asyncio.TimeoutError:
        logger.warning("Timed out waiting for Ollama lock — using rule-based tags.")
        return {**_DEFAULT_METADATA, "tags": rb_tags, "summary": ""}

    result = None
    try:
        for model in [_PRIMARY_MODEL] + _FALLBACK_MODELS:
            result = await _call_ollama(model, {**base_payload, "model": model})
            if result and isinstance(result, dict) and "summary" in result:
                break
            logger.warning(f"Model {model} returned unusable result, trying next…")
    finally:
        ollama_lock.release()

    rb_summary = _rule_based_summary(filename, text_sample)

    if not result or not isinstance(result, dict):
        return {**_DEFAULT_METADATA, "tags": rb_tags, "summary": rb_summary}

    # Sanitise tags — strip junk, supplement with rule-based if needed
    result["tags"] = _clean_llm_tags(result.get("tags", []), filename, text_sample)

    # If LLM returned a bad/empty summary, substitute rule-based one
    llm_summary = (result.get("summary") or "").strip()
    if not llm_summary or llm_summary.lower().startswith("ai summary"):
        result["summary"] = rb_summary

    return result
