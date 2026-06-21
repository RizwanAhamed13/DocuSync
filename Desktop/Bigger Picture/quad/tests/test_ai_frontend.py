import os
import subprocess
import time
import tempfile
import socket
import json
import pytest
from playwright.sync_api import sync_playwright

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="module")
def servers():
    # Setup temporary database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    
    # Initialize the db
    init_cmd = f"DB_PATH={db_path} venv/bin/python -c 'from app.db import init_db; init_db()'"
    subprocess.run(init_cmd, shell=True, check=True)
    
    # Find free ports
    backend_port = get_free_port()
    frontend_port = get_free_port()
    
    # Start backend
    backend_env = os.environ.copy()
    backend_env["DB_PATH"] = db_path
    backend_proc = subprocess.Popen(
        ["venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)],
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Start frontend
    frontend_env = os.environ.copy()
    frontend_env["VITE_API_URL"] = f"http://127.0.0.1:{backend_port}"
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
        cwd="frontend",
        env=frontend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for servers to start
    time.sleep(5)
    
    yield f"http://127.0.0.1:{frontend_port}", f"http://127.0.0.1:{backend_port}"
    
    # Teardown
    backend_proc.terminate()
    frontend_proc.terminate()
    try:
        backend_proc.wait(timeout=5)
    except:
        backend_proc.kill()
    try:
        frontend_proc.wait(timeout=5)
    except:
        frontend_proc.kill()
        
    if os.path.exists(db_path):
        os.remove(db_path)

def test_ai_studio_frontend(servers):
    frontend_url, backend_url = servers
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Setup API mocking
        page.route("**/ai/status/myapp", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"indexed": True, "chunk_count": 42, "file_count": 5})
        ))
        
        page.route("**/ai/ingest/myapp", lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job_id": "ingest-job-1", "status": "QUEUED"})
        ))
        
        page.route("**/ai/jobs/ingest-job-1", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "job_id": "ingest-job-1",
                "status": "DONE",
                "job_type": "ingest",
                "result": {"files_indexed": 5, "chunks_indexed": 42, "duration_seconds": 1.2}
            })
        ))

        page.route("**/ai/chat/myapp", lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job_id": "chat-job-1"})
        ))

        page.route("**/ai/jobs/chat-job-1", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "job_id": "chat-job-1",
                "status": "DONE",
                "job_type": "chat",
                "result": {"answer": "Mock chat answer citation", "sources": [{"file_path": "main.py", "start_line": 1, "end_line": 10}]}
            })
        ))

        page.route("**/ai/review/myapp", lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job_id": "review-job-1"})
        ))

        page.route("**/ai/jobs/review-job-1", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "job_id": "review-job-1",
                "status": "DONE",
                "job_type": "pr_review",
                "result": {"summary": "Mock diff assessment summary", "issues": [{"severity": "high", "file": "main.py", "line": 5, "issue": "bug detection", "suggestion": "fix suggestion"}], "approved": True, "approval_reason": "Clean code"}
            })
        ))

        page.route("**/ai/docs/myapp", lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job_id": "docs-job-1"})
        ))

        page.route("**/ai/jobs/docs-job-1", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "job_id": "docs-job-1",
                "status": "DONE",
                "job_type": "auto_docs",
                "result": {"content": "# Mock Generated Documentation Details"}
            })
        ))

        page.route("**/ai/onboarding/myapp", lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job_id": "onboarding-job-1"})
        ))

        page.route("**/ai/jobs/onboarding-job-1", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "job_id": "onboarding-job-1",
                "status": "DONE",
                "job_type": "onboarding",
                "result": {"content": "# Onboarding Guide details"}
            })
        ))

        page.route("**/ai/diagram/myapp", lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"job_id": "diagram-job-1"})
        ))

        page.route("**/ai/jobs/diagram-job-1", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "job_id": "diagram-job-1",
                "status": "DONE",
                "job_type": "arch_diagram",
                "result": {"diagram": "```mermaid\ngraph TD\n  A --> B\n```"}
            })
        ))

        # 1. Register User
        page.goto(f"{frontend_url}/auth")
        page.click("text=Register")
        page.fill("input[placeholder='john-doe']", "aistudent")
        page.fill("input[placeholder='john@example.com']", "ai@student.edu")
        page.fill("input[placeholder='••••••••']", "AiPassword123")
        page.fill("input[placeholder='John Doe']", "AI User")
        page.click("button[type='submit']")
        
        # Wait for navigation to dashboard
        page.wait_for_url(f"{frontend_url}/dashboard")
        
        # 2. Navigate to AI Studio Page directly
        page.goto(f"{frontend_url}/ai/myapp")
        page.wait_for_url(f"{frontend_url}/ai/myapp")
        
        # Check Header
        page.wait_for_selector("text=AI Studio: myapp", timeout=5000)
        page.wait_for_selector("text=Indexed", timeout=5000)
        page.wait_for_selector("text=42 chunks", timeout=5000)
        
        # Check Chat Tab rendering
        page.wait_for_selector("text=Codebase Chat Assistant", timeout=5000)
        
        # Fill Chat message and submit
        page.fill("input[placeholder='Ask a question about the code...']", "Explain the project structure")
        page.press("input[placeholder='Ask a question about the code...']", "Enter")
        
        page.wait_for_selector("text=Mock chat answer citation", timeout=8000)
        assert "main.py" in page.content()
        
        # Switch to Review Diff tab
        page.click("text=Review Diff")
        page.wait_for_selector("text=Asynchronous Diff Code Review", timeout=5000)
        page.fill("textarea", "+++ b/main.py\n+print('hello')")
        page.click("text=Submit for Review")
        
        page.wait_for_selector("text=Mock diff assessment summary", timeout=8000)
        page.wait_for_selector("text=bug detection", timeout=5000)
        
        # Switch to Auto Docs tab
        page.click("text=Auto Docs")
        page.wait_for_selector("text=Auto-Documentation Generator", timeout=5000)
        page.click("text=Generate README")
        
        page.wait_for_selector("text=Mock Generated Documentation Details", timeout=8000)
        
        # Switch to Onboarding tab
        page.click("text=Onboarding")
        page.wait_for_selector("text=Onboarding Guide Generator", timeout=5000)
        page.fill("input[placeholder='Sarah Jenkins']", "Sarah")
        page.click("text=Generate Onboarding Guide")
        
        page.wait_for_selector("text=Onboarding Guide details", timeout=8000)
        
        # Switch to Architecture tab
        page.click("text=Architecture")
        page.wait_for_selector("text=Mermaid Architecture Diagram", timeout=5000)
        page.click("text=Generate Diagram")
        
        page.wait_for_selector("text=graph TD", timeout=8000)
        
        browser.close()
