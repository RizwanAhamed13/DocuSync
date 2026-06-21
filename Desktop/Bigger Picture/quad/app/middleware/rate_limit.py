from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

limiter = Limiter(key_func=get_remote_address, default_limits=[])

def _safe_rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", None) or str(exc)
    return JSONResponse({"error": f"Rate limit exceeded: {detail}"}, status_code=429)

def init_rate_limit(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(HTTP_429_TOO_MANY_REQUESTS, _safe_rate_limit_handler)
