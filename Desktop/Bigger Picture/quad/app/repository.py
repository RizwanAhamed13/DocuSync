from datetime import datetime, timezone
import sqlite3
from typing import List, Optional
from .db import get_connection
from .models import App

def create_app(name: str, stack: Optional[str] = None, owner: Optional[str] = None) -> App:
    conn = get_connection()
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO apps (name, stack, status, created_at, owner)
            VALUES (?, ?, 'STOPPED', ?, ?)
            """,
            (name, stack, created_at, owner)
        )
        conn.commit()
        app_id = cursor.lastrowid
        cursor.execute("SELECT * FROM apps WHERE id = ?", (app_id,))
        row = cursor.fetchone()
        return App.model_validate(dict(row))
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e) or "name" in str(e):
            raise ValueError(f"App with name '{name}' already exists.")
        raise e
    finally:
        conn.close()

def get_app(name: str) -> Optional[App]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM apps WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return App.model_validate(dict(row))
        return None
    finally:
        conn.close()

def list_apps() -> List[App]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM apps")
        rows = cursor.fetchall()
        return [App.model_validate(dict(row)) for row in rows]
    finally:
        conn.close()

def update_status(
    name: str,
    status: str,
    container_id: Optional[str] = None,
    image_tag: Optional[str] = None,
    internal_port: Optional[int] = None,
    pid: Optional[int] = None,
    process_port: Optional[int] = None
) -> App:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM apps WHERE name = ?", (name,))
        if not cursor.fetchone():
            raise ValueError(f"App with name '{name}' not found.")

        cursor.execute(
            """
            UPDATE apps
            SET status = ?, container_id = ?, image_tag = ?, internal_port = ?,
                pid = ?, process_port = ?
            WHERE name = ?
            """,
            (status, container_id, image_tag, internal_port, pid, process_port, name)
        )
        conn.commit()

        cursor.execute("SELECT * FROM apps WHERE name = ?", (name,))
        row = cursor.fetchone()
        return App.model_validate(dict(row))
    finally:
        conn.close()

def set_approval_status(name: str, approval_status: str) -> Optional[App]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM apps WHERE name = ?", (name,))
        if not cursor.fetchone():
            return None
        cursor.execute(
            "UPDATE apps SET approval_status = ? WHERE name = ?",
            (approval_status, name)
        )
        conn.commit()
        cursor.execute("SELECT * FROM apps WHERE name = ?", (name,))
        return App.model_validate(dict(cursor.fetchone()))
    finally:
        conn.close()

def set_process_info(name: str, pid: Optional[int], process_port: Optional[int]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE apps SET pid = ?, process_port = ?, internal_port = ? WHERE name = ?",
            (pid, process_port, process_port, name)
        )
        conn.commit()
    finally:
        conn.close()

def touch_last_seen(name: str) -> App:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM apps WHERE name = ?", (name,))
        if not cursor.fetchone():
            raise ValueError(f"App with name '{name}' not found.")
        
        cursor.execute(
            "UPDATE apps SET last_seen = ? WHERE name = ?",
            (now, name)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM apps WHERE name = ?", (name,))
        row = cursor.fetchone()
        return App.model_validate(dict(row))
    finally:
        conn.close()

def delete_app(name: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM apps WHERE name = ?", (name,))
        if not cursor.fetchone():
            return False
        # Delete child records first to avoid FK constraint failures
        for table in ("ai_jobs", "tunnels", "devlog", "project_teams", "upvotes", "app_views"):
            try:
                cursor.execute(f"DELETE FROM {table} WHERE app_name = ?", (name,))
            except Exception:
                pass
        # forks table uses original_app and forked_app columns
        try:
            cursor.execute("DELETE FROM forks WHERE original_app = ? OR forked_app = ?", (name, name))
        except Exception:
            pass
        cursor.execute("DELETE FROM apps WHERE name = ?", (name,))
        conn.commit()
        return True
    finally:
        conn.close()
