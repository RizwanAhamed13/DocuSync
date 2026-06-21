import os
import re
import uuid
import random
import string
import requests
from requests.auth import HTTPBasicAuth
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import BASE_DOMAIN
from app.tunnel_repo import (
    create_tunnel,
    get_tunnel,
    get_tunnel_by_subdomain,
    list_tunnels,
    close_tunnel,
    delete_tunnel,
    ping_tunnel
)
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/tunnels", tags=["tunnels"])

class TunnelOpenRequest(BaseModel):
    app_name: str
    local_port: int
    owner: Optional[str] = None

class TunnelResponse(BaseModel):
    tunnel_id: str
    subdomain: str
    public_url: str
    frpc_config: str
    connect_command: str

def validate_tunnel_name(name: str) -> bool:
    return bool(re.match(r'^[a-z0-9\-]{3,40}$', name))

def get_frpc_template() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "tunnel", "client", "frpc-template.toml")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return (
        "serverAddr = \"{server_host}\"\n"
        "serverPort = {server_port}\n"
        "auth.token = \"{frp_token}\"\n\n"
        "[[proxies]]\n"
        "name = \"{frpc_name}\"\n"
        "type = \"http\"\n"
        "localPort = {local_port}\n"
        "customDomains = [\"{subdomain}.{base_domain}\"]\n"
    )

@router.post("/open", response_model=TunnelResponse, status_code=status.HTTP_201_CREATED)
def open_tunnel(payload: TunnelOpenRequest, current_user: dict = Depends(get_current_user)):
    app_name = payload.app_name
    local_port = payload.local_port
    owner = current_user["sub"]

    if not validate_tunnel_name(app_name):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "App name must be 3-40 lowercase alphanumeric/hyphen characters only.",
                "code": "INVALID_APP_NAME"
            }
        )

    if not (1 <= local_port <= 65535):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Local port must be between 1 and 65535.",
                "code": "INVALID_PORT"
            }
        )

    # Sanitize owner
    owner_sanitized = re.sub(r'[^a-z0-9\-]', '', owner.lower()).strip('-')
    if not owner_sanitized:
        owner_sanitized = "user"

    subdomain = f"{owner_sanitized}-{app_name}"
    
    # Check uniqueness of subdomain — delete inactive tunnel with same subdomain, or add suffix if active
    existing = get_tunnel_by_subdomain(subdomain)
    if existing:
        if existing["status"].lower() == "active":
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            subdomain = f"{subdomain}-{suffix}"
        else:
            delete_tunnel(existing["tunnel_id"])

    tunnel_uuid = str(uuid.uuid4())
    # frpc name must be unique
    frpc_name = f"quad-{tunnel_uuid[:8]}"

    # Save to SQLite
    tunnel_data = create_tunnel(
        app_name=app_name,
        owner=owner,
        local_port=local_port,
        subdomain=subdomain,
        frpc_name=frpc_name
    )
    # The returned create_tunnel creates a new uuid4 internally but we can query it
    tunnel_id = tunnel_data["tunnel_id"]

    # Render config
    frp_token = os.getenv("FRP_TOKEN", "changeme-set-in-env")
    frp_server_port = int(os.getenv("FRP_SERVER_PORT", "7000"))
    
    # Server host for client connection: if BASE_DOMAIN is quad.localhost, client connects to localhost
    server_host = "localhost" if "localhost" in BASE_DOMAIN else BASE_DOMAIN

    template = get_frpc_template()
    frpc_config = template.format(
        server_host=server_host,
        server_port=frp_server_port,
        frp_token=frp_token,
        frpc_name=frpc_name,
        local_port=local_port,
        subdomain=subdomain,
        base_domain=BASE_DOMAIN
    )

    public_url = f"http://{subdomain}.{BASE_DOMAIN}"
    connect_cmd = f"quad share --port {local_port} --token {frp_token}"

    from app.social.activity import emit_event
    emit_event(owner, "tunnel_open", "tunnel", subdomain)

    return TunnelResponse(
        tunnel_id=tunnel_id,
        subdomain=subdomain,
        public_url=public_url,
        frpc_config=frpc_config,
        connect_command=connect_cmd
    )

def get_frps_proxies_info() -> dict:
    frp_server_host = os.getenv("TUNNEL_SERVER_HOST", "quad-tunnel-server")
    url = f"http://{frp_server_host}:7500/api/proxy/http"
    try:
        resp = requests.get(url, auth=HTTPBasicAuth("admin", "admin"), timeout=2)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}

def enrich_tunnel_data(t: dict, active_proxies: list) -> dict:
    t_copy = dict(t)
    t_copy["bandwidth_in"] = 0
    t_copy["bandwidth_out"] = 0
    t_copy["cur_conns"] = 0
    
    found = False
    for p in active_proxies:
        if p["name"] == t["frpc_name"]:
            found = True
            t_copy["status"] = "active" if p["status"] == "online" else "inactive"
            t_copy["bandwidth_in"] = p.get("today_traffic_in", 0)
            t_copy["bandwidth_out"] = p.get("today_traffic_out", 0)
            t_copy["cur_conns"] = p.get("cur_conns", 0)
            break
            
    if not found:
        from datetime import datetime, timezone
        lping = t.get("last_ping")
        if lping and t["status"] == "ACTIVE":
            try:
                lping_dt = datetime.fromisoformat(lping)
                if lping_dt.tzinfo is None:
                    lping_dt = lping_dt.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - lping_dt).total_seconds()
                if elapsed < 300:
                    t_copy["status"] = "active"
                else:
                    t_copy["status"] = "inactive"
            except Exception:
                t_copy["status"] = "inactive"
        else:
            t_copy["status"] = "inactive"
    return t_copy

@router.post("/{tunnel_id}/ping")
def ping(tunnel_id: str):
    t = get_tunnel(tunnel_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found")
    ping_tunnel(tunnel_id)
    return {"ok": True}

@router.get("/{tunnel_id}/ping")
def get_ping_status(tunnel_id: str):
    t = get_tunnel(tunnel_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found")
    
    info = get_frps_proxies_info()
    proxies = info.get("proxies", [])
    is_online = False
    for p in proxies:
        if p["name"] == t["frpc_name"]:
            is_online = p["status"] == "online"
            if is_online:
                ping_tunnel(tunnel_id)
            break
    return {"online": is_online, "status": "active" if is_online else "inactive"}

@router.post("/{tunnel_id}/close")
def close(tunnel_id: str, current_user: dict = Depends(get_current_user)):
    t = get_tunnel(tunnel_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found")
    if t["owner"] != current_user["sub"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    close_tunnel(tunnel_id)
    
    from app.social.activity import emit_event
    emit_event(current_user["sub"], "tunnel_close", "tunnel", t["subdomain"])
    return {"closed": tunnel_id}

@router.get("")
def list_active_tunnels(owner: Optional[str] = None):
    tlist = list_tunnels(owner)
    info = get_frps_proxies_info()
    proxies = info.get("proxies", [])
    return [enrich_tunnel_data(t, proxies) for t in tlist]

@router.get("/{tunnel_id}")
def get_single_tunnel(tunnel_id: str):
    t = get_tunnel(tunnel_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found")
    info = get_frps_proxies_info()
    proxies = info.get("proxies", [])
    return enrich_tunnel_data(t, proxies)
