import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from novalm.config.settings import settings
import redis.asyncio as redis

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based Rate Limits.
    Uses a simple fixed window counter with automated expiry.
    """
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.redis = None

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/health", "/docs", "/openapi.json", "/metrics"]:
            return await call_next(request)

        # Lazy init redis
        if not self.redis:
            self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

        client_id = request.client.host
        # Use API key if available for more specific limits? 
        # For now, IP-based.
        
        # Key: rate_limit:{ip}:{current_minute}
        current_minute = int(time.time() // 60)
        key = f"rate_limit:{client_id}:{current_minute}"
        
        try:
            # Atomic increment
            # async pipeline to optimize? 
            # Simple INCR is fast enough.
            current_count = await self.redis.incr(key)
            
            if current_count == 1:
                # Set expiry if new key
                await self.redis.expire(key, 60)
                
            if current_count > self.rpm:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"}
                )
        except Exception as e:
            # If Redis fails, fail open or closed?
            # Fail open for resilience usually preferable in MVP unless strict
            print(f"Redis rate limit error: {e}")
            pass
            
        return await call_next(request)
