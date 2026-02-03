import time
import uuid
from typing import AsyncIterator
from novalm.core.types import ChatCompletionRequest, ChatCompletionResponseChunk
from novalm.core.inference import InferenceEngine
from novalm.core.safety import SafetyLayer
from novalm.config.settings import settings

from novalm.core.memory import VectorMemory

class Orchestrator:
    """
    The Brain of NovaLM.
    Coordinates: Request -> Input Safety -> Inference -> Output Safety -> Response
    """
    
    def __init__(self, inference_engine: InferenceEngine, safety_layer: SafetyLayer):
        self.inference_engine = inference_engine
        self.safety_layer = safety_layer
        self.memory = VectorMemory() # Initialize Memory
        
    def _assemble_prompt(self, messages, tools=None) -> str:
        """
        Converts list of messages to a single prompt string.
        Injects RAG context and Tool definitions if available.
        """
        # 1. Extract latest user query
        latest_query = ""
        for msg in reversed(messages):
            if msg.role == "user":
                latest_query = msg.content
                break
        
        # 2. Retrieve Context
        context_str = ""
        if latest_query:
            retrieved_docs = self.memory.retrieve(latest_query)
            if retrieved_docs:
                context_str = "\nCONTEXT:\n" + "\n".join(retrieved_docs) + "\n"
        
        # 3. Prepare Tools Prompt
        tools_str = ""
        if tools:
            import json
            tools_desc = json.dumps(tools, indent=2)
            tools_str = f"\nAVAILABLE TOOLS:\n{tools_desc}\n\nTo use a tool, please output the JSON format of the tool call.\n"

        # 4. Build Prompt
        prompt = ""
        # Inject System Prompt with Context and Tools
        system_msg_found = False
        for msg in messages:
            role = msg.role.upper()
            content = msg.content
            
            if role == "SYSTEM":
                if context_str:
                    content += context_str
                if tools_str:
                    content += tools_str
                system_msg_found = True
                
            prompt += f"{role}: {content}\n"
            
        # If no system message but we have context/tools, prepend it
        prefix = ""
        if context_str:
            prefix += f"Use the following context to answer.\n{context_str}\n"
        if tools_str:
            prefix += f"{tools_str}"
            
        if prefix and not system_msg_found:
             prompt = f"SYSTEM: {prefix}\n" + prompt

        prompt += "ASSISTANT:"
        return prompt

    async def handle_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """
        Main entry point for handling chat requests.
        Returns an AsyncIterator yielding JSON-formatted string chunks (SSE data).
        """
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        model_name = request.model
        
        # 1. Assemble Prompt (with Tools)
        prompt = self._assemble_prompt(request.messages, request.tools)
        
        # 1.5 JSON Mode Injection
        if request.response_format and request.response_format.get("type") == "json_object":
             prompt = "SYSTEM: You must output a valid JSON object.\n" + prompt
        
        # 2. Input Safety Check
        if settings.ENABLE_SAFETY_CHECKS:
            try:
                self.safety_layer.check_input(prompt)
            except ValueError as e:
                # In streaming, we yield an error chunk or raising exception for middleware to catch
                # Ideally middleware catches this. We'll raise it.
                raise e

        # 3. Setup Sampling Params
        # Use request params or defaults
        sampling_params = request.sampling_params if request.sampling_params else None
        if sampling_params is None:
             # Create default 
             from novalm.core.types import SamplingParams
             sampling_params = SamplingParams()

        # 4. Inference & Output Safety
        from novalm.core.metrics import GENERATED_TOKENS_TOTAL
        
        token_count = 0

        async for text_chunk in self.inference_engine.generate(prompt, sampling_params, request_id):
            
            # Post-Inference Safety Check (Streaming)
            if settings.ENABLE_SAFETY_CHECKS:
                text_chunk = self.safety_layer.check_output(text_chunk)
            
            # Update Metrics
            # vLLM usually sends 1 token per chunk in streaming.
            GENERATED_TOKENS_TOTAL.labels(model=model_name).inc()
            token_count += 1
            
            # Construct Response Chunk
            chunk_data = ChatCompletionResponseChunk(
                id=request_id,
                created=created_time,
                model=model_name,
                choices=[{
                    "index": 0,
                    "delta": {"content": text_chunk},
                    "finish_reason": None
                }]
            )
            
            # Yield formatted SSE data
            yield chunk_data

        # Logging Usage (Structured)
        import logging
        # We don't have API key here directly, usually passed in context or assumption. 
        # But logs are useful anyway.
        logging.info(f"USAGE: request_id={request_id} model={model_name} tokens={token_count}")

        # Yield [DONE] is usually handled by the transport layer or a specific sentinel
        # We will finish here.
