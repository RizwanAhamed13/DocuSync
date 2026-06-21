import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth.dependencies import get_current_user
from app.db import get_connection
from app.repository import get_app

router = APIRouter(prefix="/devlog", tags=["devlog"])


class DevlogCreate(BaseModel):
    title: str
    content: str
    published: bool = True


class DevlogUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    published: bool | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_owner(app_name: str, current_user: dict):
    app = get_app(app_name)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    if app.owner != current_user["sub"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the project owner")
    return app


@router.get("/{app_name}")
def list_devlogs(app_name: str):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM devlogs WHERE app_name = ? AND published = 1 ORDER BY created_at DESC",
            (app_name,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@router.post("/{app_name}", status_code=status.HTTP_201_CREATED)
def create_devlog(app_name: str, payload: DevlogCreate, current_user: dict = Depends(get_current_user)):
    _require_owner(app_name, current_user)
    if not payload.title.strip() or not payload.content.strip():
        raise HTTPException(status_code=400, detail="Title and content are required")
    conn = get_connection()
    try:
        log_id = "log_" + uuid.uuid4().hex[:12]
        now = _now()
        conn.execute(
            """
            INSERT INTO devlogs (log_id, app_name, author, title, content, published, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (log_id, app_name, current_user["sub"], payload.title, payload.content,
             1 if payload.published else 0, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM devlogs WHERE log_id = ?", (log_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/{app_name}/{log_id}")
def update_devlog(app_name: str, log_id: str, payload: DevlogUpdate, current_user: dict = Depends(get_current_user)):
    _require_owner(app_name, current_user)
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM devlogs WHERE log_id = ? AND app_name = ?", (log_id, app_name)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Devlog entry not found")
        fields, params = [], []
        if payload.title is not None:
            fields.append("title = ?"); params.append(payload.title)
        if payload.content is not None:
            fields.append("content = ?"); params.append(payload.content)
        if payload.published is not None:
            fields.append("published = ?"); params.append(1 if payload.published else 0)
        if fields:
            fields.append("updated_at = ?"); params.append(_now())
            params.extend([log_id, app_name])
            conn.execute(
                f"UPDATE devlogs SET {', '.join(fields)} WHERE log_id = ? AND app_name = ?",
                params,
            )
            conn.commit()
        row = conn.execute("SELECT * FROM devlogs WHERE log_id = ?", (log_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/{app_name}/{log_id}")
def delete_devlog(app_name: str, log_id: str, current_user: dict = Depends(get_current_user)):
    _require_owner(app_name, current_user)
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM devlogs WHERE log_id = ? AND app_name = ?", (log_id, app_name)
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Devlog entry not found")
        return {"deleted": True, "log_id": log_id}
    finally:
        conn.close()
