import os
import pytest
import tempfile
import datetime
from fastapi.testclient import TestClient
from app import config, db, repository
from app.main import app as quad_app
from app.auth.service import create_user
from app.dsa.service import log_submission, get_submissions, get_dsa_stats, get_dsa_leaderboard

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

def test_dsa_submission_unit():
    create_user("alice", "a@test.com", "password123")
    
    # Check initial
    stats = get_dsa_stats("alice")
    assert stats["dsa_streak"] == 0
    assert stats["dsa_total_solved"] == 0
    
    # Submit problem
    res = log_submission("alice", "two-sum", "Two Sum", "Easy", "My solution notes")
    assert res["new_streak"] == 1
    assert res["total_solved"] == 1
    
    # Submit duplicate problem -> raises
    with pytest.raises(ValueError, match="already solved"):
        log_submission("alice", "two-sum", "Two Sum", "Easy")

def test_streak_logic_unit():
    create_user("bob", "b@test.com", "password123")
    
    # Yesterday
    yesterday = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()
    conn = db.get_connection()
    try:
        conn.execute("UPDATE users SET dsa_streak = 5, dsa_streak_updated = ? WHERE username = ?", (yesterday, "bob"))
        conn.commit()
    finally:
        conn.close()
        
    # Solve today -> streak becomes 6
    res = log_submission("bob", "reverse-string", "Reverse String", "Easy")
    assert res["new_streak"] == 6
    
    # Solve another problem today -> streak stays 6
    res2 = log_submission("bob", "palindrome-number", "Palindrome Number", "Easy")
    assert res2["new_streak"] == 6
    
    # Reset streak: update updated_at to 3 days ago
    three_days_ago = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)).isoformat()
    conn = db.get_connection()
    try:
        conn.execute("UPDATE users SET dsa_streak_updated = ? WHERE username = ?", (three_days_ago, "bob"))
        conn.commit()
    finally:
        conn.close()
        
    # Solve today -> streak resets to 1
    res3 = log_submission("bob", "merge-intervals", "Merge Intervals", "Medium")
    assert res3["new_streak"] == 1

def test_dsa_leaderboard_unit():
    create_user("usr1", "u1@test.com", "password123")
    create_user("usr2", "u2@test.com", "password123")
    create_user("usr3", "u3@test.com", "password123")
    
    # Set streaks and total solved
    conn = db.get_connection()
    try:
        conn.execute("UPDATE users SET dsa_streak = 5, dsa_total_solved = 10 WHERE username = 'usr1'")
        conn.execute("UPDATE users SET dsa_streak = 10, dsa_total_solved = 15 WHERE username = 'usr2'")
        # usr3 has same streak but more total solved than usr1
        conn.execute("UPDATE users SET dsa_streak = 5, dsa_total_solved = 20 WHERE username = 'usr3'")
        conn.commit()
    finally:
        conn.close()
        
    leaderboard = get_dsa_leaderboard()
    # Find matching records by username since leaderboard might include users from previous fixtures/tests
    usr_records = [u for u in leaderboard if u["username"] in ("usr1", "usr2", "usr3")]
    assert usr_records[0]["username"] == "usr2" # streak 10
    assert usr_records[1]["username"] == "usr3" # streak 5, total 20
    assert usr_records[2]["username"] == "usr1" # streak 5, total 10

# ==================== API TESTS ====================

def test_dsa_endpoints_api():
    client = TestClient(quad_app)
    # Register/Login
    client.post("/auth/register", json={"username": "user1", "email": "u1@test.com", "password": "password123"})
    login_resp = client.post("/auth/login", json={"username_or_email": "user1", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Submit problem
    resp = client.post(
        "/dsa/submit",
        headers=headers,
        json={"problem_slug": "two-sum", "problem_title": "Two Sum", "difficulty": "Easy", "notes": "Hash map"}
    )
    assert resp.status_code == 201
    assert resp.json()["new_streak"] == 1
    
    # Get Stats
    resp = client.get("/dsa/stats/user1")
    assert resp.status_code == 200
    assert resp.json()["dsa_streak"] == 1
    assert resp.json()["difficulty_distribution"]["Easy"] == 1
    
    # Get Submissions
    resp = client.get("/dsa/submissions/user1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["problem_slug"] == "two-sum"
    
    # Get Leaderboard
    resp = client.get("/dsa/leaderboard")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert resp.json()[0]["username"] == "user1"
