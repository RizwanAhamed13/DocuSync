from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.teams.models import TeamCreate, TeamDetailResponse, MemberAddRequest, ProjectAddRequest
from app.teams import service

router = APIRouter(prefix="/teams", tags=["teams"])

@router.post("", status_code=status.HTTP_201_CREATED)
def create_new_team(payload: TeamCreate, current_user: dict = Depends(get_current_user)):
    try:
        team = service.create_team(
            slug=payload.slug,
            display_name=payload.display_name,
            owner_username=current_user["sub"],
            description=payload.description,
            visibility=payload.visibility
        )
        from app.social.activity import emit_event
        emit_event(current_user["sub"], "team_create", "team", payload.slug)
        return team
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("", response_model=List[dict])
def list_my_teams(current_user: dict = Depends(get_current_user)):
    return service.list_user_teams(current_user["sub"])

@router.get("/{slug}", response_model=TeamDetailResponse)
def get_team_detail(slug: str, current_user: dict = Depends(get_current_user)):
    team = service.get_team(slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Team '{slug}' not found.")
        
    members = service.list_members(slug)
    is_member = any(m["username"] == current_user["sub"] for m in members)
    
    if team["visibility"] == "private" and not is_member and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to private team.")
        
    projects = service.list_team_projects(slug)
    
    # Cast/construct the detailed response structure
    return {
        "slug": team["slug"],
        "display_name": team["display_name"],
        "description": team["description"],
        "owner_username": team["owner_username"],
        "visibility": team["visibility"],
        "created_at": team["created_at"],
        "members": members,
        "projects": projects
    }

@router.post("/{slug}/members", status_code=status.HTTP_201_CREATED)
def add_team_member(
    slug: str,
    payload: MemberAddRequest,
    current_user: dict = Depends(get_current_user)
):
    team = service.get_team(slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
        
    # Require current_user is owner or admin
    if team["owner_username"] != current_user["sub"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner or an admin can add members.")
        
    try:
        service.add_member(slug, payload.username, payload.role)
        from app.social.activity import emit_event
        emit_event(current_user["sub"], "team_join", "team", slug, {"joined_username": payload.username})
        try:
            from app.badges.service import check_and_award
            from app.notifications.service import create_notification
            check_and_award(payload.username, "team_joined")
            create_notification(payload.username, "team_invite", "Added to a team",
                                f"You were added to team {team['display_name']}", f"/teams")
        except Exception:
            pass
        return service.list_members(slug)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/{slug}/members/{username}")
def remove_team_member(
    slug: str,
    username: str,
    current_user: dict = Depends(get_current_user)
):
    team = service.get_team(slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
        
    # Require current_user is owner or admin, or removing themselves
    is_self = current_user["sub"] == username
    if team["owner_username"] != current_user["sub"] and current_user.get("role") != "admin" and not is_self:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
        
    try:
        service.remove_member(slug, username)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{slug}/projects", status_code=status.HTTP_201_CREATED)
def add_team_project(
    slug: str,
    payload: ProjectAddRequest,
    current_user: dict = Depends(get_current_user)
):
    team = service.get_team(slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
        
    # Requester must be a member of the team
    members = service.list_members(slug)
    is_member = any(m["username"] == current_user["sub"] for m in members)
    if not is_member and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must be a team member to link projects.")
        
    # Requester must own the app (or be admin)
    from app.repository import get_app
    app = get_app(payload.app_name)
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.")
        
    if app.owner != current_user["sub"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must own the application to link it.")
        
    try:
        service.add_project(slug, payload.app_name)
        return service.list_team_projects(slug)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/{slug}/projects/{app_name}")
def remove_team_project(
    slug: str,
    app_name: str,
    current_user: dict = Depends(get_current_user)
):
    team = service.get_team(slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
        
    # Require owner of team or admin
    if team["owner_username"] != current_user["sub"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
        
    service.remove_project(slug, app_name)
    return {"ok": True}
