import asyncio
import os
import logging
import time
import uuid
from typing import AsyncIterator, Optional
from novalm.core.inference import InferenceEngine
from novalm.core.types import SamplingParams
from novalm.config.settings import settings
from novalm.core.metrics import (
    GENERATED_TOKENS_TOTAL,
    INFERENCE_LATENCY_SECONDS
)

logger = logging.getLogger(__name__)

try:
    import torch
    from vllm import AsyncLLMEngine, AsyncEngineArgs, SamplingParams as VLLMSamplingParams
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False

class VLLMInferenceEngine(InferenceEngine):
    """
    Production-ready Inference Engine using vLLM.
    Global instance initialized at startup.
    Thread-safe initialization (Lazy Lock).
    
    WARNING: This engine is a singleton designed for a single-worker process per GPU.
    Do NOT run with Gunicorn workers > 1 if sharing a GPU.
    """
    def __init__(self):
        self.engine = None
        # Lazy lock: initialized in initialize() to ensure loop binding
        self._init_lock: Optional[asyncio.Lock] = None

    async def initialize(self):
        """
        Explicit initialization logic.
        Thread-safe and async-friendly.
        Fails FAST if CUDA is not available.
        """
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()

        async with self._init_lock:
            if self.engine:
                return

            if not VLLM_AVAILABLE:
                raise RuntimeError("vLLM is not installed. Cannot start VLLMInferenceEngine.")
                
            if not torch.cuda.is_available():
                # Strict enforcement as requested
                raise RuntimeError("CRITICAL: CUDA is not available. NovaLM requires a GPU to run. Aborting.")

            logger.info(f"Initializing vLLM Engine with model: {settings.MODEL_PATH}...")
            
            # Helper to check model path existence logic
            if not os.path.exists(settings.MODEL_PATH):
                 logger.info(f"Model path {settings.MODEL_PATH} not found locally. Assuming HuggingFace Hub ID.")
            
            engine_args = AsyncEngineArgs(
                model=settings.MODEL_PATH,
                trust_remote_code=settings.TRUST_REMOTE_CODE,
                max_model_len=settings.MAX_MODEL_LEN,
                gpu_memory_utilization=settings.GPU_MEMORY_UTILIZATION
            )
            # This can block, but acceptable during startup phase.
            self.engine = AsyncLLMEngine.from_engine_args(engine_args)
            logger.info("vLLM Engine initialized successfully.")

    async def shutdown(self):
        """Graceful shutdown logic."""
        if self.engine:
            logger.info("Shutting down vLLM Engine...")
            # Attempt upstream shutdown if supported
            if hasattr(self.engine, "shutdown"):
                # verify it's awaitable
                if asyncio.iscoroutinefunction(self.engine.shutdown):
                    await self.engine.shutdown()
                else:
                    self.engine.shutdown()
            
            self.engine = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info("vLLM Engine shutdown complete (Note: Full process restart may be needed to fully release GPU).")

    async def generate(
        self, 
        prompt: str, 
        sampling_params: SamplingParams,
        request_id: str
    ) -> AsyncIterator[str]:
        
        if not self.engine:
            raise RuntimeError("Engine not initialized. Call initialize() first.")
            
        # 1. Input Validation
        # Prompt Length Check (Heuristic)
        MAX_CHARS = settings.MAX_MODEL_LEN * 4  # Rough char count approximation
        if len(prompt) > MAX_CHARS:
             raise ValueError(f"Prompt too long ({len(prompt)} chars). Approx limit: {MAX_CHARS}")

        # Sampling Params Validation
        if sampling_params.temperature < 0:
            raise ValueError("temperature must be >= 0")
        if sampling_params.top_p < 0 or sampling_params.top_p > 1:
            raise ValueError("top_p must be between 0 and 1")
        if sampling_params.top_k < -1: # -1 usually means all
            raise ValueError("top_k must be >= -1")
        if sampling_params.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        if sampling_params.ignore_eos and not sampling_params.stop:
             raise ValueError("ignore_eos=True requires stop tokens to avoid runaway generation")
        
        # 2. Namespace Request ID to avoid collisions
        safe_request_id = f"{request_id}-{uuid.uuid4().hex[:8]}"

        # Map params
        vllm_sampling_params = VLLMSamplingParams(
            temperature=sampling_params.temperature,
            top_p=sampling_params.top_p,
            top_k=sampling_params.top_k,
            max_tokens=sampling_params.max_tokens,
            presence_penalty=sampling_params.presence_penalty,
            frequency_penalty=sampling_params.frequency_penalty,
            stop=sampling_params.stop,
            ignore_eos=sampling_params.ignore_eos
        )
        
        start_time = time.time()
        ttft_logged = False
        
        try:
            # Observability: Measure Latency
            with INFERENCE_LATENCY_SECONDS.labels(model=settings.MODEL_PATH).time():
                results_generator = self.engine.generate(
                    prompt,
                    vllm_sampling_params,
                    safe_request_id
                )

                last_text = ""
                async for request_output in results_generator:
                    if not request_output.outputs:
                        continue

                    current_text = request_output.outputs[0].text
                    
                    # TTFT Logging
                    if not ttft_logged and current_text:
                        ttft_ms = (time.time() - start_time) * 1000
                        logger.info("TTFT %.2f ms for %s", ttft_ms, safe_request_id)
                        ttft_logged = True
                    
                    delta = current_text[len(last_text):]
                    last_text = current_text
                    
                    if delta:
                        # Observability: Count Tokens
                        # (Approximate by chars or rely on vllm internal counts if accessible)
                        # Here we rely on delta len for simplicity in streaming context
                        # ideally we'd use output.token_ids change.
                        GENERATED_TOKENS_TOTAL.labels(model=settings.MODEL_PATH).inc(len(delta) // 4 + 1)
                        yield delta
                    
        except asyncio.CancelledError:
            logger.info(f"Generation cancelled for request {safe_request_id}")
            if hasattr(self.engine, "abort"):
                await self.engine.abort(safe_request_id)
            raise
        except Exception as e:
            logger.error(f"Generation failed for {safe_request_id}: {e}")
            raise

class MockInferenceEngine(InferenceEngine):
    """
    Fallback Engine for development/testing without GPU.
    Enabled ONLY if ALLOW_MOCK_INFERENCE is True.
    """
    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def generate(
        self, 
        prompt: str, 
        sampling_params: SamplingParams,
        request_id: str
    ) -> AsyncIterator[str]:
        
        mock_response = " This is a mock response from NovaLM running on CPU. "
        for ch in mock_response:
             await asyncio.sleep(0.02) 
             yield ch
            
_engine_instance = None

def get_inference_engine() -> InferenceEngine:
    global _engine_instance
    if _engine_instance:
        return _engine_instance
        
    if settings.ALLOW_MOCK_INFERENCE:
        logger.warning("Using Mock Inference Engine (ALLOW_MOCK_INFERENCE=True)")
        _engine_instance = MockInferenceEngine()
    else:
        _engine_instance = VLLMInferenceEngine()
    
    return _engine_instance
