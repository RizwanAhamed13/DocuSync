from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import datetime, uuid
from app.db import log_rate_limit

class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = datetime.datetime.utcnow()
        response = await call_next(request)
        duration = (datetime.datetime.utcnow() - start).total_seconds()
        await log_rate_limit(
            ip=request.client.host,
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration=duration,
            request_id=str(uuid.uuid4()),
        )
        return response
