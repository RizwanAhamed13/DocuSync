import os
import pytest
import tempfile
from fastapi.testclient import TestClient

from app import config, db, repository
from app.main import app as quad_app
from app.auth.service import create_user, create_access_token
from app.teams.service import (
    create_team,
    get_team,
    add_member,
    remove_member,
    list_members,
    add_project,
    list_team_projects
)

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

def test_create_team():
    create_user("owner", "o@test.com", "password123")
    t = create_team("team-alpha", "Team Alpha", "owner", "Description", "private")
    assert t["slug"] == "team-alpha"
    assert t["owner_username"] == "owner"
    
    members = list_members("team-alpha")
    assert len(members) == 1
    assert members[0]["username"] == "owner"
    assert members[0]["role"] == "owner"

def test_create_team_duplicate_slug():
    create_user("owner", "o@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    with pytest.raises(ValueError, match="already exists"):
        create_team("team-alpha", "Team Alpha 2", "owner")

def test_add_member():
    create_user("owner", "o@test.com", "password123")
    create_user("member1", "m1@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    
    add_member("team-alpha", "member1", "member")
    members = list_members("team-alpha")
    assert len(members) == 2
    assert any(m["username"] == "member1" for m in members)

def test_add_duplicate_member():
    create_user("owner", "o@test.com", "password123")
    create_user("member1", "m1@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    
    add_member("team-alpha", "member1")
    with pytest.raises(ValueError, match="already in team"):
        add_member("team-alpha", "member1")

def test_remove_member():
    create_user("owner", "o@test.com", "password123")
    create_user("member1", "m1@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    
    add_member("team-alpha", "member1")
    remove_member("team-alpha", "member1")
    members = list_members("team-alpha")
    assert len(members) == 1
    assert not any(m["username"] == "member1" for m in members)

def test_remove_owner_raises():
    create_user("owner", "o@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    with pytest.raises(ValueError, match="Cannot remove the team owner"):
        remove_member("team-alpha", "owner")

def test_add_project():
    create_user("owner", "o@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    repository.create_app("myapp", "static", "owner")
    
    add_project("team-alpha", "myapp")
    projects = list_team_projects("team-alpha")
    assert len(projects) == 1
    assert projects[0]["name"] == "myapp"

def test_list_team_projects():
    create_user("owner", "o@test.com", "password123")
    create_team("team-alpha", "Team Alpha", "owner")
    repository.create_app("myapp1", "static", "owner")
    repository.create_app("myapp2", "node", "owner")
    
    add_project("team-alpha", "myapp1")
    add_project("team-alpha", "myapp2")
    
    projects = list_team_projects("team-alpha")
    assert len(projects) == 2
    names = [p["name"] for p in projects]
    assert "myapp1" in names
    assert "myapp2" in names


# ==================== API TESTS ====================

def test_create_team_api():
    client = TestClient(quad_app)
    # Register user
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    response = client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-api", "display_name": "Team API", "visibility": "private"}
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "team-api"

def test_get_team_public():
    client = TestClient(quad_app)
    # Register owner
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    # Create public team
    client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-pub", "display_name": "Team Public", "visibility": "public"}
    )
    
    # Register viewer
    client.post("/auth/register", json={"username": "viewer", "email": "v@test.com", "password": "password123"})
    v_login = client.post("/auth/login", json={"username_or_email": "viewer", "password": "password123"})
    v_token = v_login.json()["access_token"]
    
    # Get team
    response = client.get("/teams/team-pub", headers={"Authorization": f"Bearer {v_token}"})
    assert response.status_code == 200
    assert response.json()["slug"] == "team-pub"

def test_get_team_private_unauthorized():
    client = TestClient(quad_app)
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    # Create private team
    client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-priv", "display_name": "Team Private", "visibility": "private"}
    )
    
    client.post("/auth/register", json={"username": "viewer", "email": "v@test.com", "password": "password123"})
    v_login = client.post("/auth/login", json={"username_or_email": "viewer", "password": "password123"})
    v_token = v_login.json()["access_token"]
    
    response = client.get("/teams/team-priv", headers={"Authorization": f"Bearer {v_token}"})
    assert response.status_code == 403

def test_add_member_not_owner():
    client = TestClient(quad_app)
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-priv", "display_name": "Team Private"}
    )
    
    # Register helper user and intruder user
    client.post("/auth/register", json={"username": "intruder", "email": "i@test.com", "password": "password123"})
    client.post("/auth/register", json={"username": "member1", "email": "m1@test.com", "password": "password123"})
    i_login = client.post("/auth/login", json={"username_or_email": "intruder", "password": "password123"})
    i_token = i_login.json()["access_token"]
    
    response = client.post(
        "/teams/team-priv/members",
        headers={"Authorization": f"Bearer {i_token}"},
        json={"username": "member1", "role": "member"}
    )
    assert response.status_code == 403

def test_add_member_owner():
    client = TestClient(quad_app)
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-priv", "display_name": "Team Private"}
    )
    
    client.post("/auth/register", json={"username": "member1", "email": "m1@test.com", "password": "password123"})
    
    response = client.post(
        "/teams/team-priv/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "member1", "role": "member"}
    )
    assert response.status_code == 201
    assert len(response.json()) == 2

def test_add_project_not_member():
    client = TestClient(quad_app)
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-priv", "display_name": "Team Private"}
    )
    
    # Register non-member
    client.post("/auth/register", json={"username": "stranger", "email": "s@test.com", "password": "password123"})
    s_login = client.post("/auth/login", json={"username_or_email": "stranger", "password": "password123"})
    s_token = s_login.json()["access_token"]
    
    # stranger creates app
    repository.create_app("stranger-app", "static", "stranger")
    
    # stranger tries to add project to owner's team
    response = client.post(
        "/teams/team-priv/projects",
        headers={"Authorization": f"Bearer {s_token}"},
        json={"app_name": "stranger-app"}
    )
    assert response.status_code == 403

def test_full_team_flow():
    client = TestClient(quad_app)
    # Register owner
    client.post("/auth/register", json={"username": "owner", "email": "o@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "owner", "password": "password123"})
    token = login_resp.json()["access_token"]
    
    # Create Team
    client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "team-flow", "display_name": "Team Flow", "visibility": "public"}
    )
    
    # Add Member
    client.post("/auth/register", json={"username": "member1", "email": "m1@test.com", "password": "password123"})
    client.post(
        "/teams/team-flow/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "member1", "role": "member"}
    )
    
    # Add Project
    repository.create_app("owner-app", "static", "owner")
    client.post(
        "/teams/team-flow/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"app_name": "owner-app"}
    )
    
    # Fetch team
    response = client.get("/teams/team-flow", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["members"]) == 2
    assert len(data["projects"]) == 1
    assert data["projects"][0]["name"] == "owner-app"
