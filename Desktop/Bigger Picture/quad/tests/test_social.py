import os
import pytest
import tempfile
import shutil
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app import config, db, repository
from app.main import app as quad_app
from app.auth.service import create_user, create_access_token
from app.social.upvotes import upvote_app, unupvote_app, has_upvoted
from app.social.activity import get_activity_feed, emit_event

@pytest.fixture(autouse=True)
def temp_db_and_source():
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    old_db_path = config.DB_PATH
    config.DB_PATH = temp_db_path
    db.init_db()
    
    # Setup projects_source temp folder
    old_projects_source = "projects_source"
    os.makedirs("projects_source", exist_ok=True)
    
    yield
    
    config.DB_PATH = old_db_path
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)
        
    if os.path.exists("projects_source"):
        shutil.rmtree("projects_source")

# ==================== UNIT TESTS ====================

def test_upvotes_unit():
    create_user("user1", "u1@test.com", "password123")
    repository.create_app("myapp", "static", "user1")
    
    assert not has_upvoted("user1", "myapp")
    upvote_app("user1", "myapp")
    assert has_upvoted("user1", "myapp")
    
    app = repository.get_app("myapp")
    assert app.upvote_count == 1
    
    # Duplicate upvote raises
    with pytest.raises(ValueError, match="already upvoted"):
        upvote_app("user1", "myapp")
        
    # Unupvote
    unupvote_app("user1", "myapp")
    assert not has_upvoted("user1", "myapp")
    app = repository.get_app("myapp")
    assert app.upvote_count == 0
    
    # Unupvoting again raises
    with pytest.raises(ValueError, match="not upvoted"):
        unupvote_app("user1", "myapp")

def test_activity_feed_unit():
    emit_event("alice", "deploy", "app", "app1", {"stack": "node"})
    emit_event("bob", "fork", "app", "app2", {"original_app": "app1"})
    
    feed = get_activity_feed(limit=5)
    assert len(feed) == 2
    assert feed[0]["username"] == "bob"
    assert feed[0]["event_type"] == "fork"
    assert feed[0]["metadata"]["original_app"] == "app1"
    assert feed[1]["username"] == "alice"
    assert feed[1]["event_type"] == "deploy"

# ==================== API TESTS ====================

def test_upvote_api():
    client = TestClient(quad_app)
    # Register / Login
    client.post("/auth/register", json={"username": "user1", "email": "u1@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "user1", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    # Create App
    repository.create_app("myapp", "static", "user1")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Upvote
    resp = client.post("/social/upvotes/myapp", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    
    # Duplicate upvote -> 400
    resp = client.post("/social/upvotes/myapp", headers=headers)
    assert resp.status_code == 400
    assert "already upvoted" in resp.json()["detail"].lower()
    
    # Remove upvote
    resp = client.delete("/social/upvotes/myapp", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

def test_fork_api():
    client = TestClient(quad_app)
    # Register / Login
    client.post("/auth/register", json={"username": "owner", "email": "owner@test.com", "password": "password123"})
    client.post("/auth/register", json={"username": "forker", "email": "forker@test.com", "password": "password123"})
    
    f_login = client.post("/auth/login", json={"username_or_email": "forker", "password": "password123"})
    token = f_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create original app
    repository.create_app("orig-app", "static", "owner")
    # Setup its persistent source
    orig_dir = os.path.join("projects_source", "orig-app")
    os.makedirs(orig_dir, exist_ok=True)
    with open(os.path.join(orig_dir, "index.html"), "w") as f:
        f.write("Original Page")
        
    with patch("app.deploy._deploy_pipeline") as mock_pipeline:
        resp = client.post(
            "/social/forks",
            headers=headers,
            json={"original_app": "orig-app", "forked_app": "forked-app"}
        )
        assert resp.status_code == 202
        assert resp.json()["ok"] is True
        assert resp.json()["forked_app"] == "forked-app"
        
        # Verify db record for fork exists
        app = repository.get_app("forked-app")
        assert app is not None
        assert app.owner == "forker"
        assert app.status == "BUILDING"
        
        # Verify projects_source file copied
        forked_file = os.path.join("projects_source", "forked-app", "index.html")
        assert os.path.exists(forked_file)
        with open(forked_file, "r") as f:
            assert f.read() == "Original Page"
            
        mock_pipeline.assert_called_once()

def test_wired_events_api():
    client = TestClient(quad_app)
    # Register/Login
    client.post("/auth/register", json={"username": "user1", "email": "u1@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "user1", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Team Create
    resp = client.post(
        "/teams",
        headers=headers,
        json={"slug": "team-event", "display_name": "Event Team", "visibility": "public"}
    )
    assert resp.status_code == 201
    
    # 2. Team Join
    client.post("/auth/register", json={"username": "user2", "email": "u2@test.com", "password": "password123"})
    resp = client.post(
        "/teams/team-event/members",
        headers=headers,
        json={"username": "user2", "role": "member"}
    )
    assert resp.status_code == 201
    
    # Check activity feed
    resp = client.get("/social/activity")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 2
    types = [e["event_type"] for e in events]
    assert "team_create" in types
    assert "team_join" in types
