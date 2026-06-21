import os
import shutil
import datetime
from app.db import get_connection
from app.repository import get_app, create_app, update_status
from app.social.activity import emit_event

def fork_project(original_app_name: str, forked_app_name: str, forked_by: str, background_tasks) -> None:
    # 1. Verify original_app exists
    original_app = get_app(original_app_name)
    if not original_app:
        raise ValueError(f"Original app '{original_app_name}' not found.")
        
    # 2. Check unique constraint for forks
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id FROM forks WHERE original_app = ? AND forked_by = ?",
            (original_app_name, forked_by)
        )
        if cursor.fetchone():
            raise ValueError("You have already forked this application.")
    finally:
        conn.close()
        
    # 3. Verify target name is unique
    if get_app(forked_app_name) is not None:
        raise ValueError(f"App name '{forked_app_name}' is already taken.")
        
    # 4. Copy source code directory
    original_dir = os.path.join("projects_source", original_app_name)
    forked_dir = os.path.join("projects_source", forked_app_name)
    
    if os.path.exists(original_dir):
        try:
            shutil.copytree(original_dir, forked_dir)
        except Exception as e:
            raise ValueError(f"Failed to copy project files: {e}")
    else:
        # Fallback if source files are missing
        try:
            os.makedirs(forked_dir, exist_ok=True)
            with open(os.path.join(forked_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(f"<h1>Fork of {original_app_name}</h1>\n")
        except Exception as e:
            raise ValueError(f"Failed to create fork directory: {e}")
            
    # Create app entry first so the forked_app foreign key exists
    create_app(forked_app_name, owner=forked_by)
    update_status(forked_app_name, "BUILDING")

    # 5. Insert into forks table
    conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        conn.execute(
            "INSERT INTO forks (original_app, forked_app, forked_by, forked_at) VALUES (?, ?, ?, ?)",
            (original_app_name, forked_app_name, forked_by, now)
        )
        conn.commit()
    except Exception as e:
        # cleanup directory and app
        if os.path.exists(forked_dir):
            shutil.rmtree(forked_dir)
        from app.repository import delete_app
        delete_app(forked_app_name)
        raise ValueError(f"Database error: {e}")
    finally:
        conn.close()
    
    # 6. Trigger deploy background tasks
    from app.deploy import _deploy_pipeline
    background_tasks.add_task(_deploy_pipeline, forked_app_name, forked_dir)
    
    # 7. Emit activity event
    emit_event(forked_by, "fork", "app", forked_app_name, {"original_app": original_app_name})

    # 8. Notify + badge the original owner
    if original_app.owner and original_app.owner != forked_by:
        try:
            from app.notifications.service import create_notification
            from app.badges.service import check_and_award
            create_notification(
                original_app.owner, "fork", "Project forked",
                f"{forked_by} forked your project {original_app_name}",
                f"/dev/{forked_app_name}",
            )
            check_and_award(original_app.owner, "project_forked")
        except Exception:
            pass
