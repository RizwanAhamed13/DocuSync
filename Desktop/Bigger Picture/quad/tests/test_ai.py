import os
import json
import tempfile
import pytest
import hashlib
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app import config, db
from app.db import get_connection
from app.main import app as quad_app
from app.ai.ingest import walk_project, chunk_file, ingest_project, delete_project_index
from app.ai.worker import build_context_block, call_ollama, handle_deploy_doctor, handle_pr_review
from app.ai.job_queue import enqueue_job, get_job_status
from app.auth.dependencies import get_current_user

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

# Unit Tests - Ingest Walk & Chunk

def test_walk_project_skips_node_modules(tmp_path):
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "index.js").write_text("console.log('node')")
    (tmp_path / "main.js").write_text("console.log('main')")
    
    files = walk_project(str(tmp_path))
    assert not any("node_modules" in f["file_path"] for f in files)
    assert any("main.js" in f["file_path"] for f in files)

def test_walk_project_skips_binary(tmp_path):
    binary_file = tmp_path / "app.png"
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    
    files = walk_project(str(tmp_path))
    assert not any("app.png" in f["file_path"] for f in files)

def test_walk_project_skips_large_file(tmp_path):
    large_file = tmp_path / "large.txt"
    large_file.write_text("a" * 150_000)
    
    files = walk_project(str(tmp_path))
    assert not any("large.txt" in f["file_path"] for f in files)

def test_chunk_file_line_based(tmp_path):
    lines = [f"Line {i}" for i in range(150)]
    content = "\n".join(lines)
    
    chunks = chunk_file({
        "file_path": "readme.md",
        "language": "text",
        "content": content
    })
    
    assert len(chunks) > 1
    assert all(c["chunk_type"] == "file" for c in chunks)
    assert chunks[0]["start_line"] == 1

def test_chunk_file_python_functions(tmp_path):
    content = (
        "def func_one():\n"
        "    print('one')\n\n"
        "def func_two():\n"
        "    print('two')\n\n"
        "class MyClass:\n"
        "    def method(self):\n"
        "        pass\n"
    )
    
    chunks = chunk_file({
        "file_path": "main.py",
        "language": "python",
        "content": content
    })
    
    function_chunks = [c for c in chunks if c["chunk_type"] == "function"]
    class_chunks = [c for c in chunks if c["chunk_type"] == "class"]
    assert len(function_chunks) >= 2
    assert len(class_chunks) >= 1
    assert all(c["symbol_name"] is not None for c in function_chunks)

def test_chunk_overlap():
    lines = [f"Line {i}" for i in range(100)]
    content = "\n".join(lines)
    
    chunks = chunk_file({
        "file_path": "readme.md",
        "language": "text",
        "content": content
    })
    
    assert len(chunks) >= 2
    assert chunks[1]["start_line"] < chunks[0]["end_line"]

def test_build_context_block_truncates():
    chunks = []
    for i in range(20):
        chunks.append({
            "file_path": f"file_{i}.txt",
            "start_line": 1,
            "end_line": 10,
            "content": "a" * 400
        })
        
    result = build_context_block(chunks, max_tokens=1000)
    assert len(result) <= 1000 * 4 * 1.2
    assert "lines" in result

def test_build_context_block_always_one_chunk():
    large_chunk = {
        "file_path": "giant.txt",
        "start_line": 1,
        "end_line": 2000,
        "content": "a" * 15000
    }
    result = build_context_block([large_chunk], max_tokens=100)
    assert "giant.txt" in result

def test_cache_key_deterministic():
    input_1 = {"question": "how to deploy?", "history": []}
    input_2 = {"history": [], "question": "how to deploy?"}
    
    # Pre-populate database with a DONE job with a fixed cache_key
    serialized_input = json.dumps(input_1, sort_keys=True)
    hash_payload = f"chat:{serialized_input}".encode("utf-8")
    cache_key = hashlib.sha256(hash_payload).hexdigest()
    
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO ai_jobs (job_id, app_name, username, job_type, status, input, queued_at, completed_at, cache_key, result)
            VALUES ('cached-id-123', 'myapp', 'rizwan', 'chat', 'DONE', ?, '2026-06-15 12:00:00', '2026-06-15 12:01:00', ?, '{"answer": "yes"}')
        """, (serialized_input, cache_key))
        conn.commit()
    finally:
        conn.close()
        
    with patch("app.ai.job_queue.get_queue") as mock_q:
        mock_q.return_value = MagicMock()
        job_id_1 = enqueue_job("chat", "myapp", "rizwan", input_1)
        job_id_2 = enqueue_job("chat", "myapp", "rizwan", input_2)
        
        # Both should hit the cache and return the same job ID
        assert job_id_1 == "cached-id-123"
        assert job_id_2 == "cached-id-123"

def test_enqueue_job_cache_hit():
    serialized_input = json.dumps({"question": "test"}, sort_keys=True)
    hash_payload = f"chat:{serialized_input}".encode("utf-8")
    cache_key = hashlib.sha256(hash_payload).hexdigest()
    
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO ai_jobs (job_id, app_name, username, job_type, status, input, queued_at, completed_at, cache_key, result)
            VALUES ('cached-id', 'myapp', 'rizwan', 'chat', 'DONE', ?, '2026-06-15 12:00:00', '2026-06-15 12:01:00', ?, '{"answer": "cached answer"}')
        """, (serialized_input, cache_key))
        conn.commit()
    finally:
        conn.close()
        
    with patch("app.ai.job_queue.get_queue") as mock_q:
        q_inst = MagicMock()
        mock_q.return_value = q_inst
        
        job_id = enqueue_job("chat", "myapp", "rizwan", {"question": "test"})
        assert job_id == "cached-id"
        assert q_inst.enqueue.call_count == 0

def test_enqueue_job_cache_miss():
    with patch("app.ai.job_queue.get_queue") as mock_q:
        q_inst = MagicMock()
        mock_q.return_value = q_inst
        
        job_id = enqueue_job("chat", "myapp", "rizwan", {"question": "different"})
        assert job_id is not None
        assert q_inst.enqueue.call_count == 1

def test_get_job_status_not_found():
    assert get_job_status("nonexistent-uuid") is None

def test_get_job_status_parses_json():
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO ai_jobs (job_id, app_name, username, job_type, status, input, queued_at, result)
            VALUES ('job-1', 'myapp', 'rizwan', 'chat', 'DONE', '{"question": "hi"}', '2026-06-15 12:00:00', '{"answer": "hello"}')
        """)
        conn.commit()
    finally:
        conn.close()
        
    status = get_job_status("job-1")
    assert status is not None
    assert status["input"]["question"] == "hi"
    assert status["result"]["answer"] == "hello"

def test_call_ollama_connection_error(monkeypatch):
    import requests
    def mock_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")
    monkeypatch.setattr(requests, "post", mock_post)
    
    with pytest.raises(RuntimeError) as exc:
        call_ollama("hello prompt")
    assert "Ollama not reachable" in str(exc.value)

def test_deploy_doctor_parses_json(monkeypatch):
    def mock_call(*args, **kwargs):
        return '{"root_cause": "NPM error", "explanation": "missing package", "fix": "npm install", "confidence": "high"}'
    monkeypatch.setattr("app.ai.worker.call_ollama", mock_call)
    
    result = handle_deploy_doctor({
        "app_name": "myapp",
        "input": {"build_log": "npm ERR!", "stack": "node"}
    })
    assert result["root_cause"] == "NPM error"
    assert result["fix"] == "npm install"

def test_deploy_doctor_handles_bad_json(monkeypatch):
    def mock_call(*args, **kwargs):
        return "Not JSON output from model"
    monkeypatch.setattr("app.ai.worker.call_ollama", mock_call)
    
    result = handle_deploy_doctor({
        "app_name": "myapp",
        "input": {"build_log": "npm ERR!", "stack": "node"}
    })
    assert result["confidence"] == "low"
    assert "Not JSON output" in result["explanation"]

def test_pr_review_parses_json(monkeypatch):
    def mock_call(*args, **kwargs):
        return '{"summary": "Looks good", "issues": [{"severity": "high", "file": "main.py", "line": 5, "issue": "bug", "suggestion": "fix"}], "approved": true, "approval_reason": "Clean code"}'
    monkeypatch.setattr("app.ai.worker.call_ollama", mock_call)
    monkeypatch.setattr("app.ai.worker.retrieve_context", lambda *args, **kwargs: [])
    
    result = handle_pr_review({
        "app_name": "myapp",
        "input": {"diff": "+++ b/main.py\n+print('hello')"}
    })
    assert result["summary"] == "Looks good"
    assert len(result["issues"]) == 1
    assert result["approved"] is True

# API Tests

def test_ingest_requires_auth():
    client = TestClient(quad_app)
    # Mock get_current_user dependency directly to simulate unauthenticated
    async def mock_get_current_user():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    quad_app.dependency_overrides[get_current_user] = mock_get_current_user
    try:
        response = client.post("/ai/ingest/myapp", headers={})
        assert response.status_code == 401
    finally:
        quad_app.dependency_overrides.clear()

def test_ingest_returns_202():
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO apps (name, stack, status, created_at, owner)
            VALUES ('myapp', 'python', 'RUNNING', '2026-06-15 12:00:00', 'rizwan')
        """)
        conn.commit()
    finally:
        conn.close()
        
    client = TestClient(quad_app)
    with patch("app.ai.router.enqueue_job", return_value="mock-job-uuid"):
        response = client.post("/ai/ingest/myapp")
        assert response.status_code == 202
        assert response.json()["job_id"] == "mock-job-uuid"
        assert response.json()["status"] == "QUEUED"

def test_chat_no_index():
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO apps (name, stack, status, created_at, owner)
            VALUES ('myapp', 'python', 'RUNNING', '2026-06-15 12:00:00', 'rizwan')
        """)
        conn.commit()
    finally:
        conn.close()
        
    client = TestClient(quad_app)
    response = client.post("/ai/chat/myapp", json={"question": "what is this?"})
    assert response.status_code == 400
    assert "not indexed yet" in response.json()["detail"]

def test_chat_returns_202():
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO apps (name, stack, status, created_at, owner)
            VALUES ('myapp', 'python', 'RUNNING', '2026-06-15 12:00:00', 'rizwan')
        """)
        conn.execute("""
            INSERT INTO code_chunks (app_name, chunk_id, file_path, start_line, end_line, chunk_type, language, content, symbol_name, indexed_at)
            VALUES ('myapp', 'chunk-1', 'main.py', 1, 10, 'file', 'python', 'print(1)', NULL, '2026-06-15 12:00:00')
        """)
        conn.commit()
    finally:
        conn.close()
        
    client = TestClient(quad_app)
    with patch("app.ai.router.enqueue_job", return_value="chat-job-id"):
        response = client.post("/ai/chat/myapp", json={"question": "what is this?"})
        assert response.status_code == 202
        assert response.json()["job_id"] == "chat-job-id"

def test_get_job_status_api():
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO ai_jobs (job_id, app_name, username, job_type, status, input, queued_at, result)
            VALUES ('test-job-uuid', 'myapp', 'rizwan', 'chat', 'DONE', '{"question": "test"}', '2026-06-15 12:00:00', '{"answer": "yes"}')
        """)
        conn.commit()
    finally:
        conn.close()
        
    client = TestClient(quad_app)
    response = client.get("/ai/jobs/test-job-uuid")
    assert response.status_code == 200
    assert response.json()["job_id"] == "test-job-uuid"
    assert response.json()["result"]["answer"] == "yes"

def test_get_job_not_found():
    client = TestClient(quad_app)
    response = client.get("/ai/jobs/nonexistent-id")
    assert response.status_code == 404

def test_list_jobs_filtered():
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO ai_jobs (job_id, app_name, username, job_type, status, input, queued_at)
            VALUES 
            ('j-1', 'myapp', 'rizwan', 'chat', 'DONE', '{}', '2026-06-15 12:00:00'),
            ('j-2', 'myapp', 'rizwan', 'chat', 'QUEUED', '{}', '2026-06-15 12:01:00'),
            ('j-3', 'myapp', 'someone_else', 'chat', 'DONE', '{}', '2026-06-15 12:02:00')
        """)
        conn.commit()
    finally:
        conn.close()
        
    client = TestClient(quad_app)
    response = client.get("/ai/jobs")
    assert response.status_code == 200
    job_ids = [job["job_id"] for job in response.json()]
    assert "j-1" in job_ids
    assert "j-2" in job_ids
    assert "j-3" not in job_ids
