import os
import json
import tempfile
import pytest
import datetime
from unittest.mock import patch, MagicMock

from app import config, db
from app.db import get_connection
from app.repository import create_app, get_app, update_status
from app.deploy import _deploy_pipeline, delete_deployment
from app.social.forks import fork_project
from app.reaper import auto_reindex_apps, cleanup_old_jobs

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

@patch("app.deploy.detect_stack")
def test_deploy_pipeline_sets_pending_approval(mock_detect, tmp_path):
    # New subprocess-based flow: pipeline extracts, detects stack, and waits for approval.
    mock_detect.return_value = {"stack": "python", "port": 8000, "confidence": "high"}

    # Create a fake project source dir
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hi')\n")

    create_app("testapp", owner="student1")
    update_status("testapp", "BUILDING")

    import asyncio
    asyncio.run(_deploy_pipeline("testapp", str(src)))

    # Status should be PENDING_APPROVAL and stack recorded
    app = get_app("testapp")
    assert app.status == "PENDING_APPROVAL"
    assert app.stack == "python"

    # Project files should be copied into projects/testapp
    assert os.path.exists(os.path.join("projects", "testapp", "main.py"))

    # Cleanup
    import shutil
    shutil.rmtree(os.path.join("projects", "testapp"), ignore_errors=True)


@patch("app.deploy._start_subprocess")
def test_approve_starts_subprocess(mock_start):
    from app.deploy import approve_deployment
    mock_start.return_value = {"pid": 12345, "port": 9000, "status": "RUNNING"}

    create_app("approveapp", owner="student1")
    update_status("approveapp", "PENDING_APPROVAL")
    # stack + project dir must exist
    conn = get_connection()
    try:
        conn.execute("UPDATE apps SET stack = 'python' WHERE name = 'approveapp'")
        conn.commit()
    finally:
        conn.close()
    os.makedirs(os.path.join("projects", "approveapp"), exist_ok=True)

    result = approve_deployment("approveapp", current_user={"sub": "admin", "role": "admin"})
    assert result["approval_status"] == "approved"
    assert result["status"] == "RUNNING"
    assert mock_start.call_count == 1

    app = get_app("approveapp")
    assert app.approval_status == "approved"

    import shutil
    shutil.rmtree(os.path.join("projects", "approveapp"), ignore_errors=True)

@patch("app.deploy.remove_container")
@patch("app.ai.ingest.VectorStore.delete_collection")
def test_delete_deployment_removes_index(mock_delete_col, mock_remove_container):
    create_app("deleteme", owner="student1")
    
    # Insert dummy code chunk
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO code_chunks (app_name, chunk_id, file_path, start_line, end_line, chunk_type, language, content, indexed_at)
            VALUES ('deleteme', 'chunk-1', 'main.py', 1, 10, 'file', 'python', 'print(1)', '2026-06-15 12:00:00')
        """)
        conn.commit()
    finally:
        conn.close()
        
    # Call delete
    delete_deployment("deleteme", current_user={"sub": "student1", "role": "student"})
    
    # Check app and code chunks deleted
    assert get_app("deleteme") is None
    
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM code_chunks WHERE app_name = ?", ("deleteme",))
        assert cursor.fetchone()[0] == 0
    finally:
        conn.close()
        
    mock_delete_col.assert_called_once_with("deleteme")

@patch("app.ai.job_queue.get_queue")
def test_reaper_auto_reindexes_running_unindexed_apps(mock_q, tmp_path):
    # Create a running app
    create_app("running-app", owner="student1")
    update_status("running-app", "RUNNING")
    
    # Create persistent folder so os.path.exists passes
    os.makedirs(os.path.join("projects_source", "running-app"), exist_ok=True)
    
    q_inst = MagicMock()
    mock_q.return_value = q_inst
    
    import asyncio
    asyncio.run(auto_reindex_apps())
    
    # Check that job was enqueued
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM ai_jobs WHERE app_name = ? AND job_type = 'ingest'", ("running-app",))
        assert cursor.fetchone()[0] == 1
    finally:
        conn.close()
        
    assert q_inst.enqueue.call_count == 1
    
    # Cleanup directory
    import shutil
    shutil.rmtree(os.path.join("projects_source", "running-app"), ignore_errors=True)

def test_reaper_cleans_up_old_jobs():
    conn = get_connection()
    try:
        # Create completed job 35 days ago
        dt_old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=35)).isoformat()
        dt_recent = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)).isoformat()
        
        conn.execute("""
            INSERT INTO ai_jobs (job_id, app_name, username, job_type, status, queued_at, completed_at, input)
            VALUES 
            ('old-job', 'myapp', 'user1', 'chat', 'DONE', ?, ?, '{}'),
            ('recent-job', 'myapp', 'user1', 'chat', 'DONE', ?, ?, '{}')
        """, (dt_old, dt_old, dt_recent, dt_recent))
        conn.commit()
    finally:
        conn.close()
        
    cleanup_old_jobs()
    
    # Verify old-job is deleted, recent-job remains
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT job_id FROM ai_jobs")
        job_ids = [r[0] for r in cursor.fetchall()]
        assert "old-job" not in job_ids
        assert "recent-job" in job_ids
    finally:
        conn.close()
