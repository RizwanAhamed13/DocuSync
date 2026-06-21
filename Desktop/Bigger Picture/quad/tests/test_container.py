import os
import tempfile
import pytest
import docker
from app import config, db, repository
from app.container import (
    sanitize_app_name,
    get_container_name,
    PORT_RANGE_START,
    PORT_RANGE_END,
    get_next_available_port,
    create_and_start_container,
    stop_container,
    start_container,
    remove_container,
    get_container_info,
    get_container_logs,
    list_quad_containers,
    sync_container_status,
    ContainerError
)

# Section 1 - unit tests (no Docker)

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

def test_sanitize_container_name():
    assert get_container_name("My App") == "quad-my-app"
    assert get_container_name("___test___") == "quad-test"

def test_port_range():
    assert PORT_RANGE_START == 9000
    assert PORT_RANGE_END == 9999

def test_get_next_available_port_empty_db():
    assert get_next_available_port() == 9000

def test_get_next_available_port_with_used():
    repository.create_app("app1")
    repository.update_status("app1", "RUNNING", internal_port=9000)
    repository.create_app("app2")
    repository.update_status("app2", "RUNNING", internal_port=9001)
    
    assert get_next_available_port() == 9002

def test_get_next_available_port_exhausted():
    # Insert apps with all ports in range used
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        for p in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            cursor.execute(
                "INSERT INTO apps (name, status, created_at, internal_port) VALUES (?, 'RUNNING', 'now', ?)",
                (f"app-{p}", p)
            )
        conn.commit()
    finally:
        conn.close()
        
    with pytest.raises(ContainerError, match="exhausted"):
        get_next_available_port()

# Section 2 - integration tests (require Docker daemon)

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
def test_create_and_start():
    app_name = "quad-test-run"
    repository.create_app(app_name, "static")
    
    try:
        result = create_and_start_container(app_name, "nginx:alpine", 80)
        assert result.status == "RUNNING"
        assert result.container_id is not None
        assert PORT_RANGE_START <= result.host_port <= PORT_RANGE_END
        assert result.error is None
        
        # Verify SQLite updated
        app = repository.get_app(app_name)
        assert app.status == "RUNNING"
        assert app.internal_port == result.host_port
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_start_already_running():
    app_name = "quad-test-run-dup"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        result = start_container(app_name)
        assert result.status == "RUNNING"
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_stop_container():
    app_name = "quad-test-stop"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        result = stop_container(app_name)
        assert result.status == "STOPPED"
        app = repository.get_app(app_name)
        assert app.status == "STOPPED"
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_start_stopped_container():
    app_name = "quad-test-restart"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        stop_container(app_name)
        
        result = start_container(app_name)
        assert result.status == "RUNNING"
        app = repository.get_app(app_name)
        assert app.status == "RUNNING"
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_remove_container():
    app_name = "quad-test-remove"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        remove_container(app_name)
        info = get_container_info(app_name)
        assert info is None
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_remove_container_not_found():
    # Must not raise, is idempotent
    remove_container("nonexistent-app-xyz")

@skip_no_docker
@pytest.mark.integration
def test_duplicate_container_raises():
    app_name = "quad-test-dup-err"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        with pytest.raises(ContainerError, match="exists"):
            create_and_start_container(app_name, "nginx:alpine", 80)
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_get_container_logs():
    app_name = "quad-test-logs"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        logs = get_container_logs(app_name, tail=50)
        assert isinstance(logs, str)
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_list_quad_containers():
    app1 = "quad-test-list1"
    app2 = "quad-test-list2"
    repository.create_app(app1, "static")
    repository.create_app(app2, "static")
    try:
        create_and_start_container(app1, "nginx:alpine", 80)
        create_and_start_container(app2, "nginx:alpine", 80)
        
        result = list_quad_containers()
        names = [c.container_name for c in result]
        assert f"quad-{app1}" in names
        assert f"quad-{app2}" in names
    finally:
        remove_container(app1)
        remove_container(app2)

@skip_no_docker
@pytest.mark.integration
def test_sync_status_after_external_stop():
    app_name = "quad-test-ext-stop"
    repository.create_app(app_name, "static")
    try:
        create_and_start_container(app_name, "nginx:alpine", 80)
        
        # Stop container directly via Docker SDK (bypassing stop_container)
        client = docker.from_env()
        c = client.containers.get(f"quad-{app_name}")
        c.stop()
        
        sync_container_status(app_name)
        app = repository.get_app(app_name)
        assert app.status == "STOPPED"
    finally:
        remove_container(app_name)

@skip_no_docker
@pytest.mark.integration
def test_port_not_reused():
    app1 = "quad-test-p1"
    app2 = "quad-test-p2"
    repository.create_app(app1, "static")
    repository.create_app(app2, "static")
    try:
        res1 = create_and_start_container(app1, "nginx:alpine", 80)
        res2 = create_and_start_container(app2, "nginx:alpine", 80)
        
        assert res1.host_port != res2.host_port
    finally:
        remove_container(app1)
        remove_container(app2)
