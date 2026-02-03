import time
import uuid
import json
import logging
from typing import AsyncIterator, List, Dict, Any, Optional
from novalm.core.types import ChatCompletionRequest, ChatCompletionResponseChunk, ChatMessage
from novalm.core.inference import InferenceEngine
from novalm.core.safety import SafetyLayer
from novalm.config.settings import settings
from novalm.core.memory import VectorMemory
from novalm.core.tools import get_tool_by_name
from novalm.core.metrics import GENERATED_TOKENS_TOTAL

# Import Role Prompts
from novalm.core.prompts import (
    PLANNER_PROMPT, ARCHITECT_PROMPT, ENGINEER_PROMPT, 
    EVALUATOR_PROMPT, CRITIC_PROMPT, JSON_ENFORCEMENT,
    RESEARCH_PROBLEM_PROMPT, RESEARCH_HYPOTHESIS_PROMPT,
    RESEARCH_DESIGN_PROMPT, RESEARCH_EXECUTION_PROMPT,
    RESEARCH_ANALYSIS_PROMPT, AGENT_INSTRUCTIONS
)

# Import Research Schemas (Lazy import inside method or top level)
from novalm.core.schema import (
    PlannerOutput, ArchitectOutput, EngineerOutput, EvaluatorOutput, CriticOutput,
    ProblemAnalysis, HypothesisGen, ExperimentDesign, ExecutionRequest, AnalysisResult
)

class Orchestrator:
    """
    The Brain of NovaLM.
    Coordinates: Request -> Input Safety -> Inference -> Output Safety -> Response
    Supports: Simple Chat, Research Mode, and Autonomous FSM (vNext).
    """
    
    def __init__(self, inference_engine: InferenceEngine, safety_layer: SafetyLayer):
        self.inference_engine = inference_engine
        self.safety_layer = safety_layer
        self.memory = VectorMemory()
        
        from novalm.core.cache import CacheManager
        self.cache_manager = CacheManager()
        
    async def handle_chat(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """
        Main entry point. Dispatches to Autonomous Loop or Standard Loop.
        """
        if request.sampling_params and request.sampling_params.preset == "autonomous":
            async for chunk in self._run_autonomous_loop(request):
                yield chunk
        elif request.sampling_params and request.sampling_params.preset == "research":
             async for chunk in self._run_research_loop(request):
                yield chunk
        else:
            async for chunk in self._run_standard_loop(request):
                yield chunk

    async def _run_autonomous_loop(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """
        Phase 1: Finite State Machine for Autonomous Agents.
        Workflow: PLANNER -> ARCHITECT -> ENGINEER -> EVALUATOR -> CRITIC
        """
        request_id = f"auto-{uuid.uuid4()}"
        created_time = int(time.time())
        model_name = request.model
        
        # State Initialization
        state = "PLANNER"
        messages = list(request.messages)
        max_steps = 20 # Hard cap for safety
        steps = 0
        
        yield self._status_chunk(request_id, model_name, "[System: Starting Autonomous FSM...]")
        
        while state != "DONE" and steps < max_steps:
            steps += 1
            yield self._status_chunk(request_id, model_name, f"\n\n--- ROLE: {state} ---\n")
            
            # 1. Select Prompt
            system_prompt = self._get_prompt_for_role(state)
            
            # 2. Build Messages
            # We must ensure the System Prompt is correct for THIS role. 
            # We replace any existing system messages or prepend.
            # For simplicity, we create a fresh prompt sequence: System(Role) + History
            # But history might contain previous system prompts? We should filter them out for purity?
            # Or just append. Appending is safer to keep history.
            # Actually, standard practice is to have ONE system prompt at start.
            # We will override the content of the first message if it is system, or prepend.
            
            current_messages = [ChatMessage(role="system", content=system_prompt)] + [m for m in messages if m.role != "system"]
            
            # 3. Inference
            full_response = ""
            # Construct prompt string manually or use helper
            prompt_str = self._assemble_prompt_str(current_messages)
            
            # Use strict sampling for logic
            # Create a copy of sampling params or modify
            params = request.sampling_params
            if not params:
                from novalm.core.types import SamplingParams
                params = SamplingParams()
            
            params.temperature = 0.1
            params.max_tokens = 4096
            
            async for text_chunk in self.inference_engine.generate(prompt_str, params, f"{request_id}-{steps}"):
                 full_response += text_chunk
                 # Stream content to user so they see the thought process
                 yield ChatCompletionResponseChunk(
                    id=request_id, created=created_time, model=model_name,
                    choices=[{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}]
                )
            
            # 4. Parse & Transition Logic
            try:
                # Determine Schema based on Role
                from novalm.core.schema import PlannerOutput, ArchitectOutput, EngineerOutput, EvaluatorOutput, CriticOutput
                from novalm.core.parser import JsonOutputParser
                
                schema_map = {
                    "PLANNER": PlannerOutput,
                    "ARCHITECT": ArchitectOutput,
                    "ENGINEER": EngineerOutput,
                    "EVALUATOR": EvaluatorOutput,
                    "CRITIC": CriticOutput
                }
                
                current_schema = schema_map.get(state)
                # Parse Strict
                model_output = JsonOutputParser.parse(full_response, current_schema)
                # Convert back to dict for generic handling or use object
                # For minimal refactoring, we use model_output.model_dump()
                data = model_output.model_dump()
                
                # Update History
                messages.append(ChatMessage(role="assistant", content=full_response))
                
                # FSM Transitions
                if state == "PLANNER":
                    # Planner outputs milestones.
                    # Output: {"role": "planner", "milestones": [...]}
                    state = "ARCHITECT"
                    
                elif state == "ARCHITECT":
                    # Architect outputs file structure.
                    state = "ENGINEER"
                    
                elif state == "ENGINEER":
                    action = data.get("action")
                    if action == "final_answer":
                        state = "EVALUATOR"
                    elif action:
                        # Tool Execution
                        tool_input = data.get("input", {})
                        yield self._status_chunk(request_id, model_name, f"\n[Executing {action}...]\n")
                        
                        tool_output = await self._execute_tool(action, tool_input)
                        
                        messages.append(ChatMessage(role="system", content=f"Tool Output: {json.dumps(tool_output)}"))
                        # Stay in ENGINEER to continue implementing or fix errors
                    else:
                        messages.append(ChatMessage(role="system", content="Error: No action found."))
                        
                elif state == "EVALUATOR":
                    status = data.get("status")
                    if data.get("action") == "python_exec":
                         # Running a test
                         yield self._status_chunk(request_id, model_name, "\n[Running Tests...]\n")
                         tool_output = await self._execute_tool("python_exec", data.get("input", {}))
                         messages.append(ChatMessage(role="system", content=f"Test Results: {json.dumps(tool_output)}"))
                         # Stay in Evaluator to analyze results
                    elif status == "pass":
                        state = "CRITIC"
                    else:
                        # Fail -> Back to Engineer
                        messages.append(ChatMessage(role="system", content=f"Evaluator Feedback: {data.get('issues')}"))
                        state = "ENGINEER"

                elif state == "CRITIC":
                    if data.get("approved"):
                        yield self._status_chunk(request_id, model_name, "\n[System: Task Completed Successfully]\n")
                        
                        # SAVE EPISODIC MEMORY (SUCCESS)
                        user_task = messages[0].content # Simplified: First msg is User or System?
                        # Actually first msg in `messages` list passed to loop.
                        # `request.messages` are user provided.
                        # We should iterate to find USER msg.
                        user_query = "Unknown Task"
                        for m in reversed(request.messages):
                            if m.role == "user":
                                user_query = m.content
                                break
                        
                        # We save the final Assistant Code or Conversation?
                        # Ideally the final solution artifact. 
                        # But loop history is long.
                        # Let's save the summary.
                        self.memory.add_episodic(
                            task=user_query,
                            solution="See conversation history.", # TODO: extract final code
                            outcome="SUCCESS",
                            feedback=data.get("critique", "Approved")
                        )
                        state = "DONE"
                    else:
                        messages.append(ChatMessage(role="system", content=f"Critic Feedback: {data.get('feedback')}"))
                        state = "ENGINEER" # Fix critique
                        
            except ValueError as e:
                # Validation Failed
                logging.error(f"FSM Parsing Error: {e}")
                err_msg = f"SYSTEM: Output validation failed. {str(e)}. Please output VALID JSON strictly adhering to the schema."
                yield self._status_chunk(request_id, model_name, f"\n[System: Invalid JSON. Retrying...]\n")
                messages.append(ChatMessage(role="system", content=err_msg))
                # Retry same state (loop continues)
            except Exception as e:
                logging.error(f"FSM Error: {e}")
                messages.append(ChatMessage(role="system", content=f"Error: {e}"))
    async def _run_research_loop(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """
        Phase 4: Scientific Method FSM.
        States: PROBLEM -> HYPOTHESIS -> DESIGN -> EXECUTION -> ANALYSIS
        """
        request_id = f"res-{uuid.uuid4()}"
        created_time = int(time.time())
        model_name = request.model
        
        state = "PROBLEM"
        messages = list(request.messages)
        max_steps = 15
        steps = 0
        
        from novalm.core.parser import JsonOutputParser
        
        yield self._status_chunk(request_id, model_name, "[System: Starting Research FSM...]")
        
        while state != "DONE" and steps < max_steps:
            steps += 1
            yield self._status_chunk(request_id, model_name, f"\n\n--- PHASE: {state} ---\n")
            
            # 1. Select Prompt
            system_prompt = self._get_prompt_for_research_role(state)
            
            # 2. Build Messages (System + History)
            current_messages = [ChatMessage(role="system", content=system_prompt)] + [m for m in messages if m.role != "system"]
            
            # 3. Inference
            prompt_str = self._assemble_prompt_str(current_messages)
            
            # Use specific params for Research (higher context, lower temp)
            params = request.sampling_params
            if not params:
                 from novalm.core.types import SamplingParams
                 params = SamplingParams()
            params.temperature = 0.2
            params.max_tokens = 4096
            
            full_response = ""
            async for text_chunk in self.inference_engine.generate(prompt_str, params, f"{request_id}-{steps}"):
                 full_response += text_chunk
                 yield ChatCompletionResponseChunk(
                    id=request_id, created=created_time, model=model_name,
                    choices=[{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}]
                )
            
            # 4. Parse & Transition
            try:
                # Determine Schema
                if state == "PROBLEM": schema = ProblemAnalysis
                elif state == "HYPOTHESIS": schema = HypothesisGen
                elif state == "DESIGN": schema = ExperimentDesign
                elif state == "EXECUTION": schema = ExecutionRequest
                elif state == "ANALYSIS": schema = AnalysisResult
                else: schema = AnalysisResult # fallback
                
                model_output = JsonOutputParser.parse(full_response, schema)
                data = model_output.model_dump()
                
                # Append History
                messages.append(ChatMessage(role="assistant", content=full_response))
                
                # FSM Logic
                if state == "PROBLEM":
                    # Action: Search Literature?
                    keywords = data.get("literature_keywords", [])
                    if keywords and "pdf_reader" in [t["function"]["name"] for t in (request.tools or [])]:
                        # If tool available, we could trigger it. 
                        # For now, we assume user provides context or we skip search to save tokens.
                        # Ideally: INTERMEDIATE state "LITERATURE_SEARCH".
                        pass
                    state = "HYPOTHESIS"
                    
                elif state == "HYPOTHESIS":
                    state = "DESIGN"
                    
                elif state == "DESIGN":
                    state = "EXECUTION"
                    
                elif state == "EXECUTION":
                    action = data.get("action")
                    if action:
                        yield self._status_chunk(request_id, model_name, f"\n[Running Experiment: {action}...]\n")
                        tool_output = await self._execute_tool(action, data.get("input", {}))
                        messages.append(ChatMessage(role="system", content=f"Experiment Output: {json.dumps(tool_output)}"))
                        state = "ANALYSIS"
                    else:
                        state = "ANALYSIS" # Skip execution if no action? Or retry?
                        
                elif state == "ANALYSIS":
                    if data.get("next_step") == "done":
                        yield self._status_chunk(request_id, model_name, "\n[System: Research Concluded]\n")
                        
                        # SAVE SEMANTIC MEMORY (Knowledge)
                        self.memory.add_semantic(
                            content=f"Research Conclusion: {data.get('conclusion')}\nObservation: {data.get('observation')}",
                            source="research_agent"
                        )
                        state = "DONE"
                    else:
                        state = "HYPOTHESIS" # Refine
                        
            except ValueError as e:
                logging.error(f"Research FSM Error: {e}")
                err_msg = f"SYSTEM: Validation failed: {e}. Retry with valid JSON."
                messages.append(ChatMessage(role="system", content=err_msg))
            except Exception as e:
                logging.error(f"Research FSM Error: {e}")
                messages.append(ChatMessage(role="system", content=f"Error: {e}"))

        """
        The Standard Orchestrator Loop (Legacy + Research Mode).
        """
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        model_name = request.model
        
        # 1. Assemble Prompt
        prompt = self._assemble_prompt(request.messages, request.tools)
        
        # 1.5 JSON Mode Injection
        if request.response_format and request.response_format.get("type") == "json_object":
             prompt = "SYSTEM: You must output a valid JSON object.\n" + prompt
        
        # 2. Input Safety Check
        if settings.ENABLE_SAFETY_CHECKS:
            try:
                self.safety_layer.check_input(prompt)
            except ValueError as e:
                yield self._error_chunk(request_id, str(e))
                return

        # 3. Setup Sampling Params
        sampling_params = request.sampling_params if request.sampling_params else None
        if sampling_params is None:
             from novalm.core.types import SamplingParams
             sampling_params = SamplingParams()
             
        # Apply Presets
        if sampling_params.preset == "deterministic" or sampling_params.preset == "coding":
            sampling_params.temperature = 0.1
            sampling_params.top_p = 0.1
            sampling_params.max_tokens = max(sampling_params.max_tokens, 1024)
        elif sampling_params.preset == "creative":
            sampling_params.temperature = 0.9
            sampling_params.top_p = 0.95
        elif sampling_params.preset == "research":
            sampling_params.temperature = 0.2
            sampling_params.top_p = 0.95
            sampling_params.max_tokens = 2048

        # 4. Inference loop (ReAct)
        max_steps = 5
        current_step = 0
        is_agent_mode = bool(request.tools)
        messages = list(request.messages)
        
        while current_step < max_steps:
            current_step += 1
            request_id_step = f"{request_id}-step-{current_step}"
            
            # Re-assemble prompt if loop
            prompt = self._assemble_prompt(messages, request.tools)
            
            # 4.5.0 Research Persona Injection
            if sampling_params and sampling_params.preset == "research":
                prompt = "SYSTEM: " + RESEARCH_SYSTEM_PROMPT + "\n" + prompt.replace("SYSTEM: ", "", 1)

            # 4.5.1 Agent JSON Enforcement
            if is_agent_mode:
                prompt += AGENT_INSTRUCTIONS

            # Inference
            collected_response = ""
            
            # Cache Check
            cached_text = None
            if self.cache_manager:
                 cached_text = self.cache_manager.get(prompt, sampling_params)
            
            if cached_text:
                collected_response = cached_text
                yield ChatCompletionResponseChunk(
                        id=request_id, created=created_time, model=model_name,
                        choices=[{"index": 0, "delta": {"content": cached_text}, "finish_reason": "stop"}]
                    )
            else:
                try:
                    async for text_chunk in self.inference_engine.generate(prompt, sampling_params, request_id_step):
                        if settings.ENABLE_SAFETY_CHECKS:
                            text_chunk = self.safety_layer.check_output(text_chunk)
                        
                        collected_response += text_chunk
                        GENERATED_TOKENS_TOTAL.labels(model=model_name).inc()
                        
                        yield ChatCompletionResponseChunk(
                            id=request_id, created=created_time, model=model_name,
                            choices=[{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}]
                        )
                    
                    if self.cache_manager and collected_response:
                        self.cache_manager.set(prompt, collected_response, sampling_params)
                        
                except Exception as e:
                     logging.error(f"Inference error: {e}")
                     yield self._error_chunk(request_id, str(e))
                     return

            if not is_agent_mode:
                break

            # Agent Logic: Parse & Act (Simplistic ReAct)
            tool_action = None
            try:
                start = collected_response.find("{")
                end = collected_response.rfind("}")
                if start != -1 and end != -1:
                    data = json.loads(collected_response[start:end+1])
                    if "action" in data and data["action"] != "final_answer":
                        tool_action = data
            except: pass
                
            if tool_action:
                tool_name = tool_action.get("action")
                tool_input = tool_action.get("input", {})
                
                yield ChatCompletionResponseChunk(
                    id=request_id, created=created_time, model=model_name,
                    choices=[{"index": 0, "delta": {"content": f"\n\n[System: Executing {tool_name}...]\n\n"}, "finish_reason": None}]
                )
                
                tool_output = await self._execute_tool(tool_name, tool_input)
                
                # Loop continuation
                messages.append(ChatMessage(role="assistant", content=collected_response))
                messages.append(ChatMessage(role="system", content=f"Tool Output: {json.dumps(tool_output)}"))
            else:
                break # Failed to parse or final answer

    def _assemble_prompt(self, messages, tools=None) -> str:
        # 1. Extract latest user query
        latest_query = ""
        for msg in reversed(messages):
            if msg.role == "user":
                latest_query = msg.content
                break
        
        # 2. Retrieve Context & Experiences (Multi-Layer Memory)
        context_str = ""
        episodic_str = ""
        semantic_str = ""
        procedural_str = ""
        
        if latest_query:
            # We call the new retrieve_all method via cast or direct usage if typed
            # Or retrieve individually for control
            
            # A. Episodic (Past Runs)
            episodes = self.memory.retrieve_episodic(latest_query)
            if episodes:
                episodic_str = "\n[MEMORY: PAST EPISODES]\n" + "\n".join(episodes) + "\n"
            
            # B. Semantic (Knowledge)
            semantics = self.memory.retrieve_semantic(latest_query)
            if semantics:
                semantic_str = "\n[MEMORY: KNOWLEDGE BASE]\n" + "\n".join(semantics) + "\n"
                
            # C. Procedural (Heuristics)
            procedures = self.memory.retrieve_procedural(latest_query)
            if procedures:
                procedural_str = "\n[MEMORY: RECOMMENDED WORKFLOWS]\n" + "\n".join(procedures) + "\n"
        
        # Combine into a single Memory Block
        memory_block = ""
        if episodic_str: memory_block += episodic_str
        if semantic_str: memory_block += semantic_str
        if procedural_str: memory_block += procedural_str
        
        # 3. Prepare Tools Prompt
        tools_str = ""
        if tools:
            tools_desc = json.dumps(tools, indent=2)
            tools_str = f"\nAVAILABLE TOOLS:\n{tools_desc}\n\nTo use a tool, please output the JSON format of the tool call.\n"

        # 4. Build Prompt
        prompt = ""
        system_msg_found = False
        for msg in messages:
            role = msg.role.upper()
            content = msg.content
            if role == "SYSTEM":
                content += "\n" + memory_block
                if tools_str: content += tools_str
                system_msg_found = True
            prompt += f"{role}: {content}\n"
            
        prefix = ""
        if tools_str: prefix += f"{tools_str}"
            
        if prefix and not system_msg_found:
             prompt = f"SYSTEM: {prefix}{memory_block}\n" + prompt

        prompt += "ASSISTANT:"
        return prompt

    def _get_prompt_for_role(self, role: str) -> str:
        if role == "PLANNER": return PLANNER_PROMPT
        if role == "ARCHITECT": return ARCHITECT_PROMPT
        if role == "ENGINEER": return ENGINEER_PROMPT
        if role == "EVALUATOR": return EVALUATOR_PROMPT
        if role == "CRITIC": return CRITIC_PROMPT
        return JSON_ENFORCEMENT

    async def _execute_tool(self, name: str, input_data: dict) -> dict:
        tool = get_tool_by_name(name)
        if tool:
            try:
                return await tool.run(input_data)
            except Exception as e:
                return {"error": str(e)}
        return {"error": "Tool not found"}

    def _get_prompt_for_research_role(self, role: str) -> str:
        if role == "PROBLEM": return RESEARCH_PROBLEM_PROMPT
        if role == "HYPOTHESIS": return RESEARCH_HYPOTHESIS_PROMPT
        if role == "DESIGN": return RESEARCH_DESIGN_PROMPT
        if role == "EXECUTION": return RESEARCH_EXECUTION_PROMPT
        if role == "ANALYSIS": return RESEARCH_ANALYSIS_PROMPT
        return JSON_ENFORCEMENT
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        raise ValueError("No JSON found")

    def _assemble_prompt_str(self, messages: List[ChatMessage]) -> str:
        prompt = ""
        for msg in messages:
            prompt += f"{msg.role.upper()}: {msg.content}\n"
        prompt += "ASSISTANT:"
        return prompt

    def _status_chunk(self, req_id, model, msg):
        return ChatCompletionResponseChunk(
             id=req_id, created=int(time.time()), model=model,
             choices=[{"index": 0, "delta": {"content": msg}, "finish_reason": None}]
        )

    def _error_chunk(self, request_id, message):
         return ChatCompletionResponseChunk(
             id=request_id, created=int(time.time()), model="error",
             choices=[{"index": 0, "delta": {"content": f"Error: {message}"}, "finish_reason": "error"}]
        )
