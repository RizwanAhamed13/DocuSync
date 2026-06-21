import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from app import config, db
from app.main import app

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

def test_api_endpoints():
    client = TestClient(app)
    
    # 1. GET /health returns {"status":"ok","db":"connected"}
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}
    
    # 2. POST /apps with {"name":"test"} returns the app with status STOPPED
    response = client.post("/apps", json={"name": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test"
    assert data["status"] == "STOPPED"
    assert data["id"] is not None
    
    # 3. POST /apps again with {"name":"test"} returns 409 with a structured error
    response = client.post("/apps", json={"name": "test"})
    assert response.status_code == 409
    error_data = response.json()
    assert "error" in error_data
    assert error_data["code"] == "DUPLICATE_APP_NAME"
    
    # 4. GET /apps lists the created app
    response = client.get("/apps")
    assert response.status_code == 200
    apps = response.json()
    assert len(apps) == 1
    assert apps[0]["name"] == "test"
