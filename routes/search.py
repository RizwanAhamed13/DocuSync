"""
Search route — /search (hybrid BM25 + vector + cross-encoder reranking).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from services.search import hybrid_search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


@router.post("/search")
def search_documents(request: SearchRequest):
    """Hybrid semantic + keyword search across all indexed documents."""
    if not request.query.strip():
        return []
    return hybrid_search(request.query, limit=request.limit)
