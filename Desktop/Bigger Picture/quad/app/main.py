from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from .db import init_db, get_connection
from .models import AppCreate, App
from . import repository

import asyncio
from app.reaper import reaper_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        from app.dsa.seed import seed_dsa_questions
        seed_dsa_questions()
    except Exception:
        pass
    try:
        from app.templates.seed import seed_templates
        seed_templates()
    except Exception:
        pass
    task = asyncio.create_task(reaper_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


from fastapi.middleware.cors import CORSMiddleware
from app.middleware.rate_limit import init_rate_limit
from app.middleware.security import SecurityMiddleware
from app.middleware.request_log import RequestLogMiddleware

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestLogMiddleware)
init_rate_limit(app)

@app.get("/health")
def health():
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    
    return {"status": "ok", "db": db_status}

@app.get("/apps", response_model=list[App])
def list_apps():
    return repository.list_apps()

@app.post("/apps", response_model=App)
def create_app(payload: AppCreate):
    try:
        return repository.create_app(payload.name, payload.stack)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": str(e),
                "code": "DUPLICATE_APP_NAME"
            }
        )

from app.auth.router import router as auth_router
app.include_router(auth_router)

from app.deploy import router as deploy_router
app.include_router(deploy_router)

from app.teams.router import router as teams_router
app.include_router(teams_router)

from app.tunnel_router import router as tunnel_router
app.include_router(tunnel_router)

from app.social.router import router as social_router
app.include_router(social_router)

from app.showcase.router import router as showcase_router
app.include_router(showcase_router)

from app.dsa.router import router as dsa_router
app.include_router(dsa_router)

from app.ai.router import router as ai_router
app.include_router(ai_router)

from app.faculty.router import router as faculty_router
app.include_router(faculty_router)

from app.hackathon.router import router as hackathon_router
app.include_router(hackathon_router)

from app.health.router import router as health_router
app.include_router(health_router)

from app.social.posts_router import router as posts_router
app.include_router(posts_router)

from app.terminal.router import router as terminal_router
app.include_router(terminal_router)

from app.notifications.router import router as notifications_router
app.include_router(notifications_router)

from app.badges.router import router as badges_router
app.include_router(badges_router)

from app.templates.router import router as templates_router
app.include_router(templates_router)

from app.devlog.router import router as devlog_router
app.include_router(devlog_router)

from app.proxy import router as proxy_router
app.include_router(proxy_router)


