from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import os

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # HTTPS redirect when behind a proxy that sets x-forwarded-proto
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if forwarded_proto == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            return Response(status_code=301, headers={"location": https_url})
        # Basic path traversal protection
        if ".." in request.url.path:
            return Response(status_code=400, content="Invalid path")
        # TODO: integrate virus scan for uploaded files
        response = await call_next(request)
        # Add security headers
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
