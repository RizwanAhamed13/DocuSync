import os
import uuid
import time
import zipfile
import shutil
from app.db import get_connection

def create_assignment(title: str, description: str, created_by: str,
                      course_code: str = None, batch: str = None,
                      deadline: str = None, max_score: int = 100) -> dict:
    conn = get_connection()
    assignment_id = str(uuid.uuid4())
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO assignments (
                assignment_id, title, description, created_by,
                course_code, batch, deadline, max_score, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """, (assignment_id, title, description, created_by, course_code, batch, deadline, max_score, now_str))
        conn.commit()
    finally:
        conn.close()
    return get_assignment(assignment_id)

def get_assignment(assignment_id: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM assignments WHERE assignment_id = ?", (assignment_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_assignments(created_by: str = None) -> list[dict]:
    conn = get_connection()
    try:
        if created_by:
            # Query assignment details including submission counts
            cursor = conn.execute("""
                SELECT a.*, COUNT(s.id) as submission_count 
                FROM assignments a
                LEFT JOIN submissions s ON a.assignment_id = s.assignment_id
                WHERE a.created_by = ?
                GROUP BY a.id
                ORDER BY a.created_at DESC
            """, (created_by,))
        else:
            cursor = conn.execute("""
                SELECT a.*, COUNT(s.id) as submission_count 
                FROM assignments a
                LEFT JOIN submissions s ON a.assignment_id = s.assignment_id
                GROUP BY a.id
                ORDER BY a.created_at DESC
            """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def close_assignment(assignment_id: str, faculty_username: str) -> None:
    assignment = get_assignment(assignment_id)
    if not assignment:
        raise ValueError("Assignment not found.")
    if assignment["created_by"] != faculty_username:
        raise PermissionError("Only the creator can close this assignment.")
        
    conn = get_connection()
    try:
        conn.execute("UPDATE assignments SET status = 'closed' WHERE assignment_id = ?", (assignment_id,))
        conn.commit()
    finally:
        conn.close()

def create_submission(assignment_id: str, student_name: str, roll_number: str,
                      zip_path: str, student_username: str = None) -> dict:
    assignment = get_assignment(assignment_id)
    if not assignment:
        raise ValueError("Assignment not found.")
    if assignment["status"] != "open":
        raise ValueError("Assignment is closed for submissions.")
        
    submission_id = str(uuid.uuid4())
    extracted_path = f"projects/submissions/{submission_id}"
    os.makedirs(extracted_path, exist_ok=True)
    
    # Extract zip archive
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extracted_path)
    except Exception as e:
        # cleanup directory
        shutil.rmtree(extracted_path, ignore_errors=True)
        raise ValueError(f"Invalid zip file: {e}")
        
    conn = get_connection()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO submissions (
                submission_id, assignment_id, student_username, student_name,
                roll_number, submitted_at, zip_path, extracted_path, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (submission_id, assignment_id, student_username, student_name, roll_number, now_str, zip_path, extracted_path))
        conn.commit()
    finally:
        conn.close()
        
    return get_submission(submission_id)

def get_submission(submission_id: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT s.*, sa.ai_summary, sa.detected_stack, sa.file_count, sa.line_count,
                   sa.issues, sa.missing_features, sa.hardcoded_secrets, sa.missing_error_handling,
                   sa.code_quality_score, sa.similarity_scores, sa.plagiarism_flag, sa.analyzed_at
            FROM submissions s
            LEFT JOIN submission_analysis sa ON s.submission_id = sa.submission_id
            WHERE s.submission_id = ?
        """, (submission_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_submissions(assignment_id: str) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT s.*, sa.ai_summary, sa.detected_stack, sa.file_count, sa.line_count,
                   sa.issues, sa.missing_features, sa.hardcoded_secrets, sa.missing_error_handling,
                   sa.code_quality_score, sa.similarity_scores, sa.plagiarism_flag, sa.analyzed_at
            FROM submissions s
            LEFT JOIN submission_analysis sa ON s.submission_id = sa.submission_id
            WHERE s.assignment_id = ?
            ORDER BY s.submitted_at DESC
        """, (assignment_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def grade_submission(submission_id: str, score: int, feedback: str,
                     faculty_username: str) -> dict:
    submission = get_submission(submission_id)
    if not submission:
        raise ValueError("Submission not found.")
        
    assignment = get_assignment(submission["assignment_id"])
    if not assignment:
        raise ValueError("Assignment not found.")
        
    if score < 0 or score > assignment["max_score"]:
        raise ValueError(f"Score must be between 0 and assignment's max score ({assignment['max_score']}).")
        
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE submissions 
            SET score = ?, feedback = ?, status = 'graded' 
            WHERE submission_id = ?
        """, (score, feedback, submission_id))
        conn.commit()
    finally:
        conn.close()
        
    return get_submission(submission_id)

def trigger_batch_analysis(assignment_id: str,
                           faculty_username: str) -> list[str]:
    """
    For every submission in the assignment with status=pending:
    1. Update status=analyzing
    2. Enqueue AI job: job_type="submission_analysis"
       input: { submission_id, extracted_path, assignment_id }
    Return list of job_ids.
    """
    assignment = get_assignment(assignment_id)
    if not assignment:
        raise ValueError("Assignment not found.")
    if assignment["created_by"] != faculty_username:
        raise PermissionError("Only the creator of the assignment can trigger analysis.")
        
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT submission_id, extracted_path FROM submissions 
            WHERE assignment_id = ? AND status = 'pending'
        """, (assignment_id,))
        pending_subs = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
        
    if not pending_subs:
        return []
        
    job_ids = []
    from app.ai.job_queue import enqueue_job
    
    for sub in pending_subs:
        sub_id = sub["submission_id"]
        # Update status in db
        conn = get_connection()
        try:
            conn.execute("UPDATE submissions SET status = 'analyzing' WHERE submission_id = ?", (sub_id,))
            conn.commit()
        finally:
            conn.close()
            
        # Enqueue job
        job_id = enqueue_job(
            job_type="submission_analysis",
            app_name=sub_id, # Use sub_id as app_name since there is no deployed app record yet
            username=faculty_username,
            input_data={
                "submission_id": sub_id,
                "extracted_path": sub["extracted_path"],
                "assignment_id": assignment_id
            }
        )
        job_ids.append(job_id)
        
    return job_ids
