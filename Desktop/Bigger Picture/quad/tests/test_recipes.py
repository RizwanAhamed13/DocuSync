import pytest
from app.recipes import generate_dockerfile, generate_dockerignore, to_exec_form, RecipeError

def test_static():
    detection = {
        "stack": "static",
        "port": 80
    }
    output = generate_dockerfile(detection)
    assert isinstance(output, str)
    assert len(output) > 0
    assert "nginx:alpine" in output
    assert "EXPOSE 80" in output
    assert 'CMD ["nginx", "-g", "daemon off;"]' in output

def test_node_without_build():
    detection = {
        "stack": "node",
        "build_command": None,
        "package_manager": "npm",
        "entrypoint": "node server.js",
        "port": 3000
    }
    output = generate_dockerfile(detection)
    assert "node:20-alpine" in output
    assert "npm install --production" in output
    assert '["node", "server.js"]' in output
    assert "AS builder" not in output

def test_node_with_build():
    detection = {
        "stack": "node",
        "build_command": "npm run build",
        "package_manager": "npm",
        "entrypoint": "node server.js",
        "port": 3000
    }
    output = generate_dockerfile(detection)
    assert "AS builder" in output
    assert "npm run build" in output

def test_node_yarn():
    detection = {
        "stack": "node",
        "package_manager": "yarn",
        "build_command": None,
        "entrypoint": "node index.js",
        "port": 3000
    }
    output = generate_dockerfile(detection)
    assert "yarn install" in output

def test_python_uvicorn():
    detection = {
        "stack": "python",
        "entrypoint": "uvicorn main:app --host 0.0.0.0 --port 8000",
        "port": 8000,
        "package_manager": "pip",
        "notes": "Found requirements.txt at root."
    }
    output = generate_dockerfile(detection)
    assert "python:3.11-slim" in output
    assert "uvicorn" in output
    assert "EXPOSE 8000" in output

def test_python_flask():
    detection = {
        "stack": "python",
        "entrypoint": "flask run --host 0.0.0.0 --port 5000",
        "port": 5000,
        "package_manager": "pip",
        "notes": "Found requirements.txt at root."
    }
    output = generate_dockerfile(detection)
    assert "EXPOSE 5000" in output

def test_python_no_entrypoint():
    detection = {
        "stack": "python",
        "entrypoint": None,
        "port": 8000,
        "package_manager": "pip",
        "notes": "Found requirements.txt at root."
    }
    output = generate_dockerfile(detection)
    assert "WARNING" in output
    assert '["python", "main.py"]' in output

def test_java_maven():
    detection = {
        "stack": "java",
        "package_manager": "maven",
        "port": 8080
    }
    output = generate_dockerfile(detection)
    assert "maven:3.9" in output
    assert "mvn package" in output
    assert "eclipse-temurin:21-jre-alpine" in output
    assert "app.jar" in output

def test_java_gradle():
    detection = {
        "stack": "java",
        "package_manager": "gradle",
        "port": 8080
    }
    output = generate_dockerfile(detection)
    assert "gradle:8-jdk21" in output
    assert "bootJar" in output
    assert "eclipse-temurin:21-jre-alpine" in output

def test_exec_form_simple():
    assert to_exec_form("node server.js") == '["node", "server.js"]'

def test_exec_form_with_flags():
    assert to_exec_form('uvicorn main:app --host 0.0.0.0 --port 8000') == '["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'

def test_unknown_stack():
    detection = {
        "stack": "ruby",
        "port": 3000
    }
    with pytest.raises(RecipeError):
        generate_dockerfile(detection)

def test_dockerignore_node():
    output = generate_dockerignore({"stack": "node"})
    assert "node_modules" in output

def test_dockerignore_python():
    output = generate_dockerignore({"stack": "python"})
    assert "__pycache__" in output
