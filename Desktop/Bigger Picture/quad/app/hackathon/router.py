import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from app.auth.dependencies import get_current_user
from app.hackathon import service
from app.hackathon.scoreboard import calculate_scoreboard

router = APIRouter(tags=["hackathon"])

class HackathonCreate(BaseModel):
    title: str
    theme: Optional[str] = None
    start_time: str
    end_time: str
    judging_criteria: List[str]
    max_team_size: Optional[int] = 4
    min_team_size: Optional[int] = 1

class TeamCreate(BaseModel):
    team_name: str
    members: Optional[List[str]] = None

class ProjectSubmit(BaseModel):
    project_title: str
    project_description: str
    app_name: Optional[str] = None
    demo_url: Optional[str] = None
    repo_url: Optional[str] = None

class ScorePayload(BaseModel):
    criterion: str
    score: int
    comment: Optional[str] = None

def check_faculty(user: dict):
    if user.get("role") not in ["faculty", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )

@router.post("/hackathons")
def create_hackathon_endpoint(
    payload: HackathonCreate,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    return service.create_hackathon(
        title=payload.title,
        theme=payload.theme,
        organizer_username=current_user["sub"],
        start_time=payload.start_time,
        end_time=payload.end_time,
        judging_criteria=payload.judging_criteria,
        max_team_size=payload.max_team_size,
        min_team_size=payload.min_team_size
    )

@router.get("/hackathons")
def list_hackathons_endpoint(current_user: dict = Depends(get_current_user)):
    return service.list_hackathons()

@router.get("/hackathons/{hackathon_id}")
def get_hackathon_endpoint(
    hackathon_id: str,
    current_user: dict = Depends(get_current_user)
):
    hack = service.get_hackathon(hackathon_id)
    if not hack:
        raise HTTPException(status_code=404, detail="Hackathon not found")
    return hack

@router.post("/hackathons/{hackathon_id}/teams")
def create_team_endpoint(
    hackathon_id: str,
    payload: TeamCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        return service.create_team(
            hackathon_id=hackathon_id,
            team_name=payload.team_name,
            leader_username=current_user["sub"],
            members=payload.members
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/hackathons/{hackathon_id}/teams")
def list_teams_endpoint(
    hackathon_id: str,
    current_user: dict = Depends(get_current_user)
):
    return service.list_teams(hackathon_id)

@router.post("/hackathons/{hackathon_id}/register")
def register_team_endpoint(
    hackathon_id: str,
    payload: TeamCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        return service.create_team(
            hackathon_id=hackathon_id,
            team_name=payload.team_name,
            leader_username=current_user["sub"],
            members=payload.members
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class HackathonSubmit(BaseModel):
    team_id: str
    title: str
    description: str
    app_name: Optional[str] = None
    demo_url: Optional[str] = None
    repo_url: Optional[str] = None


@router.post("/hackathons/{hackathon_id}/submit")
def hackathon_submit_endpoint(
    hackathon_id: str,
    payload: HackathonSubmit,
    current_user: dict = Depends(get_current_user)
):
    team = service.get_team(payload.team_id)
    if not team or team["hackathon_id"] != hackathon_id:
        raise HTTPException(status_code=404, detail="Team not found in this hackathon")
    if current_user["sub"] not in team["members"]:
        raise HTTPException(status_code=403, detail="You are not a member of this team")
    try:
        return service.submit_project(
            hack_team_id=payload.team_id,
            project_title=payload.title,
            project_description=payload.description,
            app_name=payload.app_name,
            demo_url=payload.demo_url,
            repo_url=payload.repo_url
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hackathons/{hackathon_id}/score/{team_id}")
def hackathon_score_endpoint(
    hackathon_id: str,
    team_id: str,
    payload: ScorePayload,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    try:
        return service.add_score(
            hack_team_id=team_id,
            judge_username=current_user["sub"],
            criterion=payload.criterion,
            score=payload.score,
            comment=payload.comment
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/teams/{hack_team_id}/submit")
def submit_project_endpoint(
    hack_team_id: str,
    payload: ProjectSubmit,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Check if user is on team
        team = service.get_team(hack_team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        if current_user["sub"] not in team["members"]:
            raise HTTPException(status_code=403, detail="You are not a member of this team")
            
        return service.submit_project(
            hack_team_id=hack_team_id,
            project_title=payload.project_title,
            project_description=payload.project_description,
            app_name=payload.app_name,
            demo_url=payload.demo_url,
            repo_url=payload.repo_url
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/teams/{hack_team_id}/score")
def score_project_endpoint(
    hack_team_id: str,
    payload: ScorePayload,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    try:
        return service.add_score(
            hack_team_id=hack_team_id,
            judge_username=current_user["sub"],
            criterion=payload.criterion,
            score=payload.score,
            comment=payload.comment
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/hackathons/{hackathon_id}/scoreboard")
def get_scoreboard_endpoint(
    hackathon_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        return calculate_scoreboard(hackathon_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/hackathons/{hackathon_id}/scoreboard/live")
async def sse_scoreboard_endpoint(
    hackathon_id: str,
    once: bool = False,
    current_user: dict = Depends(get_current_user)
):
    # Verify hackathon exists
    hack = service.get_hackathon(hackathon_id)
    if not hack:
        raise HTTPException(status_code=404, detail="Hackathon not found")
        
    async def sse_generator():
        try:
            while True:
                scores = calculate_scoreboard(hackathon_id)
                yield f"data: {json.dumps(scores)}\n\n"
                if once:
                    break
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            # Clean disconnect
            pass
            
    return StreamingResponse(sse_generator(), media_type="text/event-stream")
