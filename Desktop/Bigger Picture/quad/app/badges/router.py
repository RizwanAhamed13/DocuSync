from fastapi import APIRouter
from app.badges.service import get_badges

router = APIRouter(prefix="/badges", tags=["badges"])


@router.get("/{username}")
def list_badges(username: str):
    return get_badges(username)
