from fastapi import Request, HTTPException
from fastapi.security import APIKeyHeader, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from novalm.config.settings import settings

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks or docs if needed
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)
            
        api_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")
        
        token = None
        if api_key:
            token = api_key
        elif auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
        if not token or token != settings.API_KEY:
            # We return JSON response for 401
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401, 
                content={"detail": "Invalid or missing API Key"}
            )
            
        return await call_next(request)
