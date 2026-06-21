import os
import tempfile
import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import config, db, repository
from app.main import app as quad_app
from app.proxy import (
    extract_app_name,
    waking_page,
    wake_and_wait
)
from app.container import ContainerError

# Section 1 - unit tests (no Docker, no network)

def test_extract_app_name_standard():
    assert extract_app_name("myapp.quad.localhost") == "myapp"

def test_extract_app_name_with_port():
    assert extract_app_name("myapp.quad.localhost:8080") == "myapp"

def test_extract_app_name_production():
    assert extract_app_name("docusync.quad.drmcet.ac.in") == "docusync"

def test_extract_app_name_no_subdomain():
    assert extract_app_name("quad.localhost") is None

def test_extract_app_name_direct():
    assert extract_app_name("localhost:8000") is None

def test_extract_app_name_empty():
    assert extract_app_name("") is None

def test_waking_page_contains_refresh():
    html = waking_page("myapp", "node")
    body_text = html.body.decode().lower()
    assert "meta" in body_text
    assert "refresh" in body_text
    assert "myapp" in html.body.decode()

def test_waking_page_is_small():
    html = waking_page("myapp", "node")
    assert len(html.body) < 1024


# Section 2 - proxy handler tests (use FastAPI TestClient, no Docker)

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

def test_proxy_unknown_host():
    client = TestClient(quad_app)
    # Request without subdomain should hit the control plane
    response = client.get("/health", headers={"Host": "localhost:8000"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_proxy_app_not_found():
    client = TestClient(quad_app)
    with patch("app.proxy.get_app", return_value=None):
        response = client.get("/", headers={"Host": "unknown.quad.localhost"})
        assert response.status_code == 404
        assert "app not found" in response.text

def test_proxy_app_building():
    client = TestClient(quad_app)
    mock_app = MagicMock(status="BUILDING", stack="node")
    with patch("app.proxy.get_app", return_value=mock_app):
        response = client.get("/", headers={"Host": "myapp.quad.localhost"})
        assert response.status_code == 503
        assert "building" in response.text.lower()

def test_proxy_app_failed():
    client = TestClient(quad_app)
    mock_app = MagicMock(status="FAILED", stack="node")
    with patch("app.proxy.get_app", return_value=mock_app):
        response = client.get("/", headers={"Host": "myapp.quad.localhost"})
        assert response.status_code == 503
        assert "failed" in response.text.lower()

def test_proxy_app_stopped_returns_waking_page():
    client = TestClient(quad_app)
    mock_app = MagicMock(status="STOPPED", stack="node")
    with patch("app.proxy.get_app", return_value=mock_app):
        with patch("app.proxy.start_container") as mock_start:
            response = client.get("/", headers={"Host": "myapp.quad.localhost"})
            assert response.status_code == 503
            assert "starting" in response.text.lower()
            assert "meta" in response.text.lower()

def test_single_flight_lock_prevents_double_start():
    async def run_test():
        call_count = 0
        def fake_start(name):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)

        with patch("app.proxy.start_container", fake_start):
            with patch("app.proxy.get_app") as mock_get:
                mock_get.side_effect = [
                    MagicMock(status="STOPPED", internal_port=9000, stack="node"),
                    MagicMock(status="RUNNING", internal_port=9000, stack="node"),
                    MagicMock(status="RUNNING", internal_port=9000, stack="node"),
                ]
                await asyncio.gather(
                    wake_and_wait("testapp", "node"),
                    wake_and_wait("testapp", "node"),
                )
        assert call_count == 1

    asyncio.run(run_test())


# Section 3 - integration test (requires Docker + a real deployed app)

def is_docker_available():
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False

skip_no_docker = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker daemon not available"
)

@skip_no_docker
@pytest.mark.integration
def test_full_wake_cycle(tmp_path):
    from app import detector, recipes, container
    
    app_name = "quad-test-proxy-wake"
    
    # 1. Create minimal static project
    index_html = tmp_path / "index.html"
    index_html.write_text("<h1>Proxy Wake Works!</h1>", encoding="utf-8")
    
    # 2. Run full pipeline
    detection = detector.detect_stack(str(tmp_path))
    dockerfile = recipes.generate_dockerfile(detection)
    dockerignore = recipes.generate_dockerignore(detection)
    
    # Pre-register app in SQLite
    db_conn = db.get_connection()
    try:
        db_conn.execute(
            "INSERT INTO apps (name, stack, status, created_at) VALUES (?, 'static', 'STOPPED', 'now')",
            (app_name,)
        )
        db_conn.commit()
    finally:
        db_conn.close()
        
    try:
        # Build image
        from app.builder import build_image
        build_res = build_image(str(tmp_path), app_name, dockerfile, dockerignore)
        assert build_res.success is True
        
        # Start once to provision container
        c_info = container.create_and_start_container(app_name, build_res.image_tag, 80)
        assert c_info.status == "RUNNING"
        
        # 3. Stop container (put it to sleep)
        container.stop_container(app_name)
        
        # 4. Send GET request to proxy with correct Host header
        client = TestClient(quad_app)
        response = client.get("/", headers={"Host": f"{app_name}.quad.localhost"})
        
        # 5. Assert response is waking page
        assert response.status_code == 503
        assert "starting" in response.text.lower()
        
        # 6. Wait for container to become RUNNING (should happen fast in background)
        deadline = time.monotonic() + 15
        running = False
        while time.monotonic() < deadline:
            app_state = repository.get_app(app_name)
            if app_state and app_state.status == "RUNNING":
                running = True
                break
            time.sleep(0.5)
        assert running is True
        
        # 7. Send another GET request
        response2 = client.get("/", headers={"Host": f"{app_name}.quad.localhost"})
        
        # 8. Assert response is actual app content
        assert response2.status_code == 200
        assert "proxy wake works" in response2.text.lower()
        
    finally:
        container.remove_container(app_name, remove_image=True)
