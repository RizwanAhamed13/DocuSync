import os
import pytest
import tempfile
import shutil
from fastapi.testclient import TestClient
from app import config, db
from app.main import app as quad_app
from app.auth.service import create_user
from app.health.analyzer import analyze_code_health

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

def create_mock_app_source(app_name: str, files: dict) -> str:
    """Create project files under projects_source/app_name."""
    path = os.path.join("projects_source", app_name)
    os.makedirs(path, exist_ok=True)
    
    for rel_path, content in fill_nested_dict_files(files).items():
        full_path = os.path.join(path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    return path

def fill_nested_dict_files(d: dict, prefix="") -> dict:
    flat = {}
    for k, v in d.items():
        p = os.path.join(prefix, k) if prefix else k
        if isinstance(v, dict):
            flat.update(fill_nested_dict_files(v, p))
        else:
            flat[p] = v
    return flat

# ==================== UNIT TESTS ====================

def test_code_health_analyzer():
    # Mock files
    files = {
        "main.py": """
import logging
# TODO: implement this
api_key = "mysecret12345"
def check_values(x):
    try:
        if x > 10:
            print("high")
        else:
            print("low")
    except Exception:
        pass
""",
        "index.js": """
// TODO: optimize code
console.log("Starting index...");
function run() {
    try {
        doSomething();
    } catch(e) {}
}
"""
    }
    
    app_name = "test-app-health"
    path = create_mock_app_source(app_name, files)
    
    try:
        report = analyze_code_health(app_name)
        assert report["app_name"] == app_name
        assert report["overall_score"] < 100
        
        # Verify file details
        files_dict = {f["file_path"]: f for f in report["file_reports"]}
        
        # main.py checks
        assert "main.py" in files_dict
        main_rep = files_dict["main.py"]
        assert main_rep["issues_count"] >= 2 # secret, todo, bare except
        
        # index.js checks
        assert "index.js" in files_dict
        js_rep = files_dict["index.js"]
        assert js_rep["issues_count"] >= 3 # todo, console.log, empty catch
        
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)

# ==================== API TESTS ====================

def test_health_endpoints_api():
    client = TestClient(quad_app)
    
    # Create user
    create_user("alice", "a@test.com", "password123")
    login_resp = client.post("/auth/login", json={"username_or_email": "alice", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Mock app source
    app_name = "health-api-app"
    files = {
        "main.py": "print('Hello World')"
    }
    path = create_mock_app_source(app_name, files)
    
    try:
        # POST Check
        resp = client.post(f"/health-check/{app_name}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["overall_score"] == 100
        assert resp.json()["grade"] == "A"
        
        # GET Check
        resp = client.get(f"/health-check/{app_name}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["grade"] == "A"
        
        # GET History
        resp = client.get(f"/health-check/{app_name}/history", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        
        # GET Badge
        resp = client.get(f"/health-check/{app_name}/badge")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        assert "A" in resp.text
        
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)
