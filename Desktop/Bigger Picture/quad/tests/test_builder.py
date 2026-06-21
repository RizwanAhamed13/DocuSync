import os
import pytest
import docker
from app.builder import (
    sanitize_app_name,
    get_image_tag,
    write_build_files,
    save_build_log,
    build_image,
    BuildResult,
    BuildError
)
from app import detector, recipes

# Section 1 - unit tests (no Docker daemon required)

def test_sanitize_normal():
    assert sanitize_app_name("myapp") == "myapp"

def test_sanitize_spaces():
    assert sanitize_app_name("My App") == "my-app"

def test_sanitize_underscores():
    assert sanitize_app_name("my_app_2") == "my-app-2"

def test_sanitize_special_chars():
    assert sanitize_app_name("app@#$%name!") == "appname"

def test_sanitize_leading_trailing():
    assert sanitize_app_name("--myapp--") == "myapp"

def test_sanitize_uppercase():
    assert sanitize_app_name("MyApp") == "myapp"

def test_get_image_tag():
    assert get_image_tag("myapp") == "quad-myapp:latest"

def test_get_image_tag_sanitizes():
    assert get_image_tag("My App") == "quad-my-app:latest"

def test_write_build_files(tmp_path):
    project_path = str(tmp_path / "proj")
    write_build_files(project_path, "FROM alpine", "node_modules")
    
    df_path = os.path.join(project_path, "Dockerfile")
    di_path = os.path.join(project_path, ".dockerignore")
    
    assert os.path.exists(df_path)
    assert os.path.exists(di_path)
    
    with open(df_path, "r", encoding="utf-8") as f:
        assert f.read() == "FROM alpine"
        
    with open(di_path, "r", encoding="utf-8") as f:
        assert f.read() == "node_modules"

def test_save_build_log(tmp_path):
    log_dir = str(tmp_path / "logs")
    log_path = save_build_log("testapp", "build output here", log_dir=log_dir)
    
    assert os.path.exists(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        assert f.read() == "build output here"

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
def test_build_static_app(tmp_path):
    # Setup static project files
    index_html = tmp_path / "index.html"
    index_html.write_text("<h1>Quad Test</h1>", encoding="utf-8")
    
    # Run detector and recipes
    detection = detector.detect_stack(str(tmp_path))
    dockerfile = recipes.generate_dockerfile(detection)
    dockerignore = recipes.generate_dockerignore(detection)
    
    # Run builder
    result = build_image(str(tmp_path), "quad-test-static", dockerfile, dockerignore)
    
    assert result.success is True
    assert result.image_tag == "quad-quad-test-static:latest"
    assert len(result.log) > 0
    assert result.error is None
    assert result.duration_seconds > 0
    
    # Cleanup
    client = docker.from_env()
    try:
        client.images.remove(result.image_tag, force=True)
    except Exception:
        pass

@skip_no_docker
@pytest.mark.integration
def test_build_bad_dockerfile(tmp_path):
    bad_dockerfile = "FROM nonexistent-base-image-that-does-not-exist:never\nRUN exit 1"
    
    result = build_image(str(tmp_path), "quad-bad-build", bad_dockerfile, "")
    
    assert result.success is False
    assert result.error is not None
    assert result.image_tag is None
    assert len(result.log) > 0

@skip_no_docker
@pytest.mark.integration
def test_build_node_app(tmp_path):
    # Setup Node project
    pkg = {
        "name": "test",
        "version": "1.0.0",
        "scripts": {
            "start": "node index.js"
        }
    }
    pkg_json = tmp_path / "package.json"
    with open(pkg_json, "w", encoding="utf-8") as f:
        import json
        json.dump(pkg, f)
        
    index_js = tmp_path / "index.js"
    index_js.write_text(
        "const http = require('http');\n"
        "http.createServer((req, res) => { res.end('ok'); }).listen(3000);\n",
        encoding="utf-8"
    )
    
    detection = detector.detect_stack(str(tmp_path))
    dockerfile = recipes.generate_dockerfile(detection)
    dockerignore = recipes.generate_dockerignore(detection)
    
    result = build_image(str(tmp_path), "quad-test-node", dockerfile, dockerignore)
    
    assert result.success is True
    
    # Cleanup
    client = docker.from_env()
    try:
        client.images.remove(result.image_tag, force=True)
    except Exception:
        pass
