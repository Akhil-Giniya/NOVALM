from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any, Literal

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class SamplingParams(BaseModel):
    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int = -1
    max_tokens: int = 256
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    stop: Optional[Union[str, List[str]]] = None
    ignore_eos: bool = False
    
    # Execution Mode Presets
    preset: Optional[Literal["creative", "deterministic", "coding", "research"]] = None
    
    # Self-Correction
    max_debug_attempts: int = 3

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    sampling_params: Optional[SamplingParams] = None
    stream: bool = False
    
    # Tool Use Support
    tools: Optional[List[Dict[str, Any]]] = None 
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    
    # Structured Output
    response_format: Optional[Dict[str, str]] = None # e.g. {"type": "json_object"}
    
    # Evaluation / Self-Correction
    test_code: Optional[str] = None # Code to run to verify the answer
    
    # Allow extra fields for flexibility but validate the core ones
    class Config:
        extra = "allow" 

class ChatCompletionResponseChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]
