import os
import subprocess
import time
import tempfile
import socket
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

def test_frontend_smoke(servers):
    frontend_url, backend_url = servers
    
    with sync_playwright() as p:
        # Launch browser in headless mode
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Log console, page errors, and responses
        page.on("console", lambda msg: print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"BROWSER ERROR: {err}"))
        page.on("requestfailed", lambda req: print(f"BROWSER REQUEST FAILED: {req.method} {req.url} - {req.failure}"))
        page.on("response", lambda resp: print(f"HTTP RESPONSE: {resp.status} {resp.url}"))
        
        # 1. Landing Page
        page.goto(frontend_url)
        assert "QUAD" in page.content() or "Quad" in page.content()
        
        # Click on Get Started to go to /auth
        page.click("text=Get Started")
        page.wait_for_url(f"{frontend_url}/auth")
        
        # 2. Auth Page - Toggle to Register
        page.click("text=Register")
        
        # Fill in Registration form
        page.fill("input[placeholder='john-doe']", "e2estudent")
        page.fill("input[placeholder='john@example.com']", "e2e@student.edu")
        page.fill("input[placeholder='••••••••']", "E2ePassword123")
        page.fill("input[placeholder='John Doe']", "E2E Student")
        page.fill("input[placeholder='Engineering College']", "E2E University")
        page.fill("input[placeholder='Computer Science']", "ECE")
        page.fill("input[placeholder='3']", "4")
        
        # Submit form
        page.click("button[type='submit']")
        
        # Wait for navigation to /dashboard or print debug info if it fails
        try:
            page.wait_for_url(f"{frontend_url}/dashboard", timeout=5000)
        except Exception as e:
            print("\n--- Timeout / Navigation Failure Debug ---")
            print(f"Current URL: {page.url}")
            print(f"Page content snippet:\n{page.content()[:2000]}")
            raise e
            
        # Add a small wait to let the page render dashboard contents
        time.sleep(2)
        
        assert "Dashboard" in page.content() or "Logout" in page.content()
        
        # 3. Verify page links / sub-routing
        # Profile page
        page.goto(f"{frontend_url}/profile")
        page.wait_for_url(f"{frontend_url}/profile")
        time.sleep(2)  # Wait for API data load
        assert "Profile" in page.content() or "Bio" in page.content() or "e2estudent" in page.content()
        
        # Showcase page
        page.goto(f"{frontend_url}/showcase")
        page.wait_for_url(f"{frontend_url}/showcase")
        time.sleep(2)  # Wait for API data load
        assert "Showcase" in page.content() or "Projects" in page.content()
        
        # Leaderboard page
        page.goto(f"{frontend_url}/leaderboard")
        page.wait_for_url(f"{frontend_url}/leaderboard")
        time.sleep(2)  # Wait for API data load
        assert "Leaderboard" in page.content() or "Rank" in page.content()
        
        # DSA Tracker page
        page.goto(f"{frontend_url}/dsa")
        page.wait_for_url(f"{frontend_url}/dsa")
        time.sleep(2)  # Wait for API data load
        assert "DSA" in page.content() or "Submissions" in page.content()
        
        browser.close()
