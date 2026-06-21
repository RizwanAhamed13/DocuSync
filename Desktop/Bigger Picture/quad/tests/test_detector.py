import pytest
import json
import os
from app.detector import detect_stack, DetectionError, list_root_files, read_json_safe

def test_list_root_files(tmp_path):
    # Setup files and folders
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.log").write_text("world")
    os.makedirs(tmp_path / "some_dir")
    
    files = list_root_files(str(tmp_path))
    assert "file1.txt" in files
    assert "file2.log" in files
    assert "some_dir" not in files

def test_read_json_safe(tmp_path):
    p = tmp_path / "test.json"
    p.write_text('{"a": 1, "b": "hello"}')
    assert read_json_safe(str(p)) == {"a": 1, "b": "hello"}
    
    p_invalid = tmp_path / "invalid.json"
    p_invalid.write_text("{malformed json")
    assert read_json_safe(str(p_invalid)) == {}
    
    assert read_json_safe("non_existent_file.json") == {}

def test_java_maven(tmp_path):
    (tmp_path / "pom.xml").write_text("<project></project>")
    os.makedirs(tmp_path / "target")
    (tmp_path / "target" / "app-1.0.jar").write_text("fake jar")
    
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "java"
    assert res["package_manager"] == "maven"
    assert res["build_command"] == "mvn package -DskipTests"
    assert res["entrypoint"] == "java -jar target/app-1.0.jar"
    assert res["port"] == 8080
    assert res["confidence"] == "high"

def test_java_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text("// gradle config")
    os.makedirs(tmp_path / "build" / "libs")
    (tmp_path / "build" / "libs" / "app.jar").write_text("fake jar")
    
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "java"
    assert res["package_manager"] == "gradle"
    assert res["build_command"] == "./gradlew bootJar"
    assert res["entrypoint"] == "java -jar build/libs/app.jar"
    assert res["port"] == 8080
    assert res["confidence"] == "high"

def test_python_fastapi(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn")
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
    
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "python"
    assert res["package_manager"] == "pip"
    assert res["build_command"] is None
    assert "uvicorn main:app" in res["entrypoint"]
    assert res["port"] == 8000
    assert res["confidence"] == "high"

def test_python_flask(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "main.py").write_text("from flask import Flask\napp = Flask(__name__)")
    
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "python"
    assert res["package_manager"] == "pip"
    assert res["build_command"] is None
    assert "flask run" in res["entrypoint"]
    assert res["port"] == 5000
    assert res["confidence"] == "high"

def test_python_bare(tmp_path):
    (tmp_path / "requirements.txt").write_text("")
    (tmp_path / "main.py").write_text("print('hello world')")
    
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "python"
    assert res["entrypoint"] == "python main.py"
    assert res["port"] == 8000
    assert res["confidence"] == "high"

def test_node_with_start(tmp_path):
    pkg = {
        "name": "test",
        "scripts": {
            "build": "npm run compile",
            "start": "node dist/index.js --port 4040"
        }
    }
    with open(tmp_path / "package.json", "w") as f:
        json.dump(pkg, f)
        
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "node"
    assert res["package_manager"] == "npm"
    assert res["build_command"] == "npm run compile"
    assert res["entrypoint"] == "node dist/index.js --port 4040"
    assert res["port"] == 4040
    assert res["confidence"] == "high"

def test_node_bare(tmp_path):
    pkg = {"name": "test"}
    with open(tmp_path / "package.json", "w") as f:
        json.dump(pkg, f)
        
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "node"
    assert res["entrypoint"] == "node index.js"
    assert res["port"] == 3000
    assert res["confidence"] == "low"

def test_node_yarn(tmp_path):
    pkg = {"name": "test"}
    with open(tmp_path / "package.json", "w") as f:
        json.dump(pkg, f)
    (tmp_path / "yarn.lock").write_text("")
    
    res = detect_stack(str(tmp_path))
    assert res["package_manager"] == "yarn"

def test_static(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Hello</h1>")
    
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "static"
    assert res["port"] == 80
    assert res["entrypoint"] is None
    assert res["build_command"] is None
    assert res["package_manager"] is None
    assert res["confidence"] == "high"

def test_java_wins_over_node(tmp_path):
    (tmp_path / "pom.xml").write_text("<project></project>")
    pkg = {"name": "test"}
    with open(tmp_path / "package.json", "w") as f:
        json.dump(pkg, f)
        
    res = detect_stack(str(tmp_path))
    assert res["stack"] == "java"

def test_empty_folder(tmp_path):
    with pytest.raises(DetectionError):
        detect_stack(str(tmp_path))

def test_unknown(tmp_path):
    (tmp_path / "main.rb").write_text("puts 'hello'")
    with pytest.raises(DetectionError):
        detect_stack(str(tmp_path))
