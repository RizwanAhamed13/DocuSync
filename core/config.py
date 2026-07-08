from __future__ import annotations
import os
from pathlib import Path

# ── Storage paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(os.getenv("DOCUSYNC_BASE_DIR", ".")).resolve()
UPLOAD_DIR = str(Path(os.getenv("DOCUSYNC_UPLOAD_DIR", BASE_DIR / "uploads")).resolve())
VECTOR_DIR = str(Path(os.getenv("DOCUSYNC_VECTOR_DIR", BASE_DIR / "vector_store")).resolve())
DB_PATH = str(Path(os.getenv("DOCUSYNC_DB_PATH", BASE_DIR / "document_metadata.db")).resolve())

Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(VECTOR_DIR).mkdir(parents=True, exist_ok=True)
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# ── Ingestion limits (overridable via env) ────────────────────────────────────
MAX_UPLOAD_BYTES   = int(os.getenv("MAX_UPLOAD_SIZE_MB",  "120"))  * 1024 * 1024
MAX_CHUNKS_PER_DOC = int(os.getenv("MAX_CHUNKS_PER_DOC", "2000"))
OCR_WARMUP_ON_STARTUP = os.getenv("OCR_WARMUP_ON_STARTUP", "true").lower() == "true"

# ── Allowed upload extensions ─────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".json"}

# ── Model stack ───────────────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "Alibaba-NLP/gte-large-en-v1.5")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL", "Alibaba-NLP/gte-reranker-modernbert-base")
SUMMARIZER_MODEL_NAME = os.getenv("SUMMARIZER_MODEL", "facebook/bart-large-cnn")
CLASSIFIER_MODEL_NAME = os.getenv(
    "CLASSIFIER_MODEL",
    "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli",
)

USE_OLLAMA_TAGGING = os.getenv("USE_OLLAMA_TAGGING", "false").lower() == "true"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")

# ── HTTP / frontend integration ───────────────────────────────────────────────
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "80"))
_origins = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
CORS_ALLOW_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()] or ["*"]
