import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.auth.dependencies import get_current_user
from app.faculty import service
from app.faculty.similarity import compute_similarity_matrix, flag_plagiarism
from app.faculty.report import generate_assignment_report, generate_csv_export

router = APIRouter(tags=["faculty"])

class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    course_code: Optional[str] = None
    batch: Optional[str] = None
    deadline: Optional[str] = None
    max_score: Optional[int] = 100

class GradePayload(BaseModel):
    score: int
    feedback: str

def check_faculty(user: dict):
    if user.get("role") not in ["faculty", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )

@router.get("/faculty/dashboard")
def faculty_dashboard(current_user: dict = Depends(get_current_user)):
    check_faculty(current_user)
    from app.db import get_connection
    conn = get_connection()
    try:
        total_students = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'student'"
        ).fetchone()["c"]
        total_projects = conn.execute("SELECT COUNT(*) AS c FROM apps").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM apps WHERE status = 'PENDING_APPROVAL' OR approval_status = 'pending'"
        ).fetchone()["c"]

        dsa_stats = {"Easy": 0, "Medium": 0, "Hard": 0}
        for r in conn.execute(
            "SELECT difficulty, COUNT(*) AS c FROM dsa_submissions GROUP BY difficulty"
        ).fetchall():
            if r["difficulty"] in dsa_stats:
                dsa_stats[r["difficulty"]] = r["c"]

        top_dsa = [dict(r) for r in conn.execute(
            """
            SELECT username, display_name, dsa_total_solved AS total_solved, dsa_streak AS streak
            FROM users
            WHERE dsa_total_solved > 0
            ORDER BY dsa_total_solved DESC, dsa_streak DESC
            LIMIT 10
            """
        ).fetchall()]

        recent_deploys = [dict(r) for r in conn.execute(
            """
            SELECT name, owner, status, approval_status, created_at
            FROM apps
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()]

        active_tunnels = conn.execute(
            "SELECT COUNT(*) AS c FROM tunnels WHERE status = 'ACTIVE'"
        ).fetchone()["c"]

        return {
            "total_students": total_students,
            "total_projects": total_projects,
            "projects_pending_approval": pending,
            "dsa_class_stats": dsa_stats,
            "top_dsa_students": top_dsa,
            "recent_deploys": recent_deploys,
            "active_tunnels": active_tunnels,
        }
    finally:
        conn.close()


@router.post("/assignments")
def create_assignment_endpoint(
    payload: AssignmentCreate,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    return service.create_assignment(
        title=payload.title,
        description=payload.description,
        created_by=current_user["sub"],
        course_code=payload.course_code,
        batch=payload.batch,
        deadline=payload.deadline,
        max_score=payload.max_score
    )

@router.get("/assignments")
def list_assignments_endpoint(
    created_by: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return service.list_assignments(created_by=created_by)

@router.get("/assignments/{assignment_id}")
def get_assignment_endpoint(
    assignment_id: str,
    current_user: dict = Depends(get_current_user)
):
    assignment = service.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment

@router.post("/assignments/{assignment_id}/close")
def close_assignment_endpoint(
    assignment_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        service.close_assignment(assignment_id, current_user["sub"])
        return {"status": "success", "message": "Assignment closed"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/assignments/{assignment_id}/submissions")
async def create_submission_endpoint(
    assignment_id: str,
    student_name: str = Form(...),
    roll_number: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # Save the uploaded zip to a temporary file
    temp_dir = "projects/submissions/uploads"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}-{file.filename}")
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        sub = service.create_submission(
            assignment_id=assignment_id,
            student_name=student_name,
            roll_number=roll_number,
            zip_path=temp_path,
            student_username=current_user.get("sub")
        )
        return sub
    except ValueError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/assignments/{assignment_id}/submissions")
def list_submissions_endpoint(
    assignment_id: str,
    current_user: dict = Depends(get_current_user)
):
    return service.list_submissions(assignment_id)

@router.get("/submissions/{submission_id}")
def get_submission_endpoint(
    submission_id: str,
    current_user: dict = Depends(get_current_user)
):
    sub = service.get_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return sub

@router.post("/submissions/{submission_id}/grade")
def grade_submission_endpoint(
    submission_id: str,
    payload: GradePayload,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    try:
        return service.grade_submission(
            submission_id=submission_id,
            score=payload.score,
            feedback=payload.feedback,
            faculty_username=current_user["sub"]
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/assignments/{assignment_id}/analyze")
def trigger_batch_analysis_endpoint(
    assignment_id: str,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    try:
        job_ids = service.trigger_batch_analysis(assignment_id, current_user["sub"])
        return {"status": "success", "job_ids": job_ids}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/assignments/{assignment_id}/report/pdf")
def get_pdf_report(
    assignment_id: str,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    assignment = service.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
        
    submissions = service.list_submissions(assignment_id)
    
    # Compute similarity flags
    subs_list = [{"submission_id": s["submission_id"], "extracted_path": s["extracted_path"]} for s in submissions]
    sim_matrix = compute_similarity_matrix(subs_list)
    flags = flag_plagiarism(sim_matrix, threshold=0.75)
    
    report_dir = "projects/submissions/reports"
    os.makedirs(report_dir, exist_ok=True)
    output_path = os.path.join(report_dir, f"report-{assignment_id}.pdf")
    
    try:
        generate_assignment_report(assignment, submissions, flags, output_path)
        return FileResponse(output_path, media_type="application/pdf", filename=f"report-{assignment_id}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF report: {e}")

@router.get("/assignments/{assignment_id}/report/csv")
def get_csv_report(
    assignment_id: str,
    current_user: dict = Depends(get_current_user)
):
    check_faculty(current_user)
    assignment = service.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
        
    submissions = service.list_submissions(assignment_id)
    
    report_dir = "projects/submissions/reports"
    os.makedirs(report_dir, exist_ok=True)
    output_path = os.path.join(report_dir, f"report-{assignment_id}.csv")
    
    try:
        generate_csv_export(submissions, output_path)
        return FileResponse(output_path, media_type="text/csv", filename=f"report-{assignment_id}.csv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate CSV report: {e}")
