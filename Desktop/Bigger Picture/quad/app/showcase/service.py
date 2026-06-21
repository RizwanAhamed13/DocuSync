import hashlib
import datetime
from app.db import get_connection
from app.repository import get_app

def record_view(app_name: str, viewer_ip: str) -> bool:
    ip_hash = hashlib.sha256(viewer_ip.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        # Check if app exists
        cursor = conn.execute("SELECT name FROM apps WHERE name = ?", (app_name,))
        if not cursor.fetchone():
            return False
            
        # Check if this IP hash has viewed this app
        cursor = conn.execute(
            "SELECT id FROM app_views WHERE app_name = ? AND viewer_ip = ?",
            (app_name, ip_hash)
        )
        if cursor.fetchone():
            return False
        
        now = datetime.datetime.now(datetime.UTC).isoformat()
        conn.execute(
            "INSERT INTO app_views (app_name, viewer_ip, viewed_at) VALUES (?, ?, ?)",
            (app_name, ip_hash, now)
        )
        conn.execute(
            "UPDATE apps SET view_count = view_count + 1 WHERE name = ?",
            (app_name,)
        )
        conn.commit()
        return True
    finally:
        conn.close()

def get_public_apps(query: str = None, tag: str = None, limit: int = 50, offset: int = 0):
    conn = get_connection()
    try:
        sql = """
            SELECT apps.*, 
                   EXISTS(
                       SELECT 1 FROM ai_jobs 
                       WHERE ai_jobs.app_name = apps.name 
                         AND ai_jobs.job_type = 'auto_docs' 
                         AND ai_jobs.status = 'DONE'
                   ) as has_docs
            FROM apps 
            WHERE visibility = 'public'
        """
        params = []
        if query:
            sql += " AND (name LIKE ? OR description LIKE ? OR tags LIKE ?)"
            q = f"%{query}%"
            params.extend([q, q, q])
        if tag:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_leaderboard(sort_by: str = "upvotes", limit: int = 10):
    conn = get_connection()
    try:
        order_col = "upvote_count" if sort_by == "upvotes" else "view_count"
        cursor = conn.execute(
            f"""
            SELECT apps.*, 
                   EXISTS(
                       SELECT 1 FROM ai_jobs 
                       WHERE ai_jobs.app_name = apps.name 
                         AND ai_jobs.job_type = 'auto_docs' 
                         AND ai_jobs.status = 'DONE'
                   ) as has_docs
            FROM apps 
            WHERE visibility = 'public' 
            ORDER BY {order_col} DESC, name ASC LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def update_app_metadata(app_name: str, username: str, visibility: str = None, description: str = None, tags: str = None, is_admin: bool = False):
    app = get_app(app_name)
    if not app:
        raise ValueError(f"App '{app_name}' not found.")
    if app.owner != username and not is_admin:
        raise PermissionError("Permission denied.")
        
    conn = get_connection()
    try:
        updates = []
        params = []
        if visibility is not None:
            if visibility not in ("public", "private"):
                raise ValueError("Visibility must be 'public' or 'private'.")
            updates.append("visibility = ?")
            params.append(visibility)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if tags is not None:
            updates.append("tags = ?")
            params.append(tags)
            
        if not updates:
            cursor = conn.execute("SELECT * FROM apps WHERE name = ?", (app_name,))
            return dict(cursor.fetchone())
            
        sql = f"UPDATE apps SET {', '.join(updates)} WHERE name = ?"
        params.append(app_name)
        conn.execute(sql, params)
        conn.commit()
        
        cursor = conn.execute("SELECT * FROM apps WHERE name = ?", (app_name,))
        return dict(cursor.fetchone())
    finally:
        conn.close()
