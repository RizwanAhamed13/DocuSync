from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from typing import Any, List, Optional

from app.auth.dependencies import get_current_user
from app.dsa import service

router = APIRouter(prefix="/dsa", tags=["dsa"])

# ── Pydantic models ────────────────────────────────────────────────────────────

class ExampleModel(BaseModel):
    input: str
    output: str
    explanation: Optional[str] = None

class TestCaseIn(BaseModel):
    input: List[Any] = Field(..., description="List of arguments passed to solve()")
    expected: Any = Field(..., description="Expected return value")
    is_hidden: bool = False

class QuestionCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=80)
    title: str = Field(..., min_length=2, max_length=200)
    difficulty: str
    category: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=10)
    constraints: str = ""
    examples: List[ExampleModel] = []
    tags: List[str] = []
    hints: List[str] = []
    editorial: str = ""
    starter_code_python: str = "def solve(*args):\n    pass\n"
    starter_code_js: str = "function solve(...args) {\n  \n}\n"
    starter_code_ts: str = "function solve(...args: any[]): any {\n  \n}\n"
    starter_code_java: str = "static Object solve(Object... args) {\n    // Use helpers: toIntArray(args[0]), toInt(args[1]), toStr(args[0])\n    return null;\n}"
    starter_code_cpp: str = "// args is a JVal array. Helpers: args[0].asInt(), args[0].asIntVec(), args[0].asStr()\nauto solve(JVal args) {\n    return 0;\n}"
    starter_code_go: str = "func solve(args ...interface{}) interface{} {\n    return nil\n}"
    test_cases: List[TestCaseIn] = []

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in ("Easy", "Medium", "Hard"):
            raise ValueError("difficulty must be Easy, Medium, or Hard")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError("slug must contain only lowercase letters, digits, and hyphens")
        return v

class QuestionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    difficulty: Optional[str] = None
    category: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = None
    constraints: Optional[str] = None
    examples: Optional[List[ExampleModel]] = None
    tags: Optional[List[str]] = None
    hints: Optional[List[str]] = None
    editorial: Optional[str] = None
    starter_code_python: Optional[str] = None
    starter_code_js: Optional[str] = None
    starter_code_ts: Optional[str] = None
    starter_code_java: Optional[str] = None
    starter_code_cpp: Optional[str] = None
    starter_code_go: Optional[str] = None

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str | None) -> str | None:
        if v is not None and v not in ("Easy", "Medium", "Hard"):
            raise ValueError("difficulty must be Easy, Medium, or Hard")
        return v

class RunRequest(BaseModel):
    slug: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"python", "py", "javascript", "js", "typescript", "ts", "java", "cpp", "c++", "go"}
        if v.lower() not in allowed:
            raise ValueError(f"language must be one of: {', '.join(sorted(allowed))}")
        return v.lower()

class SubmissionRequest(BaseModel):
    problem_slug: str = Field(..., min_length=1)
    problem_title: str = Field(..., min_length=1)
    difficulty: str

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in ("Easy", "Medium", "Hard"):
            raise ValueError("difficulty must be Easy, Medium, or Hard")
        return v

    notes: Optional[str] = Field(None, max_length=1000)

class TestCaseAddRequest(BaseModel):
    input: List[Any] = Field(..., description="List of args passed to solve()")
    expected: Any = Field(..., description="Expected return value")
    is_hidden: bool = False

class CustomRunRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    stdin: str = Field(default="", max_length=10_000)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"python", "py", "javascript", "js", "typescript", "ts", "java", "cpp", "c++", "go"}
        if v.lower() not in allowed:
            raise ValueError(f"language must be one of: {', '.join(sorted(allowed))}")
        return v.lower()

class NoteUpsert(BaseModel):
    content: str = Field(..., max_length=5000)

class AIGenerateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    difficulty: str = "Medium"

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in ("Easy", "Medium", "Hard"):
            raise ValueError("difficulty must be Easy, Medium, or Hard")
        return v

class AIAddTestCasesRequest(BaseModel):
    description: str = Field(default="", max_length=2000)

# ── Question endpoints ─────────────────────────────────────────────────────────

@router.get("/questions", response_model=List[dict])
def list_dsa_questions(
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
):
    return service.list_questions(category=category, difficulty=difficulty)

@router.get("/questions/{slug}", response_model=dict)
def get_dsa_question(slug: str):
    q = service.get_question(slug)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return q

@router.post("/questions", response_model=dict, status_code=201)
def create_dsa_question(
    payload: QuestionCreate,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can create questions")
    try:
        return service.create_question(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/questions/{slug}", response_model=dict)
def update_dsa_question(
    slug: str,
    payload: QuestionUpdate,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can update questions")
    try:
        return service.update_question(slug, payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/questions/{slug}", status_code=204)
def delete_dsa_question(
    slug: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete questions")
    service.delete_question(slug)

# ── Test case endpoints ────────────────────────────────────────────────────────

@router.get("/questions/{slug}/test-cases", response_model=List[dict])
def list_question_test_cases(
    slug: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can view all test cases")
    q = service.get_question(slug)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return service.list_test_cases(slug, include_hidden=True)

@router.post("/questions/{slug}/test-cases", response_model=dict, status_code=201)
def add_test_case(
    slug: str,
    payload: TestCaseAddRequest,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can add test cases")
    q = service.get_question(slug)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return service.add_test_case(slug, payload.input, payload.expected, payload.is_hidden)

@router.delete("/questions/{slug}/test-cases/{tc_id}", status_code=204)
def delete_test_case(
    slug: str,
    tc_id: int,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can delete test cases")
    service.delete_test_case(tc_id)

# ── Code execution ─────────────────────────────────────────────────────────────

@router.post("/run", response_model=dict)
def run_dsa_code(payload: RunRequest):
    import os
    if os.environ.get("JUDGE0_API_KEY"):
        return service.run_via_judge0(payload.slug, payload.code, payload.language)
    return service.run_code(payload.slug, payload.code, payload.language)

@router.post("/run-custom", response_model=dict)
def run_custom_code(payload: CustomRunRequest):
    return service.run_custom(payload.code, payload.language, payload.stdin)

@router.get("/languages", response_model=List[dict])
def list_supported_languages():
    """Return supported languages with availability status."""
    import shutil
    checks = {
        "python":     ("Python",     "python3",   shutil.which("python3") is not None),
        "javascript": ("JavaScript", "node",      shutil.which("node") is not None or shutil.which("nodejs") is not None),
        "typescript": ("TypeScript", "tsx/ts-node", shutil.which("tsx") is not None or shutil.which("ts-node") is not None or shutil.which("node") is not None),
        "java":       ("Java",       "java",      shutil.which("java") is not None),
        "cpp":        ("C++",        "g++",       shutil.which("g++") is not None),
        "go":         ("Go",         "go",        shutil.which("go") is not None),
    }
    return [
        {"id": k, "label": v[0], "runtime": v[1], "available": v[2]}
        for k, v in checks.items()
    ]

# ── Submissions / stats / leaderboard ─────────────────────────────────────────

@router.post("/submit", status_code=201)
def submit_dsa_problem(
    payload: SubmissionRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        res = service.log_submission(
            username=current_user["sub"],
            problem_slug=payload.problem_slug,
            problem_title=payload.problem_title,
            difficulty=payload.difficulty,
            notes=payload.notes,
        )
        try:
            from app.badges.service import check_and_award
            check_and_award(current_user["sub"], "dsa_solved")
        except Exception:
            pass
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stats/{username}", response_model=dict)
def get_user_dsa_stats(username: str):
    try:
        return service.get_dsa_stats(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/submissions/{username}", response_model=List[dict])
def list_user_submissions(
    username: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return service.get_submissions(username, limit=limit, offset=offset)

@router.get("/leaderboard", response_model=List[dict])
def get_dsa_leaderboard(limit: int = Query(10, ge=1, le=100)):
    return service.get_dsa_leaderboard(limit=limit)

# ── AI generation ─────────────────────────────────────────────────────────────

@router.post("/ai-generate", response_model=dict)
async def ai_generate_question(
    payload: AIGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate full question metadata (test cases, hints, editorial, starter code) from a description.
    Runs in a thread executor so the long Ollama call doesn't block the event loop."""
    import asyncio, functools
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can use AI generation")
    try:
        from app.dsa.ai_gen import generate_question_metadata
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(generate_question_metadata, payload.title, payload.description, payload.difficulty)
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/questions/{slug}/ai-test-cases", response_model=List[dict], status_code=201)
async def ai_add_test_cases(
    slug: str,
    payload: AIAddTestCasesRequest,
    current_user: dict = Depends(get_current_user),
):
    """Auto-generate and insert test cases for an existing question using AI."""
    if current_user.get("role") not in ("admin", "faculty"):
        raise HTTPException(status_code=403, detail="Only admin/faculty can use AI generation")
    q = service.get_question(slug)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    try:
        import asyncio, functools
        from app.dsa.ai_gen import auto_generate_test_cases_only
        loop = asyncio.get_event_loop()
        desc = payload.description or q.get("description", "")
        cases = await loop.run_in_executor(
            None, functools.partial(auto_generate_test_cases_only, slug, desc)
        )
        added = []
        for tc in cases:
            row = service.add_test_case(slug, tc["input"], tc["expected"], tc.get("is_hidden", False))
            added.append(row)
        return added
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Per-user notes ─────────────────────────────────────────────────────────────

@router.get("/notes/{slug}", response_model=dict)
def get_note(slug: str, current_user: dict = Depends(get_current_user)):
    content = service.get_note(current_user["sub"], slug)
    return {"slug": slug, "content": content}

@router.put("/notes/{slug}", response_model=dict)
def save_note(slug: str, payload: NoteUpsert, current_user: dict = Depends(get_current_user)):
    service.save_note(current_user["sub"], slug, payload.content)
    return {"slug": slug, "content": payload.content}
