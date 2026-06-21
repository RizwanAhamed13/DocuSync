import os
import io
import tempfile
import zipfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import config, db, repository
from app.main import app as quad_app

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

def test_deploy_upload_invalid_name():
    client = TestClient(quad_app)
    file_data = io.BytesIO(b"fake zip content")
    response = client.post(
        "/deploy/upload?name=My App!",
        files={"file": ("archive.zip", file_data, "application/zip")}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_APP_NAME"

def test_deploy_upload_name_too_short():
    client = TestClient(quad_app)
    file_data = io.BytesIO(b"fake zip content")
    response = client.post(
        "/deploy/upload?name=ab",
        files={"file": ("archive.zip", file_data, "application/zip")}
    )
    assert response.status_code == 400

def test_deploy_upload_duplicate_name():
    client = TestClient(quad_app)
    repository.create_app("myapp")
    file_data = io.BytesIO(b"fake zip content")
    response = client.post(
        "/deploy/upload?name=myapp",
        files={"file": ("archive.zip", file_data, "application/zip")}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_APP_NAME"

def test_deploy_upload_returns_202():
    client = TestClient(quad_app)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("index.html", "<h1>Hello</h1>")
    zip_buffer.seek(0)
    
    with patch("app.deploy._deploy_pipeline") as mock_pipeline:
        response = client.post(
            "/deploy/upload?name=myapp",
            files={"file": ("archive.zip", zip_buffer, "application/zip")}
        )
        assert response.status_code == 202
        data = response.json()
        assert data["app_name"] == "myapp"
        assert data["status"] == "BUILDING"
        mock_pipeline.assert_called_once()

def test_deploy_upload_malformed_zip():
    client = TestClient(quad_app)
    file_data = io.BytesIO(b"this is not a zip")
    response = client.post(
        "/deploy/upload?name=myapp",
        files={"file": ("archive.zip", file_data, "application/zip")}
    )
    assert response.status_code == 400
    assert "zip" in response.json()["error"].lower()

def test_deploy_git_returns_202():
    client = TestClient(quad_app)
    with patch("app.deploy._deploy_from_git") as mock_git:
        response = client.post(
            "/deploy/git",
            json={"name": "gitapp", "git_url": "https://github.com/user/repo.git"}
        )
        assert response.status_code == 202
        data = response.json()
        assert data["app_name"] == "gitapp"
        assert data["status"] == "BUILDING"
        mock_git.assert_called_once()

def test_get_logs_not_found():
    client = TestClient(quad_app)
    response = client.get("/deploy/nonexistent/logs")
    assert response.status_code == 404

def test_get_logs_exists(tmp_path):
    client = TestClient(quad_app)
    repository.create_app("logapp")
    
    log_file = tmp_path / "build.log"
    log_file.write_text("build log output here", encoding="utf-8")
    
    from app.deploy import update_build_log_path
    update_build_log_path("logapp", str(log_file))
    
    response = client.get("/deploy/logapp/logs")
    assert response.status_code == 200
    assert response.text == "build log output here"

def test_delete_app():
    client = TestClient(quad_app)
    repository.create_app("deleteapp")
    with patch("app.deploy.remove_container") as mock_remove:
        with patch("app.deploy.delete_app") as mock_del:
            response = client.delete("/deploy/deleteapp")
            assert response.status_code == 200
            assert response.json() == {"deleted": "deleteapp"}
            mock_remove.assert_called_once_with("deleteapp", remove_image=True)
            mock_del.assert_called_once_with("deleteapp")

def test_delete_app_not_found():
    client = TestClient(quad_app)
    response = client.delete("/deploy/nonexistent")
    assert response.status_code == 404
