import os
import re
import sys
import json
import socket
import signal
import zipfile
import tempfile
import shutil
import asyncio
import subprocess
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, status, Depends
from fastapi.responses import Response, PlainTextResponse, JSONResponse
from pydantic import BaseModel

from app.detector import detect_stack, DetectionError
from app.builder import save_build_log
from app.repository import (
    create_app, get_app, update_status, delete_app,
    set_approval_status, set_process_info, touch_last_seen,
)
from app.models import DeployRequest, DeployResponse
from app.db import get_connection
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/deploy", tags=["deploy"])

PROJECTS_DIR = "projects"


def validate_app_name(name: str) -> bool:
    # lowercase, no spaces, 3-40 chars, alphanumeric+hyphens only
    return bool(re.match(r'^[a-z0-9\-]{3,40}$', name))


def update_build_log_path(name: str, log_path: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE apps SET build_log_path = ? WHERE name = ?", (log_path, name))
        conn.commit()
    finally:
        conn.close()


def write_immediate_failure_log(app_name: str, error_text: str) -> str:
    log_content = f"[{datetime.now(timezone.utc).isoformat()}] DEPLOYMENT FAILED\n{error_text}\n"
    log_path = save_build_log(app_name, log_content)
    update_build_log_path(app_name, log_path)
    return log_path


def find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def remove_container(app_name: str, remove_image: bool = False) -> None:
    """
    Subprocess-based replacement for the old Docker remove_container.
    Kills the running subprocess for the app if any.
    """
    app = get_app(app_name)
    if app is None:
        return
    pid = getattr(app, "pid", None)
    if pid and pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def stop_app(app_name: str) -> bool:
    """Kill the subprocess for an app and mark it STOPPED."""
    app = get_app(app_name)
    if app is None:
        return False
    pid = getattr(app, "pid", None)
    if pid and pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        update_status(app_name, "STOPPED", pid=None, process_port=app.process_port)
    except Exception:
        pass
    set_process_info(app_name, None, app.process_port)
    return True


def _build_run_command(stack: str, project_dir: str, port: int):
    """
    Returns (command_list, env) to launch the project, after installing deps.
    Returns (None, None) if the stack is not runnable as a long process (e.g. static).
    """
    env = {**os.environ, "PORT": str(port), "HOST": "0.0.0.0"}
    stack = (stack or "").lower()

    if stack == "python":
        venv_dir = os.path.abspath(os.path.join(project_dir, ".venv"))
        if not os.path.isdir(venv_dir):
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=False)
        py = os.path.join(venv_dir, "bin", "python")
        if not os.path.exists(py):
            py = sys.executable
        req = os.path.join(project_dir, "requirements.txt")
        if os.path.exists(req):
            subprocess.run([py, "-m", "pip", "install", "-r", req], check=False)
        # Detect framework and pick the right runner
        def _read(fname):
            try:
                with open(os.path.join(project_dir, fname)) as f:
                    return f.read()
            except Exception:
                return ""

        for entry in ("main.py", "app.py"):
            if not os.path.exists(os.path.join(project_dir, entry)):
                continue
            src = _read(entry)
            module = entry[:-3]  # "main" or "app"
            if "FastAPI" in src or "fastapi" in src:
                return ([py, "-m", "uvicorn", f"{module}:app", "--host", "0.0.0.0", "--port", str(port)], env)
            if "Flask" in src or "flask" in src:
                flask_env = {**env, "FLASK_APP": entry}
                return ([py, "-m", "flask", "run", "--host", "0.0.0.0", "--port", str(port)], flask_env)
            # Plain Python — run directly (app must respect PORT env var)
            return ([py, entry], env)
        return ([py, "app.py"], env)

    if stack == "node":
        if os.path.exists(os.path.join(project_dir, "package.json")):
            subprocess.run(["npm", "install"], cwd=project_dir, check=False)
        return (["npm", "start"], env)

    # static: serve with Python's built-in HTTP server (cwd=project_dir set by Popen)
    if stack == "static":
        return ([sys.executable, "-m", "http.server", str(port)], env)

    return (None, env)


def _start_subprocess(app_name: str, stack: str, project_dir: str) -> dict:
    """
    Synchronous: install deps + spawn subprocess. Returns dict with pid/port/status.
    """
    port = find_free_port()
    cmd, env = _build_run_command(stack, project_dir, port)
    if cmd is None:
        # Unknown stack — mark running with no process
        update_status(app_name, "RUNNING", internal_port=port, pid=None, process_port=port)
        return {"pid": None, "port": port, "status": "RUNNING"}

    log_path = os.path.join("logs", f"{app_name}.run.log")
    os.makedirs("logs", exist_ok=True)
    logf = open(log_path, "ab")
    try:
        proc = subprocess.Popen(
            cmd, cwd=project_dir, env=env,
            stdout=logf, stderr=logf,
            start_new_session=True,
        )
    except Exception as e:
        update_status(app_name, "FAILED")
        write_immediate_failure_log(app_name, f"Failed to start process: {e}")
        return {"pid": None, "port": port, "status": "FAILED"}

    update_status(app_name, "RUNNING", internal_port=port, pid=proc.pid, process_port=port)
    # Set last_seen so the reaper doesn't kill it immediately as idle
    touch_last_seen(app_name)
    return {"pid": proc.pid, "port": port, "status": "RUNNING"}


async def _deploy_pipeline(app_name: str, project_path: str) -> None:
    """
    Runs in background after /deploy/upload or /deploy/git returns 202.
    Subprocess-based: extract -> detect -> wait for approval (status PENDING_APPROVAL).
    Process is actually started on approval via /deploy/approve.
    """
    log_accumulator = []

    def log_step(msg: str):
        ts = datetime.now(timezone.utc).isoformat()
        log_accumulator.append(f"[{ts}] {msg}\n")

    log_step("Starting deployment pipeline (subprocess runner)...")

    try:
        # Move project into projects/{app_name}/
        dest_dir = os.path.join(PROJECTS_DIR, app_name)
        if os.path.exists(dest_dir):
            try:
                shutil.rmtree(dest_dir)
            except Exception:
                pass
        os.makedirs(PROJECTS_DIR, exist_ok=True)
        try:
            shutil.copytree(project_path, dest_dir)
        except Exception as e:
            log_step(f"Failed to copy project files: {e}")
            update_status(app_name, "FAILED")
            save_build_log(app_name, "".join(log_accumulator))
            return

        # Detect stack
        log_step(f"Detecting stack in path: {dest_dir}")
        try:
            detection = detect_stack(dest_dir)
            conn = get_connection()
            try:
                conn.execute("UPDATE apps SET stack = ? WHERE name = ?", (detection["stack"], app_name))
                conn.commit()
            finally:
                conn.close()
            log_step(f"Detected stack: {detection['stack']} (confidence: {detection['confidence']})")
        except DetectionError as e:
            log_step(f"Detection failed: {e}")
            update_status(app_name, "FAILED")
            save_build_log(app_name, "".join(log_accumulator))
            return

        log_step("Awaiting admin approval. Use POST /deploy/approve/{app_name} to start.")
        update_status(app_name, "PENDING_APPROVAL")
        log_path = save_build_log(app_name, "".join(log_accumulator))
        update_build_log_path(app_name, log_path)

    finally:
        # Cleanup the temp extraction dir (project now lives in projects/)
        if os.path.exists(project_path) and os.path.abspath(project_path) != os.path.abspath(
            os.path.join(PROJECTS_DIR, app_name)
        ):
            try:
                shutil.rmtree(project_path)
            except Exception:
                pass


async def _deploy_from_git(app_name: str, git_url: str) -> None:
    temp_dir = tempfile.mkdtemp(prefix=f"quad-git-{app_name}-")
    log_step_list = [f"[{datetime.now(timezone.utc).isoformat()}] Cloning repository: {git_url}\n"]

    try:
        process = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", git_url, temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="ignore")
                log_step_list.append(f"Git clone failed:\n{error_msg}\n")
                update_status(app_name, "FAILED")
                log_path = save_build_log(app_name, "".join(log_step_list))
                update_build_log_path(app_name, log_path)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            log_step_list.append("Git clone timed out after 60 seconds.\n")
            update_status(app_name, "FAILED")
            log_path = save_build_log(app_name, "".join(log_step_list))
            update_build_log_path(app_name, log_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
    except Exception as e:
        log_step_list.append(f"Git clone wrapper error: {e}\n")
        update_status(app_name, "FAILED")
        log_path = save_build_log(app_name, "".join(log_step_list))
        update_build_log_path(app_name, log_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    await _deploy_pipeline(app_name, temp_dir)


@router.post("/upload", response_model=DeployResponse, status_code=status.HTTP_202_ACCEPTED)
def deploy_upload(
    background_tasks: BackgroundTasks,
    name: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    if not validate_app_name(name):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "App name must be 3-40 lowercase alphanumeric/hyphen characters only.",
                "code": "INVALID_APP_NAME"
            }
        )

    if get_app(name) is not None:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": f"App '{name}' already exists.",
                "code": "DUPLICATE_APP_NAME"
            }
        )

    create_app(name, owner=current_user["sub"])
    update_status(name, "BUILDING")

    temp_dir = tempfile.mkdtemp(prefix=f"quad-zip-{name}-")
    zip_path = os.path.join(temp_dir, "archive.zip")

    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if not zipfile.is_zipfile(zip_path):
            update_status(name, "FAILED")
            write_immediate_failure_log(name, "Uploaded file is not a valid zip archive.")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Uploaded file is not a valid zip archive.",
                    "code": "INVALID_ZIP_FILE"
                }
            )

        extract_dir = os.path.join(temp_dir, "project")
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            if not zip_ref.namelist():
                update_status(name, "FAILED")
                write_immediate_failure_log(name, "Uploaded zip archive is empty.")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": "Uploaded zip archive is empty.",
                        "code": "EMPTY_ZIP_FILE"
                    }
                )
            zip_ref.extractall(extract_dir)

        # If the zip contained a single top-level directory, unwrap it so
        # index.html / package.json sit directly in extract_dir.
        entries = os.listdir(extract_dir)
        if len(entries) == 1:
            sole = os.path.join(extract_dir, entries[0])
            if os.path.isdir(sole):
                for item in os.listdir(sole):
                    shutil.move(os.path.join(sole, item), os.path.join(extract_dir, item))
                os.rmdir(sole)

    except Exception as e:
        update_status(name, "FAILED")
        write_immediate_failure_log(name, f"Failed to extract uploaded archive: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": f"Failed to extract uploaded archive: {e}",
                "code": "ZIP_EXTRACT_ERROR"
            }
        )

    background_tasks.add_task(_deploy_pipeline, name, extract_dir)

    try:
        os.remove(zip_path)
    except Exception:
        pass

    return DeployResponse(
        app_name=name,
        status="BUILDING",
        url=f"{name}.quad.localhost",
        stack=None,
        message="deployment started — poll GET /apps/name for status"
    )


@router.post("/git", response_model=DeployResponse, status_code=status.HTTP_202_ACCEPTED)
def deploy_git(
    payload: DeployRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    name = payload.name
    git_url = payload.git_url

    if not validate_app_name(name):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "App name must be 3-40 lowercase alphanumeric/hyphen characters only.",
                "code": "INVALID_APP_NAME"
            }
        )

    if not git_url:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "git_url parameter is required.",
                "code": "MISSING_GIT_URL"
            }
        )

    if get_app(name) is not None:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": f"App '{name}' already exists.",
                "code": "DUPLICATE_APP_NAME"
            }
        )

    create_app(name, owner=current_user["sub"])
    update_status(name, "BUILDING")

    background_tasks.add_task(_deploy_from_git, name, git_url)

    return DeployResponse(
        app_name=name,
        status="BUILDING",
        url=f"{name}.quad.localhost",
        stack=None,
        message="deployment started — poll GET /apps/name for status"
    )


@router.post("/approve/{app_name}")
def approve_deployment(app_name: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Admin access required.", "code": "FORBIDDEN"}
        )
    app = get_app(app_name)
    if app is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "App not found.", "code": "APP_NOT_FOUND"}
        )

    set_approval_status(app_name, "approved")
    project_dir = os.path.join(PROJECTS_DIR, app_name)
    if not os.path.isdir(project_dir):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Project files not found.", "code": "NO_PROJECT_FILES"}
        )

    stack = app.stack or "static"
    result = _start_subprocess(app_name, stack, project_dir)
    if app.owner:
        try:
            from app.notifications.service import create_notification
            from app.badges.service import check_and_award
            create_notification(app.owner, "deploy_approved", "Deploy approved",
                                f"{app_name} is now live", f"/dev/{app_name}")
            check_and_award(app.owner, "deploy_approved")
        except Exception:
            pass
    return {
        "app_name": app_name,
        "approval_status": "approved",
        "status": result["status"],
        "pid": result["pid"],
        "port": result["port"],
    }


@router.post("/reject/{app_name}")
def reject_deployment(app_name: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Admin access required.", "code": "FORBIDDEN"}
        )
    app = get_app(app_name)
    if app is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "App not found.", "code": "APP_NOT_FOUND"}
        )
    set_approval_status(app_name, "rejected")
    update_status(app_name, "STOPPED")
    if app.owner:
        try:
            from app.notifications.service import create_notification
            create_notification(app.owner, "deploy_rejected", "Deploy rejected",
                                f"{app_name} was rejected")
        except Exception:
            pass
    return {"app_name": app_name, "approval_status": "rejected", "status": "STOPPED"}


@router.post("/start/{app_name}")
def start_deployment(app_name: str, current_user: dict = Depends(get_current_user)):
    app = get_app(app_name)
    if app is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "App not found.", "code": "APP_NOT_FOUND"}
        )
    if app.owner != current_user["sub"] and current_user.get("role") != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Not permitted.", "code": "FORBIDDEN"}
        )
    if app.approval_status != "approved":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "App not approved.", "code": "NOT_APPROVED"}
        )
    result = _start_subprocess(app_name, app.stack, os.path.join(PROJECTS_DIR, app_name))
    return {"app_name": app_name, "status": "RUNNING", **result}


@router.post("/stop/{app_name}")
def stop_deployment(app_name: str, current_user: dict = Depends(get_current_user)):
    app = get_app(app_name)
    if app is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "App not found.", "code": "APP_NOT_FOUND"}
        )
    if app.owner != current_user["sub"] and current_user.get("role") != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Not permitted.", "code": "FORBIDDEN"}
        )
    stop_app(app_name)
    return {"app_name": app_name, "status": "STOPPED"}


@router.get("/files/{app_name}")
async def list_files(app_name: str, current_user=Depends(get_current_user)):
    base = os.path.join(PROJECTS_DIR, app_name)
    if not os.path.exists(base):
        raise HTTPException(404, "Project not found")
    files = []
    for root, dirs, filenames in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', 'venv', '.venv']]
        for f in filenames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base)
            files.append({"path": rel, "type": "file"})
    return {"files": files}


@router.get("/file/{app_name}")
async def read_file(app_name: str, path: str, current_user=Depends(get_current_user)):
    base = os.path.abspath(os.path.join(PROJECTS_DIR, app_name))
    target = os.path.abspath(os.path.join(base, path))
    if not target.startswith(base):
        raise HTTPException(400, "Invalid path")
    if not os.path.exists(target):
        raise HTTPException(404, "File not found")
    with open(target, 'r', errors='replace') as f:
        return {"content": f.read(), "path": path}


@router.post("/file/{app_name}")
async def write_file(app_name: str, body: dict, current_user=Depends(get_current_user)):
    base = os.path.abspath(os.path.join(PROJECTS_DIR, app_name))
    target = os.path.abspath(os.path.join(base, body["path"]))
    if not target.startswith(base):
        raise HTTPException(400, "Invalid path")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w') as f:
        f.write(body["content"])
    return {"ok": True}


@router.get("/{name}/logs", response_class=PlainTextResponse)
def get_logs(name: str):
    app = get_app(name)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    log_path = app.build_log_path
    if not log_path or not os.path.exists(log_path):
        return ""

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read log file: {e}")


@router.delete("/{name}")
def delete_deployment(name: str, current_user: dict = Depends(get_current_user)):
    app = get_app(name)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    if app.owner != current_user["sub"] and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this app."
        )

    try:
        remove_container(name, remove_image=True)
    except Exception:
        pass

    log_path = app.build_log_path

    delete_app(name)

    try:
        from app.ai.ingest import delete_project_index
        delete_project_index(name)
    except Exception:
        pass

    for d in (os.path.join("projects_source", name), os.path.join(PROJECTS_DIR, name)):
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
            except Exception:
                pass

    if log_path and os.path.exists(log_path):
        try:
            os.remove(log_path)
        except Exception:
            pass

    return {"deleted": name}
