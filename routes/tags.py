"""
Tag and perspective routes — /tags and /tags/perspectives.

Tag hierarchy:
  Perspective (Subject) → Classification (Cancer Biology) → keyword tags (#mRNA, #p53)

The Tags page shows this hierarchy — sidebar classifications are the parent level,
keyword tags are the sub-level. A label that lives in the sidebar never appears as a tag.

Dimensions are discovered dynamically from the classifications JSON stored per document.
New dimensions added in indexer.py appear automatically in the sidebar without any
changes here.
"""
from __future__ import annotations
import json

from fastapi import APIRouter

from core.db import get_db_connection

router = APIRouter()

_MAX_TAGS_PER_CLS = 20

def _get_dim_meta() -> dict:
    conn = get_db_connection()
    try:
        dims = conn.execute("SELECT id, display_name, dim_order, ui_color, ui_dim_color, ui_icon, ui_chip_colors FROM taxonomy_dimensions").fetchall()
        meta = {}
        for d in dims:
            meta[d["id"]] = {
                "label": d["display_name"],
                "order": d["dim_order"],
                "color": d["ui_color"],
                "dimColor": d["ui_dim_color"],
                "icon": d["ui_icon"],
                "chipColors": json.loads(d["ui_chip_colors"]) if d["ui_chip_colors"] else []
            }
        return meta
    except Exception:
        return {}
    finally:
        conn.close()

def _dim_label(key: str, meta: dict) -> str:
    if key in meta:
        return meta[key]["label"]
    return key.replace("_", " ").title()

def _dim_order(key: str, meta: dict) -> int:
    return meta.get(key, {}).get("order", 99)

@router.get("/tags/config")
def get_tags_config():
    """
    Returns the dynamic taxonomy dimensions configuration to the frontend
    (colors, icons, display names, order).
    """
    return _get_dim_meta()


@router.get("/tags")
def list_tags():
    """
    Returns keyword tags in two shapes:

    hierarchy  — perspectives → classifications → tags
                 (drives the Tags page tree view)

    flat       — all unique keyword tags with counts, sorted by frequency
                 (used for tag-filter dropdowns and quick lookups)
    """
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT tags, classifications FROM documents WHERE status='completed'"
    ).fetchall()
    conn.close()

    # ── Build flat tag counts ─────────────────────────────────────────────────
    flat_counts: dict[str, int] = {}
    for r in rows:
        for tag in (json.loads(r["tags"]) if r["tags"] else []):
            flat_counts[tag] = flat_counts.get(tag, 0) + 1

    flat = sorted(
        [{"name": k, "count": v} for k, v in flat_counts.items()],
        key=lambda x: -x["count"],
    )

    # ── Discover all dimension keys across all documents ───────────────────────
    meta = _get_dim_meta()
    
    all_dim_keys: set[str] = set()
    for r in rows:
        cls = json.loads(r["classifications"]) if r["classifications"] else {}
        all_dim_keys.update(cls.keys())
    all_dims = sorted(all_dim_keys, key=lambda x: _dim_order(x, meta))

    # ── Build hierarchy: dim → classification → tag → count ──────────────────
    dim_cls_tag: dict[str, dict[str, dict[str, int]]] = {d: {} for d in all_dims}
    for r in rows:
        tags = json.loads(r["tags"]) if r["tags"] else []
        cls  = json.loads(r["classifications"]) if r["classifications"] else {}
        if not tags:
            continue
        for dim in all_dims:
            for cls_val in cls.get(dim, []):
                if cls_val not in dim_cls_tag[dim]:
                    dim_cls_tag[dim][cls_val] = {}
                for tag in tags:
                    dim_cls_tag[dim][cls_val][tag] = dim_cls_tag[dim][cls_val].get(tag, 0) + 1

    hierarchy = []
    for dim in all_dims:
        cls_map = dim_cls_tag[dim]
        if not cls_map:
            continue
        classifications = []
        for cls_name, tag_counts in sorted(cls_map.items(), key=lambda x: -sum(x[1].values())):
            top_tags = sorted(
                [{"name": k, "count": v} for k, v in tag_counts.items()],
                key=lambda x: -x["count"],
            )[:_MAX_TAGS_PER_CLS]
            if top_tags:
                classifications.append({"name": cls_name, "tags": top_tags})
        if classifications:
            hierarchy.append({
                "key":             dim,
                "label":           _dim_label(dim, meta),
                "classifications": classifications,
            })

    return {"hierarchy": hierarchy, "flat": flat}


@router.get("/tags/perspectives")
def get_perspectives():
    """
    Multi-perspective classification hierarchy for the library sidebar.
    Dimensions are discovered dynamically from stored document classifications —
    new upload dimensions appear automatically without any schema change.
    """
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT classifications FROM documents WHERE status='completed'"
    ).fetchall()
    conn.close()

    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        cls = json.loads(row["classifications"]) if row["classifications"] else {}
        for dim, vals in cls.items():
            if dim not in counts:
                counts[dim] = {}
            for val in (vals or []):
                if val:
                    counts[dim][val] = counts[dim].get(val, 0) + 1

    meta = _get_dim_meta()

    return [
        {
            "key":   dim,
            "label": _dim_label(dim, meta),
            "items": sorted(
                [{"name": k, "count": v} for k, v in counts[dim].items()],
                key=lambda x: -x["count"],
            ),
        }
        for dim in sorted(counts.keys(), key=lambda x: _dim_order(x, meta))
        if counts[dim]
    ]
