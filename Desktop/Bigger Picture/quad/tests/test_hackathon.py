import os
import pytest
import tempfile
import datetime
import json
from fastapi.testclient import TestClient
from app import config, db
from app.main import app as quad_app
from app.auth.service import create_user
from app.hackathon import service
from app.hackathon.scoreboard import calculate_scoreboard

@pytest.fixture(autouse=True)
def temp_db():
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    old_db_path = config.DB_PATH
    config.DB_PATH = temp_db_path
    db.init_db()
    
    yield
    
    config.DB_PATH = old_db_path
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)

# ==================== UNIT TESTS ====================

def test_hackathon_creation_and_status():
    now = datetime.datetime.now()
    t_start = (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_end = (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    hack = service.create_hackathon(
        title="CodeFest",
        theme="AI",
        organizer_username="faculty1",
        start_time=t_start,
        end_time=t_end,
        judging_criteria=["Innovation", "Design"],
        max_team_size=3,
        min_team_size=1
    )
    
    assert hack["title"] == "CodeFest"
    assert hack["status"] == "active"
    
    # Check listing
    hacks = service.list_hackathons()
    assert len(hacks) == 1

def test_team_limits_and_members():
    now = datetime.datetime.now()
    t_start = (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_end = (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    hack = service.create_hackathon(
        title="Hack",
        theme="Web3",
        organizer_username="faculty1",
        start_time=t_start,
        end_time=t_end,
        judging_criteria=["Design"],
        max_team_size=2,
        min_team_size=1
    )
    h_id = hack["hackathon_id"]
    
    # Success
    team = service.create_team(h_id, "Devs", "alice", ["alice", "bob"])
    assert team["team_name"] == "Devs"
    assert len(team["members"]) == 2
    
    # Duplicate team name
    with pytest.raises(ValueError, match="already taken"):
        service.create_team(h_id, "Devs", "charlie")
        
    # User already in another team
    with pytest.raises(ValueError, match="already part of another team"):
        service.create_team(h_id, "Designers", "alice")
        
    # Team too big
    with pytest.raises(ValueError, match="Team size must be between"):
        service.create_team(h_id, "Enthusiasts", "charlie", ["charlie", "dave", "eve"])

def test_scoring_and_scoreboard_tie_break():
    now = datetime.datetime.now()
    t_start = (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    t_end = (now + datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    
    hack = service.create_hackathon(
        title="Hackathon 2026",
        theme="Quantum",
        organizer_username="fac1",
        start_time=t_start,
        end_time=t_end,
        judging_criteria=["Tech", "UX"],
        max_team_size=2,
        min_team_size=1
    )
    h_id = hack["hackathon_id"]
    
    # Create two teams
    t1 = service.create_team(h_id, "Alpha", "alice")
    t2 = service.create_team(h_id, "Beta", "bob")
    
    # Submit projects at different times
    # Team Alpha submits project
    service.submit_project(t1["hack_team_id"], "Quantum Crypt", "Safe encryption")
    
    # Team Beta submits project
    service.submit_project(t2["hack_team_id"], "Quantum Leap", "Speed computation")
    
    # Mock submit times in DB to ensure Alpha is earlier than Beta
    conn = db.get_connection()
    conn.execute("UPDATE hack_teams SET submitted_at = '2026-06-15 10:00:00' WHERE team_name = 'Alpha'")
    conn.execute("UPDATE hack_teams SET submitted_at = '2026-06-15 11:00:00' WHERE team_name = 'Beta'")
    conn.commit()
    conn.close()
    
    # Add scores: Total scores tied
    # Alpha: Tech=8, UX=8 -> Total=16
    # Beta: Tech=9, UX=7 -> Total=16
    service.add_score(t1["hack_team_id"], "judge1", "Tech", 8)
    service.add_score(t1["hack_team_id"], "judge1", "UX", 8)
    
    service.add_score(t2["hack_team_id"], "judge1", "Tech", 9)
    service.add_score(t2["hack_team_id"], "judge1", "UX", 7)
    
    scoreboard = calculate_scoreboard(h_id)
    assert len(scoreboard) == 2
    
    # Beta wins tie-break because primary criterion ("Tech") score (9) > Alpha's "Tech" score (8)
    assert scoreboard[0]["team_name"] == "Beta"
    assert scoreboard[1]["team_name"] == "Alpha"

# ==================== API TESTS ====================

def test_hackathon_endpoints_api():
    client = TestClient(quad_app)
    
    # Register & login as faculty
    create_user("fac-judge", "f@test.com", "password123")
    conn = db.get_connection()
    conn.execute("UPDATE users SET role = 'faculty' WHERE username = 'fac-judge'")
    conn.commit()
    conn.close()
    
    login_resp = client.post("/auth/login", json={"username_or_email": "fac-judge", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    now = datetime.datetime.now()
    t_start = (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_end = (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Create Hackathon
    hack_payload = {
        "title": "Summer Hack",
        "theme": "Education",
        "start_time": t_start,
        "end_time": t_end,
        "judging_criteria": ["Impact", "Tech"],
        "max_team_size": 4,
        "min_team_size": 1
    }
    resp = client.post("/hackathons", headers=headers, json=hack_payload)
    assert resp.status_code == 200
    h_id = resp.json()["hackathon_id"]
    
    # Create Team
    resp = client.post(f"/hackathons/{h_id}/teams", headers=headers, json={"team_name": "Coders"})
    assert resp.status_code == 200
    t_id = resp.json()["hack_team_id"]
    
    # Submit Project
    resp = client.post(f"/teams/{t_id}/submit", headers=headers, json={
        "project_title": "Quad Learn",
        "project_description": "LMS system"
    })
    assert resp.status_code == 200
    assert resp.json()["project_title"] == "Quad Learn"
    
    # Score Project
    resp = client.post(f"/teams/{t_id}/score", headers=headers, json={
        "criterion": "Impact",
        "score": 10,
        "comment": "Mind blowing!"
    })
    assert resp.status_code == 200
    assert resp.json()["score"] == 10
    
    # Get Scoreboard
    resp = client.get(f"/hackathons/{h_id}/scoreboard", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["team_name"] == "Coders"
    assert resp.json()[0]["total_score"] == 10.0
    
    # Live Scoreboard Stream (SSE)
    resp = client.get(f"/hackathons/{h_id}/scoreboard/live?once=true", headers=headers)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert resp.text.startswith("data: ")
