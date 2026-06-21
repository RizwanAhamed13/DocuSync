import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, follow_redirects=False)

def test_https_redirect():
    response = client.get("/", headers={"x-forwarded-proto": "http"})
    assert response.status_code == 301
    assert response.headers["location"].startswith("https://")

def test_rate_limit_auth():
    # exceed the limit of 5/min for login endpoint
    for _ in range(6):
        resp = client.post("/auth/login", json={"username": "nonexistent", "password": "wrong"})
    assert resp.status_code == 429

def test_path_traversal_block():
    # httpx normalises paths before sending so inject the raw path via scope
    from starlette.testclient import TestClient as StarletteClient
    tc = StarletteClient(app, follow_redirects=False)
    resp = tc.get("/%2e%2e/secret.txt")
    assert resp.status_code in (400, 404)
