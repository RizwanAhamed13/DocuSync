import os
import time
import datetime
import docker
from dataclasses import dataclass
from typing import Optional, List
from app.db import get_connection
from app.repository import update_status, get_app
from app.builder import get_docker_client, sanitize_app_name, BuildError

PORT_RANGE_START = 9000
PORT_RANGE_END   = 9999

class ContainerError(Exception):
    pass

def _extract_ports(container) -> tuple[int, int]:
    ports_dict = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    if not ports_dict:
        ports_dict = container.attrs.get("HostConfig", {}).get("PortBindings") or {}
    host_port = 0
    internal_port = 0
    for int_p, bindings in ports_dict.items():
        if bindings:
            host_port = int(bindings[0].get("HostPort", 0))
            internal_port = int(int_p.split("/")[0])
            break
    return host_port, internal_port

@dataclass
class ContainerInfo:
    app_name: str
    container_id: str        # full 64-char ID
    container_name: str      # "quad-<app_name>"
    status: str              # RUNNING | STOPPED | FAILED | REMOVED
    internal_port: int
    host_port: int           # dynamically assigned by Docker
    started_at: Optional[str]   # ISO timestamp, None if not running
    error: Optional[str]

def get_next_available_port() -> int:
    """
    Query SQLite apps table for all internal_port values currently in use.
    Find the lowest port in PORT_RANGE_START..PORT_RANGE_END not in that set.
    Raises ContainerError if all ports are exhausted.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        cursor = conn.cursor()
        cursor.execute("SELECT internal_port FROM apps WHERE internal_port IS NOT NULL")
        used_ports = {row["internal_port"] for row in cursor.fetchall()}
        conn.commit()
        for p in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            if p not in used_ports:
                return p
        raise ContainerError("All ports in range 9000-9999 are exhausted.")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        if isinstance(e, ContainerError):
            raise e
        raise ContainerError(f"Failed to allocate port: {e}")
    finally:
        conn.close()

def get_container_name(app_name: str) -> str:
    return f"quad-{sanitize_app_name(app_name)}"

def create_and_start_container(
    app_name: str,
    image_tag: str,
    internal_port: int,
) -> ContainerInfo:
    """
    1. Sanitize app_name.
    2. Check if a container named "quad-<app_name>" already exists.
    3. Call get_next_available_port() to get host_port.
    4. Create AND start container.
    5. Wait for container to be "running".
    6. If container exits before becoming running → status=FAILED, capture logs.
    7. On success: update_status and return.
    """
    sanitized = sanitize_app_name(app_name)
    c_name = get_container_name(sanitized)
    
    try:
        client = get_docker_client()
    except Exception as e:
        raise ContainerError(f"Docker connection error: {e}")
        
    try:
        # Check if container already exists
        existing = None
        try:
            existing = client.containers.get(c_name)
        except docker.errors.NotFound:
            pass
            
        if existing:
            raise ContainerError("container already exists")
            
        host_port = get_next_available_port()
        
        container = client.containers.run(
            image_tag,
            name=c_name,
            ports={f"{internal_port}/tcp": host_port},
            labels={"quad": "true", "quad_app": sanitized},
            detach=True,
            restart_policy={"Name": "no"},
        )
    except docker.errors.DockerException as e:
        if "container already exists" in str(e) or "Conflict" in str(e):
            raise ContainerError("container already exists")
        raise ContainerError(f"Docker API error: {e}")
    except ContainerError as e:
        raise e
    except Exception as e:
        raise ContainerError(f"Container run failed: {e}")

    # Determine max wait seconds based on stack type
    app_record = get_app(sanitized)
    stack = app_record.stack if app_record else None
    
    if stack == "java" or "java" in image_tag.lower():
        max_wait = 15
    elif stack in ("node", "python") or any(s in image_tag.lower() for s in ("node", "python")):
        max_wait = 8
    elif stack == "static" or "static" in image_tag.lower():
        max_wait = 3
    else:
        max_wait = 8
        
    start_time = time.time()
    container_status = "STOPPED"
    error_msg = None
    started_at_str = None
    
    while time.time() - start_time < max_wait:
        try:
            container.reload()
        except docker.errors.DockerException as e:
            raise ContainerError(f"Failed to reload container status: {e}")
            
        status = container.status.lower()
        if status == "running":
            container_status = "RUNNING"
            started_at_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            break
        elif status in ("exited", "dead"):
            container_status = "FAILED"
            try:
                error_msg = container.logs().decode("utf-8", errors="ignore")
            except Exception:
                error_msg = f"Container terminated with status {status}"
            break
        time.sleep(0.5)
        
    if container_status == "STOPPED":
        # Timed out waiting
        container_status = "FAILED"
        error_msg = "Timed out waiting for container to start."
        
    # Sync to SQLite
    status_to_store = container_status
    update_status(
        sanitized, 
        status_to_store, 
        container_id=container.id, 
        image_tag=image_tag, 
        internal_port=host_port
    )
    
    return ContainerInfo(
        app_name=sanitized,
        container_id=container.id,
        container_name=c_name,
        status=container_status,
        internal_port=internal_port,
        host_port=host_port,
        started_at=started_at_str,
        error=error_msg
    )

def stop_container(app_name: str) -> ContainerInfo:
    """
    1. Find container by name "quad-<app_name>".
       Raise ContainerError if not found.
    2. If already stopped: update_status(app_name, "STOPPED"), return early.
    3. container.stop(timeout=10)
    4. update_status(app_name, "STOPPED")
    5. Return ContainerInfo with status=STOPPED.
    """
    sanitized = sanitize_app_name(app_name)
    c_name = get_container_name(sanitized)
    
    try:
        client = get_docker_client()
        container = client.containers.get(c_name)
    except docker.errors.NotFound:
        raise ContainerError(f"Container '{c_name}' not found.")
    except Exception as e:
        raise ContainerError(f"Docker error: {e}")
        
    status = container.status.lower()
    
    # Extract config ports
    host_port, internal_port = _extract_ports(container)
            
    if status not in ("running", "restarting"):
        update_status(sanitized, "STOPPED")
        return ContainerInfo(
            app_name=sanitized,
            container_id=container.id,
            container_name=c_name,
            status="STOPPED",
            internal_port=internal_port,
            host_port=host_port,
            started_at=None,
            error=None
        )
        
    try:
        container.stop(timeout=10)
        update_status(sanitized, "STOPPED")
    except docker.errors.DockerException as e:
        raise ContainerError(f"Failed to stop container: {e}")
        
    return ContainerInfo(
        app_name=sanitized,
        container_id=container.id,
        container_name=c_name,
        status="STOPPED",
        internal_port=internal_port,
        host_port=host_port,
        started_at=None,
        error=None
    )

def start_container(app_name: str) -> ContainerInfo:
    """
    1. Find container by name "quad-<app_name>".
       Raise ContainerError if not found.
    2. If already running: return current ContainerInfo.
    3. container.start()
    4. Wait for running status.
    5. update_status(app_name, "RUNNING")
    6. Return ContainerInfo.
    """
    sanitized = sanitize_app_name(app_name)
    c_name = get_container_name(sanitized)
    
    try:
        client = get_docker_client()
        container = client.containers.get(c_name)
    except docker.errors.NotFound:
        raise ContainerError(f"Container '{c_name}' not found.")
    except Exception as e:
        raise ContainerError(f"Docker error: {e}")
        
    # Extract config ports
    host_port, internal_port = _extract_ports(container)

    status = container.status.lower()
    if status == "running":
        started_at_str = container.attrs.get("State", {}).get("StartedAt")
        return ContainerInfo(
            app_name=sanitized,
            container_id=container.id,
            container_name=c_name,
            status="RUNNING",
            internal_port=internal_port,
            host_port=host_port,
            started_at=started_at_str,
            error=None
        )
        
    try:
        container.start()
    except docker.errors.DockerException as e:
        raise ContainerError(f"Failed to start container: {e}")
        
    # Wait for running status
    app_record = get_app(sanitized)
    stack = app_record.stack if app_record else None
    image_tag = container.attrs.get("Config", {}).get("Image", "")
    
    if stack == "java" or "java" in image_tag.lower():
        max_wait = 15
    elif stack in ("node", "python") or any(s in image_tag.lower() for s in ("node", "python")):
        max_wait = 8
    elif stack == "static" or "static" in image_tag.lower():
        max_wait = 3
    else:
        max_wait = 8
        
    start_time = time.time()
    container_status = "STOPPED"
    error_msg = None
    started_at_str = None
    
    while time.time() - start_time < max_wait:
        try:
            container.reload()
        except docker.errors.DockerException as e:
            raise ContainerError(f"Failed to reload container status: {e}")
            
        st = container.status.lower()
        if st == "running":
            container_status = "RUNNING"
            started_at_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            break
        elif st in ("exited", "dead"):
            container_status = "FAILED"
            try:
                error_msg = container.logs().decode("utf-8", errors="ignore")
            except Exception:
                error_msg = f"Container terminated with status {st}"
            break
        time.sleep(0.5)
        
    if container_status == "STOPPED":
        container_status = "FAILED"
        error_msg = "Timed out waiting for container to start."
        
    if container_status == "RUNNING":
        host_port, internal_port = _extract_ports(container)
        
    update_status(
        sanitized, 
        container_status, 
        container_id=container.id, 
        image_tag=image_tag, 
        internal_port=host_port
    )
    
    return ContainerInfo(
        app_name=sanitized,
        container_id=container.id,
        container_name=c_name,
        status=container_status,
        internal_port=internal_port,
        host_port=host_port,
        started_at=started_at_str,
        error=error_msg
    )

def remove_container(app_name: str, remove_image: bool = False) -> None:
    """
    1. Find container by name "quad-<app_name>".
       If not found: no-op (idempotent).
    2. Stop if running.
    3. container.remove()
    4. If remove_image=True: find image by tag and remove it.
    5. update_status(app_name, "STOPPED", None, None, None)
    """
    sanitized = sanitize_app_name(app_name)
    c_name = get_container_name(sanitized)
    
    try:
        client = get_docker_client()
    except Exception:
        # If docker daemon is unreachable, stop/remove cannot run
        return
        
    try:
        container = client.containers.get(c_name)
    except docker.errors.NotFound:
        # Idempotency: update SQL anyways to clean up state
        if get_app(sanitized):
            update_status(sanitized, "STOPPED", container_id=None, image_tag=None, internal_port=None)
        return
        
    try:
        if container.status.lower() in ("running", "restarting"):
            container.stop(timeout=5)
        image_tag = container.attrs.get("Config", {}).get("Image")
        container.remove()
        
        if remove_image and image_tag:
            try:
                client.images.remove(image_tag, force=True)
            except Exception:
                pass
                
        if get_app(sanitized):
            update_status(sanitized, "STOPPED", container_id=None, image_tag=None, internal_port=None)
    except docker.errors.DockerException as e:
        raise ContainerError(f"Failed to remove container: {e}")

def get_container_info(app_name: str) -> Optional[ContainerInfo]:
    """
    Find container by name "quad-<app_name>".
    Return ContainerInfo reflecting current live Docker status.
    Return None if container does not exist.
    Sync status back to SQLite if it differs.
    """
    sanitized = sanitize_app_name(app_name)
    c_name = get_container_name(sanitized)
    
    try:
        client = get_docker_client()
        container = client.containers.get(c_name)
    except docker.errors.NotFound:
        # Sync status to STOPPED if DB is in another state
        app_record = get_app(sanitized)
        if app_record and app_record.status != "STOPPED":
            update_status(sanitized, "STOPPED", container_id=None, image_tag=None, internal_port=None)
        return None
    except Exception as e:
        raise ContainerError(f"Docker error: {e}")
        
    # Extract config ports
    host_port, internal_port = _extract_ports(container)
            
    status = container.status.lower()
    container_status = "STOPPED"
    started_at_str = None
    
    if status == "running":
        container_status = "RUNNING"
        started_at_str = container.attrs.get("State", {}).get("StartedAt")
    elif status == "dead":
        container_status = "FAILED"
    else:
        container_status = "STOPPED"
        
    # Sync status back to SQLite if differs
    app_record = get_app(sanitized)
    if app_record and app_record.status != container_status:
        update_status(
            sanitized, 
            container_status, 
            container_id=container.id, 
            image_tag=container.attrs.get("Config", {}).get("Image"), 
            internal_port=host_port if container_status != "STOPPED" else None
        )
        
    return ContainerInfo(
        app_name=sanitized,
        container_id=container.id,
        container_name=c_name,
        status=container_status,
        internal_port=internal_port,
        host_port=host_port,
        started_at=started_at_str,
        error=None
    )

def get_container_logs(app_name: str, tail: int = 100) -> str:
    """
    Return the last `tail` lines of runtime logs from the container.
    Return empty string if container not found.
    """
    sanitized = sanitize_app_name(app_name)
    c_name = get_container_name(sanitized)
    
    try:
        client = get_docker_client()
        container = client.containers.get(c_name)
        return container.logs(tail=tail).decode("utf-8", errors="ignore")
    except docker.errors.NotFound:
        return ""
    except Exception as e:
        raise ContainerError(f"Docker error: {e}")

def list_quad_containers() -> List[ContainerInfo]:
    """
    List all containers with label {"quad": "true"}.
    Return their ContainerInfo list.
    """
    try:
        client = get_docker_client()
        containers = client.containers.list(all=True, filters={"label": "quad=true"})
    except Exception as e:
        raise ContainerError(f"Docker error: {e}")
        
    results = []
    for c in containers:
        labels = c.labels
        app_name = labels.get("quad_app", c.name.replace("quad-", ""))
        
        # Extract ports
        host_port, internal_port = _extract_ports(c)
                
        status = c.status.lower()
        container_status = "STOPPED"
        started_at_str = None
        
        if status == "running":
            container_status = "RUNNING"
            started_at_str = c.attrs.get("State", {}).get("StartedAt")
        elif status == "dead":
            container_status = "FAILED"
            
        results.append(ContainerInfo(
            app_name=app_name,
            container_id=c.id,
            container_name=c.name,
            status=container_status,
            internal_port=internal_port,
            host_port=host_port,
            started_at=started_at_str,
            error=None
        ))
    return results

def sync_container_status(app_name: str) -> None:
    """
    Read container's actual status from Docker.
    If it differs from SQLite, update SQLite.
    Subprocess-managed apps (pid set) are synced via PID check, not Docker.
    """
    sanitized = sanitize_app_name(app_name)

    # Subprocess-managed apps: check PID liveness, not Docker
    from app.repository import get_app as _get_app
    from app.deploy import pid_alive
    app_record = _get_app(sanitized)
    if app_record and app_record.pid:
        if not pid_alive(app_record.pid):
            if app_record.status == "RUNNING":
                update_status(sanitized, "STOPPED", pid=None, process_port=None, internal_port=None)
        return

    c_name = get_container_name(sanitized)

    try:
        client = get_docker_client()
        container = client.containers.get(c_name)
        status = container.status.lower()
        
        host_port, _ = _extract_ports(container)
                
        if status == "running":
            db_status = "RUNNING"
        elif status == "dead":
            db_status = "FAILED"
        else:
            db_status = "STOPPED"
            
        app_record = get_app(sanitized)
        if app_record and app_record.status != db_status:
            update_status(
                sanitized, 
                db_status, 
                container_id=container.id, 
                image_tag=container.attrs.get("Config", {}).get("Image"),
                internal_port=host_port if db_status != "STOPPED" else None
            )
    except docker.errors.NotFound:
        # Container not found → status = STOPPED
        app_record = get_app(sanitized)
        if app_record and app_record.status != "STOPPED":
            update_status(sanitized, "STOPPED", container_id=None, image_tag=None, internal_port=None)
    except Exception as e:
        raise ContainerError(f"Failed to sync container status: {e}")
