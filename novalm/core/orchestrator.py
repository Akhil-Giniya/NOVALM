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
        
        from novalm.core.cache import CacheManager
        self.cache_manager = CacheManager()
        
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
        
        # 2. Retrieve Context & Experiences
        context_str = ""
        experience_str = ""
        if latest_query:
            # RAG Docs
            retrieved_docs = self.memory.retrieve_documents(latest_query)
            if retrieved_docs:
                context_str = "\nCONTEXT:\n" + "\n".join(retrieved_docs) + "\n"
            
            # Past Experiences (Memory)
            # Only retrieve if we have a query.
            experiences = self.memory.retrieve_experiences(latest_query)
            if experiences:
                experience_str = "\nNOVELTY CHECK - EXISTING KNOWLEDGE:\n" + "\n".join(experiences) + "\n(Warning: Do not simply repeat these if they failed. If they succeeded, try to improve or apply to new context.)\n"
        
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
                if experience_str:
                    content += experience_str
                if tools_str:
                    content += tools_str
                system_msg_found = True
                
            prompt += f"{role}: {content}\n"
            
        # If no system message but we have context/tools, prepend it
        prefix = ""
        if context_str:
            prefix += f"Use the following context to answer.\n{context_str}\n"
        if experience_str:
            prefix += f"{experience_str}"
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
             
        # Apply Presets (Execution Mode)
        if sampling_params.preset == "deterministic" or sampling_params.preset == "coding":
            sampling_params.temperature = 0.1
            sampling_params.top_p = 0.1
            sampling_params.max_tokens = max(sampling_params.max_tokens, 1024) # Ensure capacity for code
        elif sampling_params.preset == "creative":
            sampling_params.temperature = 0.9
            sampling_params.top_p = 0.95
        elif sampling_params.preset == "research":
            sampling_params.temperature = 0.2
            sampling_params.top_p = 0.95
            sampling_params.max_tokens = 2048 # Research needs long output

        # 4. Inference & Output Safety
        from novalm.core.metrics import GENERATED_TOKENS_TOTAL
        
        token_count = 0

        # Agent Loop (ReAct)
        max_steps = 5
        current_step = 0
        
        # Helper to detect if we should run in agent mode
        is_agent_mode = bool(request.tools)
        
        # Tools Registry
        from novalm.core.tools import get_tool_by_name
        
        # Working messages list (local copy)
        messages = list(request.messages)
        
        while current_step < max_steps:
            current_step += 1
            request_id_step = f"{request_id}-step-{current_step}"
            
            # 1. Assemble Prompt
            prompt = self._assemble_prompt(messages, request.tools)
            
            # 1.5.0 Research Persona Injection (if preset is request)
            # We modify the prompt or inject strict system message if not present?
            # _assemble_prompt handles context/tools. 
            # If research preset is active, we should prepend the Research System Prompt if possible.
            # But prompt assembly already happened.
            # Let's simple append instructions or handle it better in _assemble_prompt.
            # For iteration speed, we inject high-level instructions here.
            
            if sampling_params and sampling_params.preset == "research":
                from novalm.core.prompts import RESEARCH_SYSTEM_PROMPT
                # If prompt start with system, replace it? Or just pre-pend.
                # Our assembled prompt is "SYSTEM: ... \n ... ASSISTANT:"
                # We can replace the default system prompt if we had one.
                # Simplified: Just ensure the model knows it's a researcher.
                prompt = "SYSTEM: " + RESEARCH_SYSTEM_PROMPT + "\n" + prompt.replace("SYSTEM: ", "", 1)

            # 1.5.1 Agent JSON Enforcement
            if is_agent_mode:
                from novalm.core.prompts import AGENT_INSTRUCTIONS
                prompt += AGENT_INSTRUCTIONS

            # 2. Input Safety
            if settings.ENABLE_SAFETY_CHECKS:
                 try:
                     self.safety_layer.check_input(prompt)
                 except ValueError:
                     yield self._error_chunk(request_id, "Safety Violation in Input")
                     return

            # 3. Inference
            token_count = 0
            collected_response = ""
            
            # CACHE CHECK
            # Only cache if NOT in strict agent execution loop with side-effects? 
            # Actually, safe to cache generation if prompt is same.
            cached_text = None
            if self.cache_manager:
                 cached_text = self.cache_manager.get(prompt, sampling_params)
            
            if cached_text:
                # HIT: Yield immediately
                collected_response = cached_text
                yield ChatCompletionResponseChunk(
                        id=request_id,
                        created=created_time,
                        model=model_name,
                        choices=[{"index": 0, "delta": {"content": cached_text}, "finish_reason": "stop"}]
                    )
            else:
                # MISS: Run Inference
                try:
                    async for text_chunk in self.inference_engine.generate(prompt, sampling_params, request_id_step):
                        # Safety
                        if settings.ENABLE_SAFETY_CHECKS:
                            text_chunk = self.safety_layer.check_output(text_chunk)
                        
                        # Accumulate for tool parsing
                        collected_response += text_chunk
                        token_count += 1
                        GENERATED_TOKENS_TOTAL.labels(model=model_name).inc()
                        
                        # Yield chunk to user
                        yield ChatCompletionResponseChunk(
                            id=request_id,
                            created=created_time,
                            model=model_name,
                            choices=[{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}]
                        )
                    
                    # CACHE SET
                    if self.cache_manager and collected_response:
                        self.cache_manager.set(prompt, collected_response, sampling_params)
                        
                except Exception as e:
                     import logging
                     logging.error(f"Inference error: {e}")
                     yield self._error_chunk(request_id, str(e))
                     return

            if not is_agent_mode:
                break # Simple chat, done after one turn using break logic above, 
                # but we need to verify indentation. 
                # The 'if not is_agent_mode: break' is currently AFTER the try/except block.
                # Correct.

            if not is_agent_mode:
                break # Simple chat, done after one turn

            # 4. Agent Logic: Parse & Act
            import json
            tool_action = None
            try:
                # Naive JSON parsing (look for first { and last })
                start = collected_response.find("{")
                end = collected_response.rfind("}")
                if start != -1 and end != -1:
                    json_str = collected_response[start:end+1]
                    data = json.loads(json_str)
                    if "action" in data and data["action"] != "final_answer":
                        tool_action = data
            except:
                pass # Not a valid JSON action, treat as text
                
            if tool_action:
                tool_name = tool_action.get("action")
                tool_input = tool_action.get("input", {})
                
                # Yield "Tool Execution" notification (as content for now)
                yield ChatCompletionResponseChunk(
                    id=request_id,
                    created=created_time,
                    model=model_name,
                    choices=[{"index": 0, "delta": {"content": f"\n\n[System: Executing {tool_name}...]\n\n"}, "finish_reason": None}]
                )
                
                tool = get_tool_by_name(tool_name)
                tool_output = None
                
                if tool:
                    try:
                        tool_output = await tool.run(tool_input)
                    except Exception as e:
                        tool_output = {"error": str(e)}
                else:
                    tool_output = {"error": f"Tool {tool_name} not found."}
                
                # --- AUTOMATED DEBUG LOOP (Self-Correction) ---
                # Check if we should run the Evaluator
                debug_feedback = None
                if request.test_code and (tool_name == "python_exec" or tool_name == "write_file"):
                     # Condition: User provided tests AND agent just wrote/ran code.
                     # We assume the agent's action affects the environment or defines the code.
                     # Logic:
                     # 1. If python_exec, the code is in tool_input["code"].
                     # 2. If write_file, the code is in a file, we might need to read it or just run the test if the test imports it.
                     
                     code_to_eval = ""
                     if tool_name == "python_exec":
                         code_to_eval = tool_input.get("code", "")
                     elif tool_name == "write_file":
                         # For write_file, the code is on disk. The test_code presumably imports it or reads it.
                         # We'll pass empty code string, letting test_code handle imports if file exists.
                         # Or we could try to read it if filename is python.
                         pass 
                         
                     # Run Evaluator
                     from novalm.core.evaluator import Evaluator
                     evaluator = Evaluator()
                     # If we are in a debug loop, checks attempts
                     # We reuse 'current_step' as a proxy for attempts in this loop, 
                     # but really we should track debug attempts separately or just let max_steps handle it.
                     # Let's rely on max_steps for now to keep it simple, 
                     # but give explicit feedback.
                     
                     eval_result = await evaluator.evaluate(code_to_eval, request.test_code)
                     
                     if eval_result["status"] == "FAIL":
                         debug_feedback = f"\nSYSTEM EVALUATION:\nTEST FAILED.\nFEEDBACK: {eval_result['feedback']}\n\nYou must fix the code. Analyze the error and try again."
                         tool_output = {"tool_output": tool_output, "evaluator_feedback": debug_feedback}
                         
                         yield ChatCompletionResponseChunk(
                            id=request_id,
                            created=created_time,
                            model=model_name,
                            choices=[{"index": 0, "delta": {"content": f"\n\n[System: Tests Failed. Auto-Correcting...]\n\n"}, "finish_reason": None}]
                        )
                     else:
                         tool_output = {"tool_output": tool_output, "evaluator_feedback": "TEST PASSED! Great job."}
                         yield ChatCompletionResponseChunk(
                            id=request_id,
                            created=created_time,
                            model=model_name,
                            choices=[{"index": 0, "delta": {"content": f"\n\n[System: Tests Passed!]\n\n"}, "finish_reason": None}]
                        )

                     # SAVE EXPERIENCE TO MEMORY
                     # Task: The last user query.
                     # Solution: The code (if python_exec) or tool action.
                     # Outcome: SUCCESS/FAIL from evaluator, or just generic success if no eval.
                     outcome = eval_result["status"] if eval_result else "SUCCESS"
                     feedback = debug_feedback if debug_feedback else ""
                     
                     # Simple heuristic: If we ran code, save it.
                     task_query = messages[-1].content # Wait, messages list is appending assistant responses. 
                     # We need the original User Query.
                     # It is tricky to get exact "Task" from linear history without structure. 
                     # For MVP, we use the initial request prompt or search back for USER role.
                     
                     user_task = "Unknown Task"
                     for m in reversed(request.messages):
                         if m.role == "user":
                             user_task = m.content
                             break
                             
                     self.memory.add_experience(
                        task=user_task,
                        solution=f"Action: {tool_name}\nInput: {json.dumps(tool_input)}",
                        outcome=outcome,
                        feedback=feedback
                     )

                # Append to history
                from novalm.core.types import ChatMessage
                messages.append(ChatMessage(role="assistant", content=collected_response))
                messages.append(ChatMessage(role="system", content=f"Tool Output: {json.dumps(tool_output)}"))
                
                # Continue loop
            else:
                # No tool action or final answer
                break
                
        # Logging Usage
        import logging
        logging.info(f"USAGE: request_id={request_id} model={model_name} total_steps={current_step}")

    def _error_chunk(self, request_id, message):
         return {
            "error": {
                "message": message,
                "type": "internal_error",
                "code": 500
            }
        }
