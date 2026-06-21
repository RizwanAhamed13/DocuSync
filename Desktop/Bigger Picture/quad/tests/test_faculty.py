import os
import pytest
import tempfile
import zipfile
import shutil
import json
from fastapi.testclient import TestClient
from app import config, db
from app.main import app as quad_app
from app.auth.service import create_user
from app.faculty.similarity import extract_all_code, compute_similarity_matrix, flag_plagiarism
from app.faculty.report import generate_assignment_report, generate_csv_export
from app.ai.worker import handle_submission_analysis

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

def create_mock_project(content_a: str, content_b: str = None) -> str:
    """Creates a temporary zip file containing mock code files."""
    temp_dir = tempfile.mkdtemp()
    
    # Create main.py
    with open(os.path.join(temp_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write(content_a)
        
    if content_b:
        with open(os.path.join(temp_dir, "utils.py"), "w", encoding="utf-8") as f:
            f.write(content_b)
            
    zip_path = os.path.join(tempfile.gettempdir(), f"mock_proj_{os.urandom(4).hex()}.zip")
    with zipfile.ZipFile(zip_path, "w") as zip_ref:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                full_path = os.path.join(root, file)
                zip_ref.write(full_path, arcname=file)
                
    shutil.rmtree(temp_dir)
    return zip_path

# ==================== UNIT TESTS ====================

def test_extract_all_code_and_similarity():
    code_a = """
    # This is a comment
    api_key = "secret_12345"
    def main():
        print("Hello World")
        try:
            do_something()
        except:
            pass
    """
    code_b = """
    // Node-like or simple Python with similar flow
    api_key = "secret_12345"
    def main():
        print("Hello World")
        try:
            do_something()
        except Exception:
            pass
    """
    
    zip_a = create_mock_project(code_a)
    zip_b = create_mock_project(code_b)
    
    # Extract
    extracted_a = tempfile.mkdtemp()
    extracted_b = tempfile.mkdtemp()
    
    with zipfile.ZipFile(zip_a, 'r') as z:
        z.extractall(extracted_a)
    with zipfile.ZipFile(zip_b, 'r') as z:
        z.extractall(extracted_b)
        
    # Test normalization
    norm_a = extract_all_code(extracted_a)
    assert "STR" in norm_a  # string literals replaced
    assert "#" not in norm_a  # comments stripped
    
    # Test matrix
    submissions = [
        {"submission_id": "sub_a", "extracted_path": extracted_a},
        {"submission_id": "sub_b", "extracted_path": extracted_b}
    ]
    matrix = compute_similarity_matrix(submissions)
    assert "sub_a" in matrix
    assert "sub_b" in matrix["sub_a"]
    
    # Test Plagiarism
    flags = flag_plagiarism(matrix, threshold=0.70)
    assert len(flags) > 0
    assert flags[0]["flag"] in ["HIGH", "MEDIUM"]
    
    # Cleanup
    shutil.rmtree(extracted_a)
    shutil.rmtree(extracted_b)
    os.remove(zip_a)
    os.remove(zip_b)

def test_handle_submission_analysis_worker():
    code = """
    import os
    # Config keys
    api_key = "abc123xyz"
    db_password = "supersecretpassword"
    
    def process():
        try:
            data = fetch()
        except:
            pass
    """
    zip_path = create_mock_project(code)
    
    # Insert assignment & submission records
    conn = db.get_connection()
    conn.execute("""
        INSERT INTO assignments (assignment_id, title, created_by, created_at)
        VALUES ('asg-1', 'Assignment 1', 'faculty_user', '2026-06-15 00:00:00')
    """)
    conn.execute("""
        INSERT INTO submissions (submission_id, assignment_id, student_name, submitted_at, zip_path, extracted_path, status)
        VALUES ('sub-1', 'asg-1', 'Alice', '2026-06-15 00:01:00', ?, ?, 'pending')
    """, (zip_path, tempfile.mkdtemp()))
    conn.commit()
    
    # Fetch extracted path
    cursor = conn.execute("SELECT extracted_path FROM submissions WHERE submission_id = 'sub-1'")
    extracted_path = cursor.fetchone()[0]
    
    # Extract to the path
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extracted_path)
    conn.close()
    
    # Run worker job
    job = {
        "app_name": "sub-1",
        "username": "faculty_user",
        "input": {
            "submission_id": "sub-1",
            "extracted_path": extracted_path,
            "assignment_id": "asg-1"
        }
    }
    
    os.environ["MOCK_OLLAMA"] = "1"
    res = handle_submission_analysis(job)
    assert res["status"] == "completed"
    assert res["file_count"] == 1
    assert res["hardcoded_secrets"] >= 1
    assert res["missing_error_handling"] == 1
    assert res["code_quality_score"] < 100
    
    # Check updated database record
    conn = db.get_connection()
    cursor = conn.execute("SELECT * FROM submission_analysis WHERE submission_id = 'sub-1'")
    analysis = dict(cursor.fetchone())
    assert analysis["hardcoded_secrets"] >= 1
    assert analysis["missing_error_handling"] == 1
    assert analysis["code_quality_score"] < 100
    
    cursor = conn.execute("SELECT status FROM submissions WHERE submission_id = 'sub-1'")
    assert cursor.fetchone()[0] == "completed"
    conn.close()
    
    # Cleanup
    shutil.rmtree(extracted_path)
    os.remove(zip_path)

# ==================== API TESTS ====================

def test_faculty_endpoints_api():
    client = TestClient(quad_app)
    
    # Create faculty user
    create_user("faculty1", "f1@test.com", "password123")
    conn = db.get_connection()
    conn.execute("UPDATE users SET role = 'faculty' WHERE username = 'faculty1'")
    conn.commit()
    conn.close()
    
    # Login
    login_resp = client.post("/auth/login", json={"username_or_email": "faculty1", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create Assignment
    asg_payload = {
        "title": "Data Structures",
        "description": "Tree implementation",
        "course_code": "CS-101",
        "batch": "2024",
        "deadline": "2026-06-30 00:00:00",
        "max_score": 100
    }
    resp = client.post("/assignments", headers=headers, json=asg_payload)
    assert resp.status_code == 200
    asg_id = resp.json()["assignment_id"]
    
    # Get Assignment
    resp = client.get(f"/assignments/{asg_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Data Structures"
    
    # Create Submission
    code = "api_key = 'super_secret'"
    zip_path = create_mock_project(code)
    
    with open(zip_path, "rb") as f:
        resp = client.post(
            f"/assignments/{asg_id}/submissions",
            headers=headers,
            data={"student_name": "Bob", "roll_number": "12345"},
            files={"file": ("project.zip", f, "application/zip")}
        )
    assert resp.status_code == 200
    sub_id = resp.json()["submission_id"]
    
    # Grade Submission
    resp = client.post(
        f"/submissions/{sub_id}/grade",
        headers=headers,
        json={"score": 85, "feedback": "Good job, but remove secrets"}
    )
    assert resp.status_code == 200
    assert resp.json()["score"] == 85
    assert resp.json()["status"] == "graded"
    
    # Clean up zip
    os.remove(zip_path)
