from contextlib import asynccontextmanager
from fastapi import FastAPI
from novalm.config.settings import settings
from novalm.fastapi_app.middleware.auth import AuthMiddleware
from novalm.fastapi_app.middleware.rate_limit import RateLimitMiddleware
from novalm.fastapi_app.routes import chat
from novalm.engine.vllm_engine import get_inference_engine, VLLMInferenceEngine
from novalm.core.orchestrator import Orchestrator
from novalm.core.safety import SafetyLayer

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting NovaLM...")
    
    # 1. Initialize Inference Engine
    inference_engine = get_inference_engine()
    if isinstance(inference_engine, VLLMInferenceEngine):
        # We explicitly initialize the VLLM engine here
        # This handles the heavy loading of the model
        try:
            await inference_engine.initialize()
        except RuntimeError as e:
            import logging
            logging.error(f"CRITICAL: Failed to initialize VLLM Engine: {e}")
            # We intentionally let this fail the startup if strictly required
            raise e
            
    # 2. Initialize Safety Layer
    safety_layer = SafetyLayer()
    
    # 3. Initialize Orchestrator
    orchestrator = Orchestrator(inference_engine, safety_layer)
    
    # Inject into app state
    app.state.orchestrator = orchestrator
    
    yield
    
    # Shutdown
    print("Shutting down NovaLM...")
    if hasattr(inference_engine, "shutdown"):
        await inference_engine.shutdown()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    lifespan=lifespan
)

# Middleware
# Note: execution order of middleware is inverse of addition order for response, 
# but direct for request.
# Request -> RateLimit -> Auth -> Route (Wait, Auth should be first?)
# Order in add_middleware: The LAST added middleware is the FIRST one to handle request.
# We want: Request -> Auth (check key) -> RateLimit (check quota) -> Route
# So we add RateLimit first, then Auth.
app.add_middleware(RateLimitMiddleware) 
app.add_middleware(AuthMiddleware)

# Routes
app.include_router(chat.router, prefix=f"/{settings.API_VERSION}/chat", tags=["chat"])

# Observability
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

@app.get("/health")
async def health_check():
    return {"status": "ok", "model": settings.MODEL_PATH}
