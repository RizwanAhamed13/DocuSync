import os
import tempfile
import asyncio
import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from app import config, db, repository
from app.reaper import stop_idle_containers, sync_all_containers, reaper_loop
from app.container import ContainerError

@pytest.fixture(autouse=True)
def temp_db():
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    old_db_path = config.DB_PATH
    config.DB_PATH = temp_db_path
    
    db.init_db()
    
    yield
    
    config.DB_PATH = old_db_path
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)

def test_reaper_stops_idle_app():
    async def run_test():
        last_seen = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO apps (name, stack, status, created_at, last_seen) VALUES ('idle-app', 'node', 'RUNNING', 'now', ?)",
                (last_seen,)
            )
            conn.commit()
        finally:
            conn.close()

        with patch("app.reaper.stop_container") as mock_stop:
            reaped = await stop_idle_containers()
            mock_stop.assert_called_once_with("idle-app")
            assert reaped == ["idle-app"]

    asyncio.run(run_test())

def test_reaper_skips_recent_app():
    async def run_test():
        last_seen = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO apps (name, stack, status, created_at, last_seen) VALUES ('recent-app', 'node', 'RUNNING', 'now', ?)",
                (last_seen,)
            )
            conn.commit()
        finally:
            conn.close()

        with patch("app.reaper.stop_container") as mock_stop:
            reaped = await stop_idle_containers()
            mock_stop.assert_not_called()
            assert reaped == []

    asyncio.run(run_test())

def test_reaper_skips_static():
    async def run_test():
        last_seen = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO apps (name, stack, status, created_at, last_seen) VALUES ('static-app', 'static', 'RUNNING', 'now', ?)",
                (last_seen,)
            )
            conn.commit()
        finally:
            conn.close()

        with patch("app.reaper.stop_container") as mock_stop:
            reaped = await stop_idle_containers()
            mock_stop.assert_not_called()
            assert reaped == []

    asyncio.run(run_test())

def test_reaper_skips_stopped():
    async def run_test():
        last_seen = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO apps (name, stack, status, created_at, last_seen) VALUES ('stopped-app', 'node', 'STOPPED', 'now', ?)",
                (last_seen,)
            )
            conn.commit()
        finally:
            conn.close()

        with patch("app.reaper.stop_container") as mock_stop:
            reaped = await stop_idle_containers()
            mock_stop.assert_not_called()
            assert reaped == []

    asyncio.run(run_test())

def test_reaper_handles_stop_error():
    async def run_test():
        last_seen = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO apps (name, stack, status, created_at, last_seen) VALUES ('error-app', 'node', 'RUNNING', 'now', ?)",
                (last_seen,)
            )
            conn.commit()
        finally:
            conn.close()

        with patch("app.reaper.stop_container", side_effect=ContainerError("docker stop error")):
            reaped = await stop_idle_containers()
            assert reaped == []

    asyncio.run(run_test())

def test_reaper_loop_runs_and_cancels():
    async def run_test():
        with patch("app.reaper.REAPER_INTERVAL_SECONDS", 0.05):
            with patch("app.reaper.sync_all_containers") as mock_sync:
                with patch("app.reaper.stop_idle_containers") as mock_stop_idle:
                    task = asyncio.create_task(reaper_loop())
                    await asyncio.sleep(0.1)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    assert mock_sync.call_count >= 1
                    assert mock_stop_idle.call_count >= 1

    asyncio.run(run_test())
