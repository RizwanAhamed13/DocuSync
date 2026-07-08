"""
DocuSync — entry point.

Starts the FastAPI application, registers all route modules, and runs
startup checks (DB migration, model version check, OCR warm-up).

Start with:  uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import CORS_ALLOW_ORIGINS, OCR_WARMUP_ON_STARTUP
from core.db import init_db, get_db_connection
from services.embeddings import EMBEDDING_MODEL_NAME
from services.indexer import (
    check_model_version_match,
    classifier_needs_reindex,
    save_classifier_signature,
    _CLASSIFIER_SIGNATURE,
)
from services.ocr import warm_up_ocr

from routes import documents, tags, search, system


# ── Application lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema creation and migrations
    init_db()

    # Warn if the embedding model changed since last run
    if not check_model_version_match():
        print(
            f"\nWARNING: Embedding model changed to '{EMBEDDING_MODEL_NAME}'. "
            "Existing search results will be inaccurate until you POST /migrate-to-cosine "
            "or POST /reset. New uploads use the new model immediately.\n"
        )

    # Classifier signature check — warn if thresholds/model changed since last run
    if classifier_needs_reindex():
        print(
            f"\n⚠  Classifier config changed (now: {_CLASSIFIER_SIGNATURE}).\n"
            "   Existing classifications may be stale.\n"
            "   Run POST /retag-ai to re-classify all documents, or\n"
            "   POST /retag-ai?force=true to re-classify everything.\n"
        )
    else:
        save_classifier_signature()

    if OCR_WARMUP_ON_STARTUP:
        print("Pre-loading OCR engine…")
        await asyncio.to_thread(warm_up_ocr)
    else:
        print("Skipping OCR warm-up; OCR will load on first scanned document.")

    yield


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="DocuSync — Local Document Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route registration ────────────────────────────────────────────────────────

app.include_router(system.router)
app.include_router(documents.router)
app.include_router(tags.router)
app.include_router(search.router)

# ── SPA static files (served last so API routes take priority) ────────────────

os.makedirs("./static", exist_ok=True)

# Serve index.html with no-cache so browser always fetches the latest JS/CSS hashes
from fastapi.responses import FileResponse
from fastapi import Request

@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(request: Request, full_path: str):
    asset_path = os.path.join("./static", full_path)
    if full_path and os.path.isfile(asset_path):
        return FileResponse(asset_path)
    resp = FileResponse("./static/index.html", media_type="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp
