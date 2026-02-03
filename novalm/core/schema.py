from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field

class PlannerOutput(BaseModel):
    role: Literal["planner"] = "planner"
    analysis: str = Field(..., description="Understanding of the request and requirements.")
    milestones: List[str] = Field(..., description="High-level steps to achieve the goal.")
    next_step: Literal["handoff_to_architect"] = "handoff_to_architect"

class ArchitectOutput(BaseModel):
    role: Literal["architect"] = "architect"
    design_rationale: str = Field(..., description="Why this architecture was chosen.")
    file_structure: Dict[str, str] = Field(..., description="Map of filename to description.")
    next_step: Literal["handoff_to_engineer"] = "handoff_to_engineer"

class EngineerOutput(BaseModel):
    role: Literal["engineer"] = "engineer"
    thought: str = Field(..., description="Reasoning for the current action.")
    action: str = Field(..., description="Tool name or 'final_answer'.")
    input: Dict[str, Any] = Field(..., description="Input arguments for the tool.")

class EvaluatorOutput(BaseModel):
    role: Literal["evaluator"] = "evaluator"
    test_plan: str = Field(..., description="What is being tested.")
    action: Optional[Literal["python_exec"]] = None
    input: Optional[Dict[str, Any]] = None
    status: Literal["pass", "fail", "running"] = Field(..., description="Current evaluation status.")
    issues: List[str] = Field(default_factory=list, description="List of issues found.")
    next_step: Literal["hand_to_critic", "retry_engineer", "continue_testing"] 

class CriticOutput(BaseModel):
    role: Literal["critic"] = "critic"
    critique: str = Field(..., description="Critical review of the solution.")
    approved: bool = Field(..., description="Whether the solution is accepted.")
    feedback: str = Field(..., description="Feedback for fixes if rejected.")

# --- RESEARCH SCHEMAS (Phase 4) ---

class ProblemAnalysis(BaseModel):
    role: Literal["researcher_analysis"] = "researcher_analysis"
    core_challenge: str = Field(..., description="The fundamental technical problem.")
    literature_keywords: List[str] = Field(..., description="Keywords to search in docs/PDFs.")
    next_step: Literal["hypothesis"] = "hypothesis"

class HypothesisGen(BaseModel):
    role: Literal["researcher_hypothesis"] = "researcher_hypothesis"
    hypothesis_statement: str = Field(..., description="Proposed theory or solution.")
    expected_outcome: str = Field(..., description="What we expect to see if true.")
    novelty_argument: str = Field(..., description="Why this hasn't been done before (or differ).")
    next_step: Literal["design"] = "design"

class ExperimentDesign(BaseModel):
    role: Literal["researcher_design"] = "researcher_design"
    metrics: List[str] = Field(..., description="KPIs to measure (e.g. latency, accuracy).")
    baseline: str = Field(..., description="What we are comparing against.")
    implementation_plan: str = Field(..., description="Steps to implement the experiment.")
    next_step: Literal["execution"] = "execution"

class ExecutionRequest(BaseModel):
    # Re-use EngineerOutput technically, but specific for research
    role: Literal["researcher_execution"] = "researcher_execution"
    thought: str = Field(...)
    action: str = Field(...)
    input: Dict[str, Any] = Field(...)

class AnalysisResult(BaseModel):
    role: Literal["researcher_result"] = "researcher_result"
    observation: str = Field(..., description="What happened during experiment.")
    supported: bool = Field(..., description="Was hypothesis supported?")
    conclusion: str = Field(..., description="Final scientific conclusion.")
    next_step: Literal["done", "refine_hypothesis"]
