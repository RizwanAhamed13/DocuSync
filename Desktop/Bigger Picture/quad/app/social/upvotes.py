import datetime
from app.db import get_connection
from app.social.activity import emit_event

def upvote_app(username: str, app_name: str) -> None:
    conn = get_connection()
    try:
        # Check if app exists
        cursor = conn.execute("SELECT name FROM apps WHERE name = ?", (app_name,))
        if not cursor.fetchone():
            raise ValueError(f"App '{app_name}' not found.")
            
        now = datetime.datetime.now(datetime.UTC).isoformat()
        conn.execute(
            "INSERT INTO upvotes (app_name, username, created_at) VALUES (?, ?, ?)",
            (app_name, username, now)
        )
        conn.execute(
            "UPDATE apps SET upvote_count = upvote_count + 1 WHERE name = ?",
            (app_name,)
        )
        conn.commit()
        emit_event(username, "upvote", "app", app_name)
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError("You have already upvoted this application.")
        raise ValueError(str(e))
    finally:
        conn.close()

def unupvote_app(username: str, app_name: str) -> None:
    conn = get_connection()
    try:
        # Check if app exists
        cursor = conn.execute("SELECT name FROM apps WHERE name = ?", (app_name,))
        if not cursor.fetchone():
            raise ValueError(f"App '{app_name}' not found.")
            
        cursor = conn.execute(
            "SELECT id FROM upvotes WHERE app_name = ? AND username = ?",
            (app_name, username)
        )
        if not cursor.fetchone():
            raise ValueError("You have not upvoted this application.")
            
        conn.execute(
            "DELETE FROM upvotes WHERE app_name = ? AND username = ?",
            (app_name, username)
        )
        conn.execute(
            "UPDATE apps SET upvote_count = MAX(0, upvote_count - 1) WHERE name = ?",
            (app_name,)
        )
        conn.commit()
        emit_event(username, "unupvote", "app", app_name)
    finally:
        conn.close()

def has_upvoted(username: str, app_name: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id FROM upvotes WHERE app_name = ? AND username = ?",
            (app_name, username)
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()
