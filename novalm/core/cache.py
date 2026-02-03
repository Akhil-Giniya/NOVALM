import hashlib
import json
import os
import logging
from typing import Optional, Any
from novalm.config.settings import settings

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class CacheManager:
    """
    Manages caching of LLM responses using Redis.
    Uses versioned keys and stable JSON hashing.
    """
    def __init__(self):
        self.redis_client = None
        if REDIS_AVAILABLE and settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                self.redis_client.ping() # Fail fast if invalid
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Caching disabled.")
                self.redis_client = None
        else:
            if not REDIS_AVAILABLE:
                logger.warning("Redis library not installed. Caching disabled.")

    def _generate_key(self, prompt: str, sampling_params: Any = None) -> str:
        """
        Generates a unique, stable key for the request.
        Key = Hash(Version + Model + ParamConfig + Prompt).
        """
        # Critical components for cache validity
        components = [
            "v1", # Schema version
            settings.MODEL_PATH,
            str(settings.MAX_MODEL_LEN),
            prompt,
        ]

        if sampling_params:
            if hasattr(sampling_params, "model_dump"):
                # Pydantic v2
                components.append(
                    json.dumps(sampling_params.model_dump(), sort_keys=True)
                )
            elif hasattr(sampling_params, "dict"):
                 # Pydantic v1
                components.append(
                    json.dumps(sampling_params.dict(), sort_keys=True)
                )
            else:
                # Fallback, but warn locally if curious
                try:
                    components.append(json.dumps(sampling_params, sort_keys=True))
                except TypeError:
                     # If not serializable, fallback to str but unsafe
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
        except Exception as e:
            logger.warning(f"Cache read failed for {key}: {e}")
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
            logger.error(f"Cache write failed: {e}")
