import re
from typing import Optional, List
from app.db import get_connection
from app.teams import repo

def user_exists(username: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def create_team(
    slug: str,
    display_name: str,
    owner_username: str,
    description: Optional[str] = None,
    visibility: str = "private"
) -> dict:
    # Validate slug: 3-40 chars, lowercase alphanumeric + hyphens
    if not slug or len(slug) < 3 or len(slug) > 40:
        raise ValueError("Team slug must be between 3 and 40 characters.")
    if not re.match(r"^[a-z0-9\-]+$", slug):
        raise ValueError("Team slug must contain only lowercase alphanumeric characters and hyphens.")
    if visibility not in ("public", "private"):
        raise ValueError("Visibility must be 'public' or 'private'.")

    return repo.insert_team(slug, display_name, owner_username, description, visibility)

def get_team(slug: str) -> Optional[dict]:
    return repo.get_team_by_slug(slug)

def add_member(team_slug: str, username: str, role: str = "member") -> None:
    # Check team exists
    team = repo.get_team_by_slug(team_slug)
    if not team:
        raise ValueError(f"Team '{team_slug}' not found.")
    
    # Check user exists
    if not user_exists(username):
        raise ValueError(f"User '{username}' not found.")
        
    # Check if user already in team
    members = repo.get_members(team_slug)
    if any(m["username"] == username for m in members):
        raise ValueError(f"User '{username}' is already in team '{team_slug}'.")
        
    repo.insert_member(team_slug, username, role)

def remove_member(team_slug: str, username: str) -> None:
    team = repo.get_team_by_slug(team_slug)
    if not team:
        raise ValueError(f"Team '{team_slug}' not found.")
        
    if team["owner_username"] == username:
        raise ValueError("Cannot remove the team owner.")
        
    repo.delete_member(team_slug, username)

def list_members(team_slug: str) -> List[dict]:
    return repo.get_members(team_slug)

def list_user_teams(username: str) -> List[dict]:
    return repo.get_user_teams_list(username)

def add_project(team_slug: str, app_name: str) -> None:
    # check team exists
    team = repo.get_team_by_slug(team_slug)
    if not team:
        raise ValueError(f"Team '{team_slug}' not found.")
        
    # check app exists
    from app.repository import get_app
    app = get_app(app_name)
    if not app:
        raise ValueError(f"App '{app_name}' not found.")
        
    repo.insert_project(team_slug, app_name)

def remove_project(team_slug: str, app_name: str) -> None:
    repo.delete_project(team_slug, app_name)

def list_team_projects(team_slug: str) -> List[dict]:
    return repo.get_team_projects_list(team_slug)
