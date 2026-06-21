import os
import pytest
import tempfile
from fastapi.testclient import TestClient

from app import config, db
from app.main import app as quad_app
from app.auth.service import (
    hash_password,
    verify_password,
    create_user,
    authenticate_user,
    create_access_token,
    decode_token,
    revoke_token
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

def test_hash_and_verify():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h)
    assert not verify_password("wrong", h)

def test_create_user_success():
    u = create_user("rizwan", "r@test.com", "password123")
    assert u["username"] == "rizwan"
    assert "password_hash" not in u

def test_create_user_duplicate_username():
    create_user("rizwan", "r@test.com", "pass1234")
    with pytest.raises(ValueError, match="already taken|already registered"):
        create_user("rizwan", "another@test.com", "pass1234")

def test_create_user_invalid_username():
    with pytest.raises(ValueError):
        create_user("r!", "r@test.com", "pass1234")
    with pytest.raises(ValueError):
        create_user("ab", "r@test.com", "pass1234")

def test_create_user_short_password():
    with pytest.raises(ValueError):
        create_user("rizwan2", "r2@test.com", "short")

def test_authenticate_by_username():
    create_user("rizwan", "r@test.com", "password123")
    u = authenticate_user("rizwan", "password123")
    assert u is not None
    assert u["username"] == "rizwan"

def test_authenticate_by_email():
    create_user("rizwan", "r@test.com", "password123")
    u = authenticate_user("r@test.com", "password123")
    assert u is not None
    assert u["username"] == "rizwan"

def test_authenticate_wrong_password():
    create_user("rizwan", "r@test.com", "password123")
    assert authenticate_user("rizwan", "wrongpass") is None

def test_token_create_and_decode():
    u = create_user("rizwan", "r@test.com", "password123")
    token = create_access_token(u["id"], "rizwan", "student")
    payload = decode_token(token)
    assert payload is not None
    assert payload.get("username") == "rizwan" or payload.get("sub") == "rizwan"

def test_token_revocation():
    u = create_user("rizwan", "r@test.com", "password123")
    token = create_access_token(u["id"], "rizwan", "student")
    payload = decode_token(token)
    assert payload is not None
    revoke_token(payload["jti"])
    assert decode_token(token) is None


# ==================== API TESTS ====================

def test_register_success():
    client = TestClient(quad_app)
    response = client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "rizwan"

def test_register_duplicate():
    client = TestClient(quad_app)
    client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    response = client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r2@test.com", "password": "password123"}
    )
    assert response.status_code == 409

def test_login_success():
    client = TestClient(quad_app)
    client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    response = client.post(
        "/auth/login",
        json={"username_or_email": "rizwan", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

def test_login_wrong_password():
    client = TestClient(quad_app)
    client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    response = client.post(
        "/auth/login",
        json={"username_or_email": "rizwan", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_me_requires_auth():
    client = TestClient(quad_app)
    response = client.get("/auth/me")
    assert response.status_code == 401

def test_me_returns_profile():
    client = TestClient(quad_app)
    reg_resp = client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    token = reg_resp.json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "rizwan"

def test_logout():
    client = TestClient(quad_app)
    reg_resp = client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    token = reg_resp.json()["access_token"]
    
    logout_resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    
    # Try using token again
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 401

def test_patch_me():
    client = TestClient(quad_app)
    reg_resp = client.post(
        "/auth/register",
        json={"username": "rizwan", "email": "r@test.com", "password": "password123"}
    )
    token = reg_resp.json()["access_token"]
    
    patch_resp = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"bio": "hello world", "display_name": "Rizwan Ahamed"}
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["bio"] == "hello world"
    assert data["display_name"] == "Rizwan Ahamed"
