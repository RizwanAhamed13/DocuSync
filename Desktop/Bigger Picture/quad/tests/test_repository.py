import os
import tempfile
import pytest
from app import config, db, repository

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

def test_create_and_get():
    app = repository.create_app("test-app", "node")
    assert app.name == "test-app"
    assert app.stack == "node"
    assert app.status == "STOPPED"
    assert app.created_at is not None
    
    fetched = repository.get_app("test-app")
    assert fetched is not None
    assert fetched.name == "test-app"
    assert fetched.stack == "node"
    assert fetched.status == "STOPPED"

def test_duplicate_name_raises():
    repository.create_app("duplicate")
    with pytest.raises(ValueError, match="already exists"):
        repository.create_app("duplicate")

def test_list_apps():
    assert len(repository.list_apps()) == 0
    repository.create_app("app1", "static")
    repository.create_app("app2", "python")
    apps = repository.list_apps()
    assert len(apps) == 2
    names = [a.name for a in apps]
    assert "app1" in names
    assert "app2" in names

def test_update_status():
    repository.create_app("update-me")
    updated = repository.update_status(
        name="update-me",
        status="RUNNING",
        container_id="123456",
        image_tag="latest",
        internal_port=3000
    )
    assert updated.status == "RUNNING"
    assert updated.container_id == "123456"
    assert updated.image_tag == "latest"
    assert updated.internal_port == 3000

    with pytest.raises(ValueError, match="not found"):
        repository.update_status("nonexistent", "RUNNING")

def test_touch_last_seen():
    repository.create_app("touch-me")
    app = repository.get_app("touch-me")
    assert app.last_seen is None
    
    updated = repository.touch_last_seen("touch-me")
    assert updated.last_seen is not None

    with pytest.raises(ValueError, match="not found"):
        repository.touch_last_seen("nonexistent")

def test_delete_app():
    repository.create_app("delete-me")
    assert repository.get_app("delete-me") is not None
    
    deleted = repository.delete_app("delete-me")
    assert deleted is True
    assert repository.get_app("delete-me") is None
    
    assert repository.delete_app("delete-me") is False
