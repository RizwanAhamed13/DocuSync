from pydantic import BaseModel
from typing import Optional

class AppCreate(BaseModel):
    name: str
    stack: Optional[str] = None

class App(BaseModel):
    id: int
    name: str
    stack: Optional[str] = None
    status: str = "STOPPED"
    container_id: Optional[str] = None
    image_tag: Optional[str] = None
    internal_port: Optional[int] = None
    max_wake_seconds: int = 10
    last_seen: Optional[str] = None
    created_at: str
    build_log_path: Optional[str] = None
    owner: Optional[str] = None
    visibility: str = "public"
    description: Optional[str] = None
    tags: Optional[str] = None
    view_count: int = 0
    upvote_count: int = 0
    pid: Optional[int] = None
    process_port: Optional[int] = None
    approval_status: str = "pending"

    model_config = {
        "from_attributes": True
    }

class DeployRequest(BaseModel):
    name: str
    git_url: Optional[str] = None

class DeployResponse(BaseModel):
    app_name: str
    status: str
    url: str
    stack: Optional[str] = None
    message: str

