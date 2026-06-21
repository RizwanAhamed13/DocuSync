import os
import re
import json

class DetectionError(Exception):
    pass

def list_root_files(project_path: str) -> list[str]:
    """Return a list of filenames (not full paths) in the root of project_path."""
    if not os.path.exists(project_path):
        raise DetectionError(f"Directory {project_path} does not exist.")
    if not os.path.isdir(project_path):
        raise DetectionError(f"Path {project_path} is not a directory.")
    try:
        items = os.listdir(project_path)
    except Exception as e:
        raise DetectionError(f"Failed to list directory {project_path}: {e}")
    
    return [f for f in items if os.path.isfile(os.path.join(project_path, f))]

def read_json_safe(file_path: str) -> dict:
    """Read a JSON file; return {} on any error."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def extract_port_from_entrypoint(entrypoint: str) -> int:
    """Detect port number from entrypoint string if mentioned, else default to 3000."""
    # Check for --port <num> or -p <num>
    m = re.search(r'(?:--port|-p)\s+(\d+)', entrypoint)
    if m:
        return int(m.group(1))
    # Check for PORT=<num>
    m = re.search(r'\bPORT\s*=\s*(\d+)', entrypoint)
    if m:
        return int(m.group(1))
    # Check for generic port word followed by a number
    m = re.search(r'port\D*(\d+)', entrypoint, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 3000

def detect_stack(project_path: str) -> dict:
    """
    Inspect the folder at project_path and return:
    {
        "stack":            "static" | "node" | "python" | "java",
        "entrypoint":       str | None,   # detected start command
        "port":             int,          # default port for this stack
        "build_command":    str | None,   # e.g. "npm run build", None if not needed
        "package_manager":  str | None,   # "npm" | "yarn" | "pip" | "maven" | "gradle" | None
        "confidence":       "high" | "low",
        "notes":            str           # human-readable explanation of what was found
    }
    Raises DetectionError if the folder doesn't exist or is empty.
    """
    if not os.path.exists(project_path):
        raise DetectionError(f"Path '{project_path}' does not exist.")
    if not os.path.isdir(project_path):
        raise DetectionError(f"Path '{project_path}' is not a directory.")
    
    try:
        all_items = os.listdir(project_path)
    except Exception as e:
        raise DetectionError(f"Could not read directory '{project_path}': {e}")
        
    if not all_items:
        raise DetectionError(f"Directory '{project_path}' is empty.")

    # Build a dictionary mapping lowercase names to their original cases
    root_items = {item.lower(): item for item in all_items}

    # 1. JAVA detection
    is_java = False
    pkg_mgr = None
    build_cmd = None
    matched_file = None

    if "pom.xml" in root_items:
        is_java = True
        pkg_mgr = "maven"
        build_cmd = "mvn package -DskipTests"
        matched_file = root_items["pom.xml"]
    elif "build.gradle" in root_items:
        is_java = True
        pkg_mgr = "gradle"
        build_cmd = "./gradlew bootJar"
        matched_file = root_items["build.gradle"]
    elif "build.gradle.kts" in root_items:
        is_java = True
        pkg_mgr = "gradle"
        build_cmd = "./gradlew bootJar"
        matched_file = root_items["build.gradle.kts"]

    if is_java:
        jar_path = None
        
        # Check target/ or build/libs/ directories case-insensitively
        target_dir = root_items.get("target")
        if target_dir and os.path.isdir(os.path.join(project_path, target_dir)):
            try:
                for f in os.listdir(os.path.join(project_path, target_dir)):
                    if f.lower().endswith(".jar") and os.path.isfile(os.path.join(project_path, target_dir, f)):
                        jar_path = f"{target_dir}/{f}"
                        break
            except Exception:
                pass
        
        build_dir = root_items.get("build")
        if not jar_path and build_dir and os.path.isdir(os.path.join(project_path, build_dir)):
            libs_dir = os.path.join(project_path, build_dir, "libs")
            if os.path.isdir(libs_dir):
                try:
                    for f in os.listdir(libs_dir):
                        if f.lower().endswith(".jar") and os.path.isfile(os.path.join(libs_dir, f)):
                            jar_path = f"{build_dir}/libs/{f}"
                            break
                except Exception:
                    pass

        entrypoint = f"java -jar {jar_path}" if jar_path else None
        
        if jar_path:
            notes = f"Found {matched_file} at root. Java project detected. Jar found at {jar_path}."
        else:
            notes = f"Found {matched_file} at root. Java project detected. No jar found in target/ or build/libs/ yet."

        return {
            "stack": "java",
            "entrypoint": entrypoint,
            "port": 8080,
            "build_command": build_cmd,
            "package_manager": pkg_mgr,
            "confidence": "high",
            "notes": notes
        }

    # 2. PYTHON detection
    is_python = "requirements.txt" in root_items or "pyproject.toml" in root_items or "setup.py" in root_items
    if is_python:
        matched_file = root_items.get("requirements.txt") or root_items.get("pyproject.toml") or root_items.get("setup.py")
        entrypoint = None
        port = 8000
        confidence = "high"
        notes = ""

        # Check in order: main.py, app.py, wsgi.py
        if "main.py" in root_items:
            main_path = os.path.join(project_path, root_items["main.py"])
            content = ""
            try:
                with open(main_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
            except Exception:
                pass

            if "fastapi" in content or "uvicorn" in content:
                entrypoint = "uvicorn main:app --host 0.0.0.0 --port 8000"
                notes = f"Found {matched_file} at root. Python project with FastAPI/Uvicorn detected in main.py."
            elif "flask" in content:
                entrypoint = "flask run --host 0.0.0.0 --port 5000"
                port = 5000
                notes = f"Found {matched_file} at root. Python project with Flask detected in main.py."
            else:
                entrypoint = "python main.py"
                notes = f"Found {matched_file} at root. Python project detected with main.py."
        
        elif "app.py" in root_items:
            app_path = os.path.join(project_path, root_items["app.py"])
            content = ""
            try:
                with open(app_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
            except Exception:
                pass

            if "fastapi" in content or "uvicorn" in content:
                entrypoint = "uvicorn app:app --host 0.0.0.0 --port 8000"
                notes = f"Found {matched_file} at root. Python project with FastAPI/Uvicorn detected in app.py."
            elif "flask" in content:
                entrypoint = "flask run --host 0.0.0.0 --port 5000"
                port = 5000
                notes = f"Found {matched_file} at root. Python project with Flask detected in app.py."
            else:
                entrypoint = "python app.py"
                notes = f"Found {matched_file} at root. Python project detected with app.py."
        
        elif "wsgi.py" in root_items:
            entrypoint = "gunicorn wsgi:application --bind 0.0.0.0:8000"
            notes = f"Found {matched_file} at root. Python project detected with wsgi.py."
        
        else:
            confidence = "low"
            notes = f"Found {matched_file} at root. Python project detected, but no standard entrypoint file (main.py, app.py, wsgi.py) found."

        return {
            "stack": "python",
            "entrypoint": entrypoint,
            "port": port,
            "build_command": None,
            "package_manager": "pip",
            "confidence": confidence,
            "notes": notes
        }

    # 3. NODE detection
    if "package.json" in root_items:
        pkg_json_path = os.path.join(project_path, root_items["package.json"])
        pkg_data = read_json_safe(pkg_json_path)
        pkg_mgr = "yarn" if "yarn.lock" in root_items else "npm"
        scripts = pkg_data.get("scripts", {})
        
        build_cmd = scripts.get("build")
        
        confidence = "high"
        if "start" in scripts:
            entrypoint = scripts["start"]
        elif "dev" in scripts:
            entrypoint = scripts["dev"]
            confidence = "low"
        else:
            entrypoint = "node index.js"
            confidence = "low"

        port = extract_port_from_entrypoint(entrypoint)
        notes = f"Found package.json at root. Node project detected with package manager {pkg_mgr}."

        return {
            "stack": "node",
            "entrypoint": entrypoint,
            "port": port,
            "build_command": build_cmd,
            "package_manager": pkg_mgr,
            "confidence": confidence,
            "notes": notes
        }

    # 4. STATIC detection
    if "index.html" in root_items:
        return {
            "stack": "static",
            "entrypoint": None,
            "port": 80,
            "build_command": None,
            "package_manager": None,
            "confidence": "high",
            "notes": "Found index.html at root. Static website detected."
        }

    # 5. Fallback UNKNOWN
    found_files = list(root_items.values())
    raise DetectionError(
        f"Could not auto-detect stack. Found files/folders: {found_files}. "
        "Expected signals for: Java (pom.xml, build.gradle), "
        "Python (requirements.txt, pyproject.toml, setup.py), "
        "Node (package.json), or Static (index.html)."
    )
