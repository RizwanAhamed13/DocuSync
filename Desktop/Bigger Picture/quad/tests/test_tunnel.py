import os
import tempfile
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import config, db
from app.main import app as quad_app
from app.tunnel_repo import (
    create_tunnel,
    get_tunnel,
    get_tunnel_by_subdomain,
    list_tunnels,
    close_tunnel,
    ping_tunnel,
    cleanup_stale_tunnels
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

def test_create_and_get_tunnel():
    res = create_tunnel("myapp", "rizwan", 3000, "rizwan-myapp", "quad-abc123")
    assert res["status"] == "ACTIVE"
    assert res["local_port"] == 3000
    
    fetched = get_tunnel_by_subdomain("rizwan-myapp")
    assert fetched is not None
    assert fetched["app_name"] == "myapp"
    assert fetched["status"] == "ACTIVE"

def test_close_tunnel():
    res = create_tunnel("myapp", "rizwan", 3000, "rizwan-myapp", "quad-abc123")
    tid = res["tunnel_id"]
    close_tunnel(tid)
    fetched = get_tunnel(tid)
    assert fetched["status"] == "CLOSED"

def test_ping_tunnel():
    res = create_tunnel("myapp", "rizwan", 3000, "rizwan-myapp", "quad-abc123")
    tid = res["tunnel_id"]
    ping_tunnel(tid)
    fetched = get_tunnel(tid)
    assert fetched["last_ping"] is not None

def test_cleanup_stale():
    from datetime import datetime, timezone, timedelta
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    
    conn = db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tunnels (tunnel_id, app_name, owner, local_port, subdomain, status, frpc_name, created_at, last_ping)
            VALUES ('stale-id', 'myapp', 'rizwan', 3000, 'rizwan-myapp', 'ACTIVE', 'quad-abc123', 'now', ?)
            """,
            (stale_time,)
        )
        conn.commit()
    finally:
        conn.close()
        
    closed = cleanup_stale_tunnels(older_than_seconds=300)
    assert "stale-id" in closed
    fetched = get_tunnel("stale-id")
    assert fetched["status"] == "CLOSED"

def test_cleanup_skips_recent():
    from datetime import datetime, timezone, timedelta
    recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    
    conn = db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tunnels (tunnel_id, app_name, owner, local_port, subdomain, status, frpc_name, created_at, last_ping)
            VALUES ('recent-id', 'myapp', 'rizwan', 3000, 'recent-myapp', 'ACTIVE', 'quad-abc123', 'now', ?)
            """,
            (recent_time,)
        )
        conn.commit()
    finally:
        conn.close()
        
    closed = cleanup_stale_tunnels(older_than_seconds=300)
    assert "recent-id" not in closed
    fetched = get_tunnel("recent-id")
    assert fetched["status"] == "ACTIVE"

def test_subdomain_uniqueness():
    create_tunnel("myapp", "rizwan", 3000, "rizwan-myapp", "quad-abc")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        create_tunnel("myapp2", "rizwan", 3000, "rizwan-myapp", "quad-def")

# API tests

def test_open_tunnel_returns_201():
    client = TestClient(quad_app)
    response = client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 3000, "owner": "rizwan"}
    )
    assert response.status_code == 201
    data = response.json()
    assert "tunnel_id" in data
    assert "subdomain" in data
    assert "public_url" in data
    assert "frpc_config" in data

def test_open_tunnel_invalid_port():
    client = TestClient(quad_app)
    response = client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 99999, "owner": "rizwan"}
    )
    assert response.status_code == 400

def test_open_tunnel_duplicate_subdomain():
    client = TestClient(quad_app)
    r1 = client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 3000, "owner": "rizwan"}
    )
    assert r1.status_code == 201
    sub1 = r1.json()["subdomain"]
    
    r2 = client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 3000, "owner": "rizwan"}
    )
    assert r2.status_code == 201
    sub2 = r2.json()["subdomain"]
    
    assert sub1 != sub2
    assert sub2.startswith("rizwan-myapp-")

def test_ping_tunnel():
    client = TestClient(quad_app)
    r1 = client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 3000, "owner": "rizwan"}
    )
    tid = r1.json()["tunnel_id"]
    
    r2 = client.post(f"/tunnels/{tid}/ping")
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}

def test_close_tunnel_api():
    client = TestClient(quad_app)
    r1 = client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 3000, "owner": "rizwan"}
    )
    tid = r1.json()["tunnel_id"]
    
    r2 = client.post(f"/tunnels/{tid}/close")
    assert r2.status_code == 200
    assert r2.json() == {"closed": tid}

def test_list_tunnels():
    client = TestClient(quad_app)
    client.post(
        "/tunnels/open",
        json={"app_name": "myapp", "local_port": 3000, "owner": "rizwan"}
    )
    response = client.get("/tunnels?owner=rizwan")
    assert response.status_code == 200
    assert len(response.json()) >= 1

def test_get_tunnel_not_found():
    client = TestClient(quad_app)
    response = client.get("/tunnels/nonexistent-id")
    assert response.status_code == 404
