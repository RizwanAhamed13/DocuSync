import asyncio
import logging
import time
from datetime import datetime, timezone
from app.repository import list_apps
from app.container import stop_container, sync_container_status, ContainerError

IDLE_TIMEOUT_SECONDS = 300        # 5 minutes
REAPER_INTERVAL_SECONDS = 60      # check every 60s
EXEMPT_STACKS = {"static"}        # static apps cost 0 RAM, never sleep

logger = logging.getLogger("reaper")

async def reaper_loop() -> None:
    """
    Runs forever as an asyncio background task.
    Every REAPER_INTERVAL_SECONDS:
      1. Call sync_all_containers()
      2. Call stop_idle_containers()
      3. Call auto_reindex_apps()
      4. Call cleanup_old_jobs()
    Catches and logs all exceptions so a single error never kills the loop.
    """
    while True:
        try:
            await sync_all_containers()
        except Exception as e:
            logger.error(f"Error in sync_all_containers: {e}", exc_info=True)
            
        try:
            await stop_idle_containers()
        except Exception as e:
            logger.error(f"Error in stop_idle_containers: {e}", exc_info=True)
            
        try:
            from app.tunnel_repo import cleanup_stale_tunnels
            stale = cleanup_stale_tunnels(older_than_seconds=300)
            for tunnel_id in stale:
                logger.info(f"Closed stale tunnel: {tunnel_id} (no ping for 5 min)")
        except Exception as e:
            logger.error(f"Error in cleanup_stale_tunnels: {e}", exc_info=True)

        try:
            await auto_reindex_apps()
        except Exception as e:
            logger.error(f"Error in auto_reindex_apps: {e}", exc_info=True)

        try:
            cleanup_old_jobs()
        except Exception as e:
            logger.error(f"Error in cleanup_old_jobs: {e}", exc_info=True)
            
        try:
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break

async def auto_reindex_apps() -> None:
    from app.db import get_connection
    from app.ai.job_queue import enqueue_job
    import os
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, owner FROM apps 
            WHERE status = 'RUNNING' 
              AND name NOT IN (SELECT DISTINCT app_name FROM code_chunks)
        """)
        unindexed = cursor.fetchall()
    except Exception as e:
        logger.error(f"Database error in auto_reindex_apps: {e}")
        return
    finally:
        conn.close()
        
    for name, owner in unindexed:
        project_path = f"projects_source/{name}"
        if not os.path.exists(project_path):
            project_path = f"projects/{name}"
        if os.path.exists(project_path):
            try:
                enqueue_job("ingest", name, owner or "unknown", {"project_path": project_path})
                logger.info(f"Auto-queued ingestion for running, unindexed app: {name}")
            except Exception as e:
                logger.error(f"Failed to auto-queue ingestion for {name}: {e}")

def cleanup_old_jobs() -> None:
    from app.db import get_connection
    conn = get_connection()
    try:
        import datetime
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        conn.execute("DELETE FROM ai_jobs WHERE completed_at < ? AND (status = 'DONE' OR status = 'FAILED')", (cutoff,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error cleaning up old jobs: {e}", exc_info=True)
    finally:
        conn.close()

async def stop_idle_containers() -> list[str]:
    """
    Query SQLite for all apps with status=RUNNING.
    For each:
      - If stack in EXEMPT_STACKS: skip.
      - If last_seen is None or now - last_seen > IDLE_TIMEOUT_SECONDS:
          call stop_container(app_name)
          log: "Reaped idle container: <app_name> (idle Xs)"
    Return list of app_names that were stopped.
    """
    reaped = []
    apps = list_apps()
    now = datetime.now(timezone.utc)
    
    for app in apps:
        if app.status != "RUNNING":
            continue
        if app.stack in EXEMPT_STACKS:
            continue
            
        should_reap = False
        idle_seconds = 0
        
        if app.last_seen is None:
            should_reap = True
        else:
            try:
                last_seen_dt = datetime.fromisoformat(app.last_seen)
                if last_seen_dt.tzinfo is None:
                    last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
                idle_seconds = (now - last_seen_dt).total_seconds()
                if idle_seconds > IDLE_TIMEOUT_SECONDS:
                    should_reap = True
            except Exception:
                # If timestamp parsing fails, reap it to be safe
                should_reap = True
                
        if should_reap:
            try:
                loop = asyncio.get_event_loop()
                # Subprocess-managed apps use deploy.stop_subprocess, not Docker stop_container
                from app.deploy import pid_alive, stop_app
                if app.pid and pid_alive(app.pid):
                    await loop.run_in_executor(None, stop_app, app.name)
                else:
                    await loop.run_in_executor(None, stop_container, app.name)
                logger.info(f"Reaped idle app: {app.name} (idle {int(idle_seconds)}s)")
                reaped.append(app.name)
            except Exception as e:
                logger.error(f"Failed to reap app '{app.name}': {e}")
                
    return reaped

async def sync_all_containers() -> None:
    """
    Call sync_container_status(app_name) for every app in SQLite.
    This catches containers that crashed or were stopped externally.
    Run each sync in a thread executor (blocking Docker call).
    Log any sync errors but do not raise.
    """
    apps = list_apps()
    loop = asyncio.get_event_loop()
    for app in apps:
        try:
            await loop.run_in_executor(None, sync_container_status, app.name)
        except Exception as e:
            logger.error(f"Failed to sync container status for app '{app.name}': {e}")
