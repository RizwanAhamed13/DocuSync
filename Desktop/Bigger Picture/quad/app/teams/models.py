from pydantic import BaseModel, Field
from typing import Optional, List
from app.models import App

class TeamCreate(BaseModel):
    slug: str = Field(..., min_length=3, max_length=40, pattern=r"^[a-z0-9\-]+$")
    display_name: str
    description: Optional[str] = None
    visibility: str = "private"

class TeamMemberInfo(BaseModel):
    username: str
    role: str
    joined_at: str

class TeamDetailResponse(BaseModel):
    slug: str
    display_name: str
    description: Optional[str] = None
    owner_username: str
    visibility: str
    created_at: str
    members: List[TeamMemberInfo] = []
    projects: List[App] = []

    model_config = {
        "from_attributes": True
    }

class MemberAddRequest(BaseModel):
    username: str
    role: str = "member" # "owner" | "member" | "viewer"

class ProjectAddRequest(BaseModel):
    app_name: str
