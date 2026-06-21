from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List

from app.auth.dependencies import get_current_user
from app.social.upvotes import upvote_app, unupvote_app
from app.social.forks import fork_project
from app.social.activity import get_activity_feed

router = APIRouter(prefix="/social", tags=["social"])

class ForkRequest(BaseModel):
    original_app: str
    forked_app: str

@router.post("/upvotes/{app_name}", status_code=status.HTTP_200_OK)
def upvote(app_name: str, current_user: dict = Depends(get_current_user)):
    try:
        upvote_app(current_user["sub"], app_name)
        return {"ok": True, "message": "App upvoted successfully."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/upvotes/{app_name}", status_code=status.HTTP_200_OK)
def unupvote(app_name: str, current_user: dict = Depends(get_current_user)):
    try:
        unupvote_app(current_user["sub"], app_name)
        return {"ok": True, "message": "Upvote removed successfully."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/forks", status_code=status.HTTP_202_ACCEPTED)
def fork(
    payload: ForkRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    # Validate target app name format
    from app.deploy import validate_app_name
    if not validate_app_name(payload.forked_app):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Forked app name must be 3-40 lowercase alphanumeric/hyphen characters only."
        )
        
    try:
        fork_project(
            original_app_name=payload.original_app,
            forked_app_name=payload.forked_app,
            forked_by=current_user["sub"],
            background_tasks=background_tasks
        )
        return {
            "ok": True,
            "message": "Fork deployment started.",
            "forked_app": payload.forked_app
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/activity", response_model=List[dict])
def list_activity(limit: int = 50, offset: int = 0):
    return get_activity_feed(limit=limit, offset=offset)

@router.get("/upvotes", response_model=List[str])
def get_user_upvotes(current_user: dict = Depends(get_current_user)):
    from app.db import get_connection
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT app_name FROM upvotes WHERE username = ?", (current_user["sub"],))
        return [row["app_name"] for row in cursor.fetchall()]
    finally:
        conn.close()
