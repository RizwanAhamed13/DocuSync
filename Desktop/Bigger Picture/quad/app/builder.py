import os
import re
import time
import docker
from dataclasses import dataclass
from typing import Optional

class BuildError(Exception):
    pass

@dataclass
class BuildResult:
    success: bool
    image_tag: Optional[str]
    log: str               # full captured build output, always populated
    error: Optional[str]   # None on success, error message on failure
    duration_seconds: float

def get_docker_client() -> docker.DockerClient:
    """
    Instantiate client inside a get_docker_client() function
    that raises BuildError with a clear message if the Docker daemon is not reachable.
    """
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        raise BuildError(f"Docker daemon is not reachable: {e}")

def sanitize_app_name(name: str) -> str:
    """
    Lowercase, replace spaces and underscores with hyphens,
    strip any character that is not a-z, 0-9, or hyphen,
    strip leading/trailing hyphens.
    "My App_2" → "my-app-2"
    "___test___" → "test"
    """
    name = name.lower()
    # Replace spaces and underscores with hyphens
    name = re.sub(r'[\s_]+', '-', name)
    # Strip any character that is not a-z, 0-9, or hyphen
    name = re.sub(r'[^a-z0-9\-]', '', name)
    # Strip leading/trailing hyphens
    name = name.strip('-')
    return name

def get_image_tag(app_name: str) -> str:
    """Returns "quad-<sanitized_app_name>:latest" """
    return f"quad-{sanitize_app_name(app_name)}:latest"

def write_build_files(
    project_path: str,
    dockerfile_content: str,
    dockerignore_content: str,
) -> None:
    """
    Write Dockerfile and .dockerignore to project_path.
    Creates project_path if it does not exist.
    Raises BuildError if write fails.
    """
    try:
        os.makedirs(project_path, exist_ok=True)
        
        dockerfile_path = os.path.join(project_path, "Dockerfile")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_content)
            
        dockerignore_path = os.path.join(project_path, ".dockerignore")
        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(dockerignore_content)
    except Exception as e:
        raise BuildError(f"Failed to write build files to '{project_path}': {e}")

def save_build_log(app_name: str, log: str, log_dir: str = "./logs") -> str:
    """
    Save log to ./logs/quad-<app_name>-build.log
    Create log_dir if it does not exist.
    Return the full path to the saved log file.
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
        sanitized = sanitize_app_name(app_name)
        log_path = os.path.join(log_dir, f"quad-{sanitized}-build.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(log)
        return os.path.abspath(log_path)
    except Exception as e:
        raise BuildError(f"Failed to save build log: {e}")

def build_image(
    project_path: str,
    app_name: str,
    dockerfile_content: str,
    dockerignore_content: str,
) -> BuildResult:
    """
    1. Write dockerfile_content to <project_path>/Dockerfile (overwrite if exists)
    2. Write dockerignore_content to <project_path>/.dockerignore (overwrite if exists)
    3. Build the image using docker SDK low-level API (client.api.build)
       so we get a stream of build events
    4. Stream and capture all build log lines
    5. Return BuildResult
    """
    # Raise BuildError if docker daemon is unreachable
    client = get_docker_client()
    
    # Write Dockerfile and .dockerignore
    write_build_files(project_path, dockerfile_content, dockerignore_content)
    
    sanitized = sanitize_app_name(app_name)
    image_tag = get_image_tag(sanitized)
    
    log_accumulator = []
    success = True
    error_msg = None
    
    start_time = time.time()
    try:
        stream = client.api.build(
            path=project_path,
            tag=image_tag,
            dockerfile="Dockerfile",
            decode=True,
            rm=True
        )
        
        for event in stream:
            if "stream" in event:
                log_accumulator.append(event["stream"])
            if "status" in event:
                progress = event.get("progress", "")
                log_accumulator.append(f"{event['status']} {progress}\n")
            if "errorDetail" in event:
                detail = event["errorDetail"]
                log_accumulator.append(f"Error detail: {detail.get('message', '')}\n")
            if "error" in event:
                success = False
                error_msg = event["error"]
                log_accumulator.append(f"Build failed: {error_msg}\n")
                
    except Exception as e:
        success = False
        error_msg = str(e)
        log_accumulator.append(f"Build failed with exception: {error_msg}\n")
        
    duration = time.time() - start_time
    full_log = "".join(log_accumulator)
    
    if success:
        return BuildResult(
            success=True,
            image_tag=image_tag,
            log=full_log,
            error=None,
            duration_seconds=duration
        )
    else:
        return BuildResult(
            success=False,
            image_tag=None,
            log=full_log,
            error=error_msg,
            duration_seconds=duration
        )
