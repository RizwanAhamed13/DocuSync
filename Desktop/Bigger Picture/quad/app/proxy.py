import asyncio
import httpx
import time
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from app.repository import get_app, touch_last_seen
from app.container import start_container, ContainerError

_wake_locks: dict[str, asyncio.Lock] = {}
_wake_locks_mutex: asyncio.Lock = asyncio.Lock()

async def get_wake_lock(app_name: str) -> asyncio.Lock:
    """
    Return the per-app asyncio lock, creating it if it does not exist.
    Thread-safe via _wake_locks_mutex.
    """
    async with _wake_locks_mutex:
        if app_name not in _wake_locks:
            _wake_locks[app_name] = asyncio.Lock()
        return _wake_locks[app_name]

MAX_WAKE_WAIT = {
    "java":   20,
    "python": 10,
    "node":   8,
    "static": 5,
}
DEFAULT_WAKE_WAIT = 10

async def wake_and_wait(app_name: str, stack: str) -> bool:
    """
    Acquire the per-app lock.
    Re-check app status inside the lock.
    If still STOPPED: call start_container(app_name) in a thread executor.
    Poll until host_port responds to HTTP GET / with any status code.
    Returns True if app is reachable, False if timed out.
    """
    max_wait = MAX_WAKE_WAIT.get(stack, DEFAULT_WAKE_WAIT)
    lock = await get_wake_lock(app_name)

    async with lock:
        app = get_app(app_name)
        if app is None:
            return False
        if app.status == "RUNNING":
            return True

        loop = asyncio.get_event_loop()
        # Subprocess-managed apps: use deploy.start_app, not Docker start_container
        from app.deploy import _start_subprocess, PROJECTS_DIR
        import os
        project_dir = os.path.join(PROJECTS_DIR, app_name)
        if os.path.isdir(project_dir):
            try:
                await loop.run_in_executor(
                    None, _start_subprocess, app_name, app.stack or "static", project_dir
                )
            except Exception:
                return False
        else:
            try:
                await loop.run_in_executor(None, start_container, app_name)
            except ContainerError:
                return False

        app = get_app(app_name)
        if app is None or app.internal_port is None:
            return False

        deadline = time.monotonic() + max_wait
        async with httpx.AsyncClient() as client:
            while time.monotonic() < deadline:
                try:
                    r = await client.get(
                        f"http://localhost:{app.internal_port}/",
                        timeout=1.0
                    )
                    if r.status_code < 600:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        return False

async def proxy_request(request: Request, host_port: int, host: str = "localhost",
                        forward_host: str | None = None) -> Response:
    """
    Forward the incoming request to http://<host>:<host_port>.
    forward_host: if set, overrides the Host header sent to the upstream (needed for frps routing).
    """
    HOP_BY_HOP = {
        "connection", "keep-alive", "transfer-encoding",
        "te", "trailers", "upgrade", "proxy-authorization",
        "proxy-authenticate"
    }

    url = httpx.URL(
        scheme="http",
        host=host,
        port=host_port,
        path=request.url.path,
        query=request.url.query.encode("utf-8"),
    )

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP and k.lower() != "host"
    }
    if forward_host:
        headers["host"] = forward_host

    body = await request.body()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
                follow_redirects=False,
            )
    except httpx.ConnectError:
        return Response("app is not responding", status_code=502)
    except Exception as e:
        return Response(f"proxy connection failed: {e}", status_code=502)

    response_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in HOP_BY_HOP
    }

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
    )

def waking_page(app_name: str, stack: str) -> HTMLResponse:
    """
    Return HTMLResponse shown while container is starting.
    Must include meta-refresh every 3 seconds.
    Under 1KB.
    """
    html_content = f"""<!doctype html>
<html>
<head>
<meta http-equiv="refresh" content="3">
<title>Starting {app_name}</title>
</head>
<body style="font-family:sans-serif;text-align:center;padding:50px;">
<h2>{app_name} is starting...</h2>
<p>Please wait while the {stack} container boots up.</p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=503)

def extract_app_name(host: str) -> str | None:
    """
    myapp.quad.localhost:8000 -> myapp
    Split on '.', first segment is app_name if there are 3+ segments.
    """
    if not host:
        return None
    h = host.split(":")[0]
    parts = h.split(".")
    if len(parts) >= 3:
        return parts[0]
    return None

router = APIRouter()

import os

@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
)
async def proxy_handler(request: Request, path: str) -> Response:
    host = request.headers.get("host", "")
    app_name = extract_app_name(host)
    if app_name is None:
        return HTMLResponse("app not found", status_code=404)

    app = get_app(app_name)
    if app is None:
        # Check if active tunnel exists
        from app.tunnel_repo import get_tunnel_by_subdomain
        tunnel = get_tunnel_by_subdomain(app_name)
        if tunnel and tunnel["status"] == "ACTIVE":
            # Proxy to the tunnel server (defaulting to localhost or quad-tunnel-server)
            tunnel_host = os.getenv("TUNNEL_SERVER_HOST", "localhost")
            from app.tunnel_repo import ping_tunnel
            try:
                ping_tunnel(tunnel["tunnel_id"])
            except Exception:
                pass
            original_host = request.headers.get("host", "").split(":")[0]
            return await proxy_request(request, 7080, host=tunnel_host, forward_host=original_host)
        return HTMLResponse("app not found", status_code=404)

    if app.status == "RUNNING":
        if not app.internal_port:
            return waking_page(app_name, app.stack or "static")
        touch_last_seen(app_name)
        resp = await proxy_request(request, app.internal_port)
        # If port not yet accepting connections, show waking page instead of error
        if resp.status_code == 502 and resp.body in (b"app is not responding", b""):
            return waking_page(app_name, app.stack or "static")
        return resp

    elif app.status == "STOPPED":
        asyncio.create_task(wake_and_wait(app_name, app.stack or "static"))
        return waking_page(app_name, app.stack or "static")

    elif app.status == "BUILDING":
        return HTMLResponse("app is building, try again shortly", status_code=503)

    elif app.status == "FAILED":
        return HTMLResponse("app failed to start — check build logs", status_code=503)

    else:
        return HTMLResponse("service unavailable", status_code=503)
