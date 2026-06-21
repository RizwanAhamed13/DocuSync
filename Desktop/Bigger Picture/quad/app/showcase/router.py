from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import List, Optional

from app.auth.dependencies import get_current_user
from app.auth.service import get_user_by_username
from app.showcase import service

router = APIRouter(prefix="/showcase", tags=["showcase"])

class MetadataPatchRequest(BaseModel):
    visibility: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None

@router.get("", response_model=List[dict])
def list_public_apps(
    query: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    return service.get_public_apps(query=query, tag=tag, limit=limit, offset=offset)

@router.get("/leaderboard", response_model=List[dict])
def get_showcase_leaderboard(sort_by: str = "upvotes", limit: int = 10):
    if sort_by not in ("upvotes", "views"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_by parameter must be either 'upvotes' or 'views'."
        )
    return service.get_leaderboard(sort_by=sort_by, limit=limit)

@router.patch("/{app_name}", response_model=dict)
def patch_app_metadata(
    app_name: str,
    payload: MetadataPatchRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        is_admin = current_user.get("role") == "admin"
        updated = service.update_app_metadata(
            app_name=app_name,
            username=current_user["sub"],
            visibility=payload.visibility,
            description=payload.description,
            tags=payload.tags,
            is_admin=is_admin
        )
        return updated
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{app_name}/view")
def record_app_view(app_name: str, request: Request):
    # Retrieve client IP
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    
    success = service.record_view(app_name, client_ip)
    return {"ok": True, "recorded": success}

@router.get("/users/{username}", response_model=dict)
def get_user_profile_showcase(username: str, request: Request):
    # Verify user exists
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Check if request has Auth header to identify requester
    # We can try to authenticate the user optionally, or just decode if available
    auth_header = request.headers.get("Authorization")
    requester = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        from app.auth.service import decode_token
        try:
            payload = decode_token(token)
            if payload:
                requester = payload.get("sub")
        except Exception:
            pass
            
    # Fetch all apps owned by target user
    from app.db import get_connection
    conn = get_connection()
    try:
        if requester == username or requester == "admin":
            cursor = conn.execute("SELECT * FROM apps WHERE owner = ? ORDER BY created_at DESC", (username,))
        else:
            cursor = conn.execute(
                "SELECT * FROM apps WHERE owner = ? AND visibility = 'public' ORDER BY created_at DESC",
                (username,)
            )
        apps = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
        
    return {
        "user": {
            "username": user["username"],
            "display_name": user["display_name"],
            "avatar_initial": user["avatar_initial"],
            "college": user["college"],
            "department": user["department"],
            "role": user["role"],
            "bio": user["bio"],
            "github_url": user["github_url"],
            "linkedin_url": user["linkedin_url"],
            "dsa_streak": user.get("dsa_streak", 0),
            "dsa_total_solved": user.get("dsa_total_solved", 0)
        },
        "apps": apps
    }
