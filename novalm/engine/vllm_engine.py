import asyncio
import os
from typing import AsyncIterator
from novalm.core.inference import InferenceEngine
from novalm.core.types import SamplingParams
from novalm.config.settings import settings

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
    """
    def __init__(self):
        self.engine = None
        
    def initialize(self):
        """
        Explicit initialization logic.
        Fails FAST if CUDA is not available.
        """
        if not VLLM_AVAILABLE:
            raise RuntimeError("vLLM is not installed. Cannot start VLLMInferenceEngine.")
            
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available. vLLM requires a GPU.")

        print(f"Initializing vLLM Engine with model: {settings.MODEL_PATH}...")
        
        engine_args = AsyncEngineArgs(
            model=settings.MODEL_PATH,
            trust_remote_code=settings.TRUST_REMOTE_CODE,
            max_model_len=settings.MAX_MODEL_LEN,
            gpu_memory_utilization=settings.GPU_MEMORY_UTILIZATION
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        print("vLLM Engine initialized successfully.")

    async def generate(
        self, 
        prompt: str, 
        sampling_params: SamplingParams,
        request_id: str
    ) -> AsyncIterator[str]:
        
        if not self.engine:
            raise RuntimeError("Engine not initialized. Call initialize() first.")
            
        # Map app-specific sampling params to vLLM params
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
        
        results_generator = self.engine.generate(
            prompt,
            vllm_sampling_params,
            request_id
        )

        async for request_output in results_generator:
            # vLLM returns the full text by default or deltas depending on version/config
            # Actually AsyncLLMEngine yields RequestOutput objects which contain the full text so far.
            # We need to calculate delta.
            
            # NOTE: For simplicity in this implementation, we assume just getting the latest delta
            # But vLLM `generate` yields cumulative output.
            # Correct logic:
            # We need to track previous length.
            # However, typically simple usage:
            # last_text = ""
            # for output in ...:
            #   current_text = output.outputs[0].text
            #   delta = current_text[len(last_text):]
            #   last_text = current_text
            #   yield delta
            pass 
        
        # Proper generator implementation
        last_text = ""
        async for request_output in results_generator:
            current_text = request_output.outputs[0].text
            delta = current_text[len(last_text):]
            last_text = current_text
            if delta:
                yield delta


class MockInferenceEngine(InferenceEngine):
    """
    Fallback Engine for development/testing without GPU.
    Enabled ONLY if ALLOW_MOCK_INFERENCE is True.
    """
    async def generate(
        self, 
        prompt: str, 
        sampling_params: SamplingParams,
        request_id: str
    ) -> AsyncIterator[str]:
        
        mock_response = " This is a mock response from NovaLM running on CPU. "
        words = mock_response.split(" ")
        for word in words:
            await asyncio.sleep(0.1) # Simulate token latency
            yield f"{word} "
            
# Factory to get the right engine
_engine_instance = None

def get_inference_engine() -> InferenceEngine:
    global _engine_instance
    if _engine_instance:
        return _engine_instance
        
    # Decision logic
    if settings.ALLOW_MOCK_INFERENCE:
        print("WARNING: Using Mock Inference Engine (ALLOW_MOCK_INFERENCE=True)")
        _engine_instance = MockInferenceEngine()
    else:
        # Default to Real Engine
        _engine_instance = VLLMInferenceEngine()
        # Note: We don't call initialize() here implicitly to keep control. 
        # But for 'get_instance' pattern often we expect it ready. 
        # Sticking to explicit lifecycle management in main.py is better.
    
    return _engine_instance
