from abc import ABC, abstractmethod
from typing import AsyncIterator, List
from novalm.core.types import SamplingParams

class InferenceEngine(ABC):
    """
    Abstract Base Class for the Inference Engine.
    Enforces a strict contract for all inference backends (vLLM, HuggingFace, Mock, etc).
    """
    
    async def initialize(self):
        """
        Initializes the engine (loading models, allocating resources).
        Should be calling before generate() is used.
        """
        pass

    async def shutdown(self):
        """
        Cleans up resources (GPU memory, connections) before exit.
        """
        pass

    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        sampling_params: SamplingParams,
        request_id: str
    ) -> AsyncIterator[str]:
        """
        Generates text based on the prompt and sampling parameters.
        Must return an AsyncIterator that yields strings (tokens/chunks).
        """
        pass
