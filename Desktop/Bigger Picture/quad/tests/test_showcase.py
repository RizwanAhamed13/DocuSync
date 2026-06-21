import os
import pytest
import tempfile
from fastapi.testclient import TestClient

from app import config, db, repository
from app.main import app as quad_app
from app.auth.service import create_user
from app.showcase.service import record_view, get_public_apps, get_leaderboard, update_app_metadata

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

# ==================== UNIT TESTS ====================

def test_showcase_views_unit():
    create_user("owner", "o@test.com", "password123")
    repository.create_app("app1", "static", "owner")
    
    # Check initial view_count
    app = repository.get_app("app1")
    assert app.view_count == 0
    
    # Record view
    assert record_view("app1", "192.168.1.1") is True
    app = repository.get_app("app1")
    assert app.view_count == 1
    
    # Duplicate view from same IP returns False
    assert record_view("app1", "192.168.1.1") is False
    app = repository.get_app("app1")
    assert app.view_count == 1
    
    # View from new IP increments
    assert record_view("app1", "192.168.1.2") is True
    app = repository.get_app("app1")
    assert app.view_count == 2

def test_showcase_query_unit():
    create_user("owner", "o@test.com", "password123")
    repository.create_app("app1", "static", "owner")
    repository.create_app("app2", "node", "owner")
    repository.create_app("app3", "python", "owner")
    
    update_app_metadata("app1", "owner", visibility="public", description="A super cool frontend app", tags="frontend,js")
    update_app_metadata("app2", "owner", visibility="public", description="A backend database app", tags="backend,database")
    update_app_metadata("app3", "owner", visibility="private", description="Top secret project", tags="secret")
    
    # list public apps
    public_apps = get_public_apps()
    assert len(public_apps) == 2
    
    # query search
    res = get_public_apps(query="cool")
    assert len(res) == 1
    assert res[0]["name"] == "app1"
    
    # tag search
    res = get_public_apps(tag="database")
    assert len(res) == 1
    assert res[0]["name"] == "app2"

# ==================== API TESTS ====================

def test_showcase_endpoints_api():
    client = TestClient(quad_app)
    # Register/Login
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create App
    repository.create_app("testapp", "static", "owner")
    
    # Patch metadata
    resp = client.patch(
        "/showcase/testapp",
        headers=headers,
        json={"visibility": "public", "description": "High performance application", "tags": "speed,python"}
    )
    assert resp.status_code == 200
    assert resp.json()["visibility"] == "public"
    assert resp.json()["description"] == "High performance application"
    assert resp.json()["tags"] == "speed,python"
    
    # Record view
    resp = client.post("/showcase/testapp/view")
    assert resp.status_code == 200
    assert resp.json()["recorded"] is True
    
    # Fetch showcase list
    resp = client.get("/showcase")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["view_count"] == 1
    
    # Leaderboard
    resp = client.get("/showcase/leaderboard?sort_by=views")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "testapp"

def test_patch_metadata_unauthorized():
    client = TestClient(quad_app)
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    client.post("/auth/register", json={"username": "intruder", "email": "i@test.com", "password": "password123"})
    
    login_resp = client.post("/auth/login", json={"username_or_email": "intruder", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    repository.create_app("testapp", "static", "owner")
    
    resp = client.patch(
        "/showcase/testapp",
        headers=headers,
        json={"visibility": "public"}
    )
    assert resp.status_code == 403

def test_user_profile_api():
    client = TestClient(quad_app)
    # Register owner & stranger
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    client.post("/auth/register", json={"username": "stranger", "email": "s@test.com", "password": "password123"})
    
    repository.create_app("pubapp", "static", "owner")
    repository.create_app("privapp", "node", "owner")
    
    # Make pubapp public, privapp stays private
    update_app_metadata("pubapp", "owner", visibility="public")
    update_app_metadata("privapp", "owner", visibility="private")
    
    # Stranger profile view -> returns only pubapp
    resp = client.get("/showcase/users/owner")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["username"] == "owner"
    assert len(data["apps"]) == 1
    assert data["apps"][0]["name"] == "pubapp"
    
    # Owner profile view with Auth -> returns both
    o_login = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    o_token = o_login.json()["access_token"]
    o_headers = {"Authorization": f"Bearer {o_token}"}
    
    resp = client.get("/showcase/users/owner", headers=o_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["apps"]) == 2
