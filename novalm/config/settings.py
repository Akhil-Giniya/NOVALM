import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "NovaLM"
    API_VERSION: str = "v1"
    DEBUG: bool = False

    # Server Config
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Model Config
    MODEL_PATH: str  # Must be provided via env var or .env
    TRUST_REMOTE_CODE: bool = False
    MAX_MODEL_LEN: int = 2048
    GPU_MEMORY_UTILIZATION: float = 0.90
    
    # Safety Config
    ENABLE_SAFETY_CHECKS: bool = True
    
    # Auth Config
    # Check for this key in X-API-Key header or Bearer token
    API_KEY: str # Must be provided
    
    # Dev/Test Flags
    ALLOW_MOCK_INFERENCE: bool = False
    
    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379"

    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
try:
    settings = Settings()
except Exception as e:
    # In case of missing env vars during simple imports or tests, we might want to handle gracefully 
    # or let it fail fast. User requested fail fast.
    print(f"Failed to load settings: {e}")
    # We will let it crash the app startup if critical settings are missing, 
    # but for now during development we might want to check
    raise
