import hashlib
import json
import os
from typing import Optional, Any
from novalm.config.settings import settings

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class CacheManager:
    """
    Manages caching of LLM responses using Redis.
    """
    def __init__(self):
        self.redis_client = None
        if REDIS_AVAILABLE and settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                self.redis_client.ping() # Fail fast if invalid
            except Exception as e:
                print(f"WARNING: Redis connection failed: {e}. Caching disabled.")
                self.redis_client = None
        else:
            if not REDIS_AVAILABLE:
                print("WARNING: Redis library not installed. Caching disabled.")

    def _generate_key(self, prompt: str, sampling_params: Any = None) -> str:
        """
        Generates a unique key for the request.
        Key = Hash(Prompt + ModelConfig + SamplingParams).
        """
        # For simplicity, we just hash the prompt and relevant params.
        components = [prompt]
        if sampling_params:
             # Convert sampling params to sortable string
             if hasattr(sampling_params, "model_dump_json"):
                 components.append(sampling_params.model_dump_json())
             else:
                 components.append(str(sampling_params))
                 
        key_str = "|".join(components)
        return f"novalm:cache:{hashlib.sha256(key_str.encode()).hexdigest()}"

    def get(self, prompt: str, sampling_params: Any = None) -> Optional[str]:
        """
        Retrieves cached response if available.
        """
        if not self.redis_client:
            return None
            
        key = self._generate_key(prompt, sampling_params)
        try:
            return self.redis_client.get(key)
        except Exception:
            return None

    def set(self, prompt: str, response: str, sampling_params: Any = None, ttl: int = 3600):
        """
        Caches a response with a TTL (default 1 hour).
        """
        if not self.redis_client:
            return
            
        key = self._generate_key(prompt, sampling_params)
        try:
            self.redis_client.setex(key, ttl, response)
        except Exception as e:
            print(f"Cache write failed: {e}")
