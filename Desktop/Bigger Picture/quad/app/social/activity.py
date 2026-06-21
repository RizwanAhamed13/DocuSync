import json
import datetime
from app.db import get_connection

def emit_event(username: str, event_type: str, target_type: str = None, target_name: str = None, metadata: dict = None):
    conn = get_connection()
    try:
        meta_str = json.dumps(metadata) if metadata else None
        now = datetime.datetime.now(datetime.UTC).isoformat()
        conn.execute(
            """
            INSERT INTO activity_events (username, event_type, target_type, target_name, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, event_type, target_type, target_name, meta_str, now)
        )
        conn.commit()
    except Exception as e:
        print(f"Error emitting activity event: {e}")
    finally:
        conn.close()

def get_activity_feed(limit: int = 50, offset: int = 0):
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, username, event_type, target_type, target_name, metadata, created_at
            FROM activity_events
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            meta = None
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"])
                except Exception:
                    meta = r["metadata"]
            result.append({
                "id": r["id"],
                "username": r["username"],
                "event_type": r["event_type"],
                "target_type": r["target_type"],
                "target_name": r["target_name"],
                "metadata": meta,
                "created_at": r["created_at"]
            })
        return result
    finally:
        conn.close()
