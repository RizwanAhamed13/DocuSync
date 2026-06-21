import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List

from app.auth.dependencies import get_current_user
from app.repository import get_app
from app.db import get_connection
from app.ai.job_queue import enqueue_job, get_job_status

router = APIRouter(prefix="/ai", tags=["ai"])

# Request Models
class ChatRequest(BaseModel):
    question: str
    history: Optional[List[dict]] = None

class DeployDoctorRequest(BaseModel):
    build_log: str

class DocsRequest(BaseModel):
    doc_type: str  # readme | api | modules

class ReviewRequest(BaseModel):
    diff: str

class OnboardingRequest(BaseModel):
    member_role: str
    member_name: str

# Helper to verify app access
def check_app_access(app_name: str, current_user: dict, require_owner_or_admin=False):
    app = get_app(app_name)
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
        
    username = current_user["sub"]
    user_role = current_user.get("role")
    
    if user_role == "admin":
        return app
        
    if app.owner == username:
        return app
        
    # Check team memberships
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM project_teams pt
            JOIN team_members tm ON pt.team_slug = tm.team_slug
            WHERE pt.app_name = ? AND tm.username = ?
        """, (app_name, username))
        member = cursor.fetchone()
        if member:
            if require_owner_or_admin:
                # If owner/admin is strictly required but they are just team member, raise
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires owner or admin permissions.")
            return app
    finally:
        conn.close()
        
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this app.")

def is_app_indexed(app_name: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM code_chunks WHERE app_name = ? LIMIT 1", (app_name,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

# Routes

@router.post("/ingest/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_ingest(app_name: str, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user, require_owner_or_admin=True)
    
    # Get project path on host
    # In Quad local context, project is inside projects_source/<app_name>
    project_path = f"projects_source/{app_name}"
    if not os.path.exists(project_path):
        # Fallback to general projects folder
        project_path = f"projects/{app_name}"
        
    job_id = enqueue_job("ingest", app_name, current_user["sub"], {"project_path": project_path})
    return {
        "job_id": job_id,
        "status": "QUEUED",
        "message": "indexing started"
    }

class SimpleChatRequest(BaseModel):
    message: str
    context_file: Optional[str] = None
    app_name: Optional[str] = None
    history: Optional[List[dict]] = None

@router.post("/chat")
def simple_chat(body: SimpleChatRequest, current_user=Depends(get_current_user)):
    import urllib.request
    import os

    msg = (body.message or "").strip()
    if not msg:
        return {"reply": "Please enter a message."}

    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3")

    system = (
        "You are an AI assistant embedded in Quad, a college developer platform. "
        "Help students with their code, explain concepts, and answer questions about their projects. "
        "Be concise and practical."
    )
    if body.context_file:
        system += f"\n\nCurrent file context:\n```\n{body.context_file[:3000]}\n```"

    messages = [{"role": "system", "content": system}]
    if body.history:
        for h in body.history[-10:]:
            role = h.get("role")
            content = h.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": msg})

    payload = json.dumps({
        "model": ollama_model,
        "messages": messages,
        "stream": False,
    }).encode()

    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        reply = data.get("message", {}).get("content", "").strip()
        return {"reply": reply or "No response from model."}
    except Exception as e:
        return {"reply": f"Local AI unavailable: {e}. Make sure Ollama is running (`ollama serve`)."}

@router.post("/chat/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_chat(app_name: str, payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user)
    
    if not is_app_indexed(app_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="not indexed yet"
        )
        
    job_id = enqueue_job("chat", app_name, current_user["sub"], {
        "question": payload.question,
        "history": payload.history or []
    })
    return {"job_id": job_id}

@router.post("/deploy-doctor/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_deploy_doctor(app_name: str, payload: DeployDoctorRequest, current_user: dict = Depends(get_current_user)):
    app = check_app_access(app_name, current_user, require_owner_or_admin=True)
    
    job_id = enqueue_job("deploy_doctor", app_name, current_user["sub"], {
        "build_log": payload.build_log,
        "stack": app.stack or "unknown"
    })
    return {"job_id": job_id}

@router.post("/docs/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_docs(app_name: str, payload: DocsRequest, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user, require_owner_or_admin=True)
    
    if payload.doc_type not in ("readme", "api", "modules"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc_type")
        
    job_id = enqueue_job("auto_docs", app_name, current_user["sub"], {
        "doc_type": payload.doc_type
    })
    return {"job_id": job_id}

@router.post("/review/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_review(app_name: str, payload: ReviewRequest, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user)
    
    job_id = enqueue_job("pr_review", app_name, current_user["sub"], {
        "diff": payload.diff
    })
    return {"job_id": job_id}

@router.post("/onboarding/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_onboarding(app_name: str, payload: OnboardingRequest, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user)
    
    job_id = enqueue_job("onboarding", app_name, current_user["sub"], {
        "member_role": payload.member_role,
        "member_name": payload.member_name
    })
    return {"job_id": job_id}

@router.post("/diagram/{app_name}", status_code=status.HTTP_202_ACCEPTED)
def post_diagram(app_name: str, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user)
    
    job_id = enqueue_job("arch_diagram", app_name, current_user["sub"], {})
    return {"job_id": job_id}

@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

@router.get("/jobs")
def list_jobs(
    app_name: Optional[str] = None,
    job_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM ai_jobs WHERE username = ?"
        params = [current_user["sub"]]
        if app_name:
            query += " AND app_name = ?"
            params.append(app_name)
        if job_type:
            query += " AND job_type = ?"
            params.append(job_type)
        if status:
            query += " AND status = ?"
            params.append(status)
            
        query += " ORDER BY queued_at DESC LIMIT 20"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        out = []
        for row in rows:
            job_dict = dict(row)
            if job_dict.get("input"):
                try:
                    job_dict["input"] = json.loads(job_dict["input"])
                except Exception:
                    pass
            if job_dict.get("result"):
                try:
                    job_dict["result"] = json.loads(job_dict["result"])
                except Exception:
                    pass
            out.append(job_dict)
        return out
    finally:
        conn.close()

@router.get("/status/{app_name}")
def get_ai_status(app_name: str, current_user: dict = Depends(get_current_user)):
    check_app_access(app_name, current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT file_path) FROM code_chunks WHERE app_name = ?", (app_name,))
        row = cursor.fetchone()
        chunk_count = row[0] if row else 0
        file_count = row[1] if row else 0
        return {
            "indexed": chunk_count > 0,
            "chunk_count": chunk_count,
            "file_count": file_count
        }
    finally:
        conn.close()

@router.delete("/jobs/{job_id}/cache")
def delete_job_cache(job_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_jobs WHERE job_id = ? AND status = 'DONE'", (job_id,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": "Cache cleared"}

import os
