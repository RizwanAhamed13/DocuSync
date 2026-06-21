import uuid
from datetime import datetime, timezone
from typing import Optional
from app.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_notification(
    username: str,
    type: str,
    title: str,
    body: str,
    link: Optional[str] = None,
    conn=None,
) -> dict:
    """Insert a notification for a user. Safe to call from any endpoint."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    notification_id = "ntf_" + uuid.uuid4().hex[:12]
    now = _now()
    try:
        conn.execute(
            """
            INSERT INTO notifications
            (notification_id, username, type, title, body, link, read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (notification_id, username, type, title, body, link, now),
        )
        if own_conn:
            conn.commit()
            
        try:
            import asyncio
            from app.notifications.ws_manager import manager
            payload = {
                "notification_id": notification_id,
                "username": username,
                "type": type,
                "title": title,
                "body": body,
                "link": link,
                "read": 0,
                "created_at": now,
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(manager.send_personal_message({"type": "notification", "data": payload}, username))
            except RuntimeError:
                pass
        except Exception:
            pass
    except Exception:
        # Never let notification failures break the calling endpoint
        if own_conn:
            conn.close()
        return {}
    finally:
        if own_conn:
            conn.close()
    return {
        "notification_id": notification_id,
        "username": username,
        "type": type,
        "title": title,
        "body": body,
        "link": link,
        "read": 0,
        "created_at": now,
    }
