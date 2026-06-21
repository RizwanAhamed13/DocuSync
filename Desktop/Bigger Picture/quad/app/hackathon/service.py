import os
import uuid
import time
import json
import datetime
from app.db import get_connection

def create_hackathon(title: str, theme: str, organizer_username: str,
                     start_time: str, end_time: str, judging_criteria: list[str],
                     max_team_size: int = 4, min_team_size: int = 1) -> dict:
    conn = get_connection()
    hackathon_id = str(uuid.uuid4())
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # Simple validation of times
    try:
        datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback to date check if needed, but standardise on %Y-%m-%d %H:%M:%S
        pass
        
    try:
        conn.execute("""
            INSERT INTO hackathons (
                hackathon_id, title, theme, organizer_username,
                start_time, end_time, judging_criteria, max_team_size,
                min_team_size, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'upcoming', ?)
        """, (
            hackathon_id, title, theme, organizer_username,
            start_time, end_time, json.dumps(judging_criteria), max_team_size,
            min_team_size, now_str
        ))
        conn.commit()
    finally:
        conn.close()
    return get_hackathon(hackathon_id)

def get_hackathon(hackathon_id: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM hackathons WHERE hackathon_id = ?", (hackathon_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        
        # Parse criteria
        try:
            data["judging_criteria"] = json.loads(data["judging_criteria"])
        except Exception:
            data["judging_criteria"] = []
            
        # Dynamically resolve status
        now = datetime.datetime.now()
        start = datetime.datetime.strptime(data["start_time"], "%Y-%m-%d %H:%M:%S")
        end = datetime.datetime.strptime(data["end_time"], "%Y-%m-%d %H:%M:%S")
        
        if now < start:
            data["status"] = "upcoming"
        elif start <= now <= end:
            data["status"] = "active"
        else:
            data["status"] = "ended"
            
        return data
    finally:
        conn.close()

def list_hackathons() -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT hackathon_id FROM hackathons ORDER BY created_at DESC")
        ids = [row["hackathon_id"] for row in cursor.fetchall()]
    finally:
        conn.close()
        
    return [get_hackathon(h_id) for h_id in ids if h_id]

def create_team(hackathon_id: str, team_name: str, leader_username: str,
                members: list[str] = None) -> dict:
    hackathon = get_hackathon(hackathon_id)
    if not hackathon:
        raise ValueError("Hackathon not found.")
        
    if members is None:
        members = [leader_username]
        
    if leader_username not in members:
        members.append(leader_username)
        
    # Check team size limits
    if len(members) < hackathon["min_team_size"] or len(members) > hackathon["max_team_size"]:
        raise ValueError(f"Team size must be between {hackathon['min_team_size']} and {hackathon['max_team_size']}.")
        
    # Check if any member is already in a team for this hackathon
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT members FROM hack_teams WHERE hackathon_id = ?", (hackathon_id,))
        existing_teams = cursor.fetchall()
        for t in existing_teams:
            try:
                t_members = json.loads(t["members"])
            except Exception:
                t_members = []
            for m in members:
                if m in t_members:
                    raise ValueError(f"User {m} is already part of another team in this hackathon.")
                    
        # Check team name uniqueness for this hackathon
        cursor = conn.execute("SELECT 1 FROM hack_teams WHERE hackathon_id = ? AND team_name = ?", (hackathon_id, team_name))
        if cursor.fetchone():
            raise ValueError(f"Team name '{team_name}' is already taken.")
            
        hack_team_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO hack_teams (
                hack_team_id, hackathon_id, team_name, members, leader_username
            ) VALUES (?, ?, ?, ?, ?)
        """, (hack_team_id, hackathon_id, team_name, json.dumps(members), leader_username))
        conn.commit()
    finally:
        conn.close()
        
    return get_team(hack_team_id)

def get_team(hack_team_id: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM hack_teams WHERE hack_team_id = ?", (hack_team_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["members"] = json.loads(data["members"])
        except Exception:
            data["members"] = []
        return data
    finally:
        conn.close()

def list_teams(hackathon_id: str) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT hack_team_id FROM hack_teams WHERE hackathon_id = ?", (hackathon_id,))
        ids = [row["hack_team_id"] for row in cursor.fetchall()]
    finally:
        conn.close()
    return [get_team(t_id) for t_id in ids if t_id]

def submit_project(hack_team_id: str, project_title: str, project_description: str,
                   app_name: str = None, demo_url: str = None, repo_url: str = None) -> dict:
    team = get_team(hack_team_id)
    if not team:
        raise ValueError("Team not found.")
        
    conn = get_connection()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            UPDATE hack_teams 
            SET project_title = ?, project_description = ?, app_name = ?,
                demo_url = ?, repo_url = ?, submitted_at = ?
            WHERE hack_team_id = ?
        """, (project_title, project_description, app_name, demo_url, repo_url, now_str, hack_team_id))
        conn.commit()
    finally:
        conn.close()
    return get_team(hack_team_id)

def add_score(hack_team_id: str, judge_username: str, criterion: str, score: int, comment: str = None) -> dict:
    team = get_team(hack_team_id)
    if not team:
        raise ValueError("Team not found.")
        
    hackathon = get_hackathon(team["hackathon_id"])
    if not hackathon:
        raise ValueError("Hackathon not found.")
        
    if criterion not in hackathon["judging_criteria"]:
        raise ValueError(f"Invalid criterion. Must be one of: {hackathon['judging_criteria']}")
        
    if score < 0 or score > 10:
        raise ValueError("Score must be between 0 and 10.")
        
    conn = get_connection()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT OR REPLACE INTO hack_scores (
                hack_team_id, judge_username, criterion, score, comment, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (hack_team_id, judge_username, criterion, score, comment, now_str))
        conn.commit()
    finally:
        conn.close()
        
    return {"status": "success", "hack_team_id": hack_team_id, "judge": judge_username, "criterion": criterion, "score": score}

def get_team_scores(hack_team_id: str) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM hack_scores WHERE hack_team_id = ?", (hack_team_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
