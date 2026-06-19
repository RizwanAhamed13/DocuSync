import logging
import os
import threading

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# GPU server: BGE-M3 (1024d, 8k context, 2.2 GB VRAM)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = 1024
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cuda")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

_embedding_model: SentenceTransformer | None = None
_embedding_lock = threading.Lock()
_chroma_client = None
_chroma_collection = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                logger.info(f"Loading embedding model {EMBEDDING_MODEL_NAME} on {EMBEDDING_DEVICE}…")
                _embedding_model = SentenceTransformer(
                    EMBEDDING_MODEL_NAME,
                    device=EMBEDDING_DEVICE,
                )
    return _embedding_model


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path="./vector_store")
    return _chroma_client


def get_chroma_collection():
    global _chroma_collection
    if _chroma_collection is None:
        client = get_chroma_client()
        _chroma_collection = client.get_or_create_collection(
            name="document_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        existing_space = (_chroma_collection.metadata or {}).get("hnsw:space", "l2")
        if existing_space != "cosine" and _chroma_collection.count() > 0:
            logger.warning(
                "ChromaDB collection uses L2 distance. "
                "Call POST /migrate-to-cosine or POST /reset."
            )
    return _chroma_collection


def reset_chroma_singleton():
    global _chroma_collection
    _chroma_collection = None
