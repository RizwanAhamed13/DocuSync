import sqlite3
from datetime import datetime, timezone
from typing import Optional, List
from app.db import get_connection

def insert_team(
    slug: str,
    display_name: str,
    owner_username: str,
    description: Optional[str] = None,
    visibility: str = "private"
) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO teams (slug, display_name, description, owner_username, visibility, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (slug, display_name, description, owner_username, visibility, created_at)
        )
        # Add owner to team_members
        cursor.execute(
            """
            INSERT INTO team_members (team_slug, username, role, joined_at)
            VALUES (?, ?, 'owner', ?)
            """,
            (slug, owner_username, created_at)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM teams WHERE slug = ?", (slug,))
        return dict(cursor.fetchone())
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e) or "slug" in str(e):
            raise ValueError(f"Team with slug '{slug}' already exists.")
        raise e
    finally:
        conn.close()

def get_team_by_slug(slug: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teams WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def insert_member(team_slug: str, username: str, role: str = "member") -> None:
    joined_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO team_members (team_slug, username, role, joined_at)
            VALUES (?, ?, ?, ?)
            """,
            (team_slug, username, role, joined_at)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            raise ValueError(f"User '{username}' is already a member of team '{team_slug}'.")
        raise e
    finally:
        conn.close()

def delete_member(team_slug: str, username: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM team_members WHERE team_slug = ? AND username = ?",
            (team_slug, username)
        )
        conn.commit()
    finally:
        conn.close()

def get_members(team_slug: str) -> List[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, role, joined_at FROM team_members WHERE team_slug = ? ORDER BY joined_at ASC",
            (team_slug,)
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def get_user_teams_list(username: str) -> List[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.* FROM teams t
            JOIN team_members tm ON t.slug = tm.team_slug
            WHERE tm.username = ?
            ORDER BY t.created_at DESC
            """,
            (username,)
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def insert_project(team_slug: str, app_name: str) -> None:
    added_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO project_teams (team_slug, app_name, added_at) VALUES (?, ?, ?)",
            (team_slug, app_name, added_at)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            raise ValueError(f"App '{app_name}' is already linked to team '{team_slug}'.")
        raise e
    finally:
        conn.close()

def delete_project(team_slug: str, app_name: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM project_teams WHERE team_slug = ? AND app_name = ?",
            (team_slug, app_name)
        )
        conn.commit()
    finally:
        conn.close()

def get_team_projects_list(team_slug: str) -> List[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.* FROM apps a
            JOIN project_teams pt ON a.name = pt.app_name
            WHERE pt.team_slug = ?
            ORDER BY pt.added_at DESC
            """,
            (team_slug,)
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
