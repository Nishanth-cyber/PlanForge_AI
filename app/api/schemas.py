"""Pydantic request and response schemas for the PlanForge REST API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GenerationRequest(BaseModel):
    """Client request initiating a residential floor-plan generation run."""
    model_config = ConfigDict(extra="ignore")

    brief: Optional[str] = Field(
        default=None,
        description="Freeform natural-language architectural brief describing plot, setbacks, and room requirements.",
    )
    project_name: str = Field(
        default="PlanForge Residential Project",
        description="Human-readable project title.",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Optional unique project identifier. If omitted, generated automatically.",
    )
    plot_shape: Optional[List[List[float]]] = Field(
        default=None,
        description="Optional list of [x, y] coordinates defining an irregular plot boundary polygon in meters.",
    )
    num_alternatives: int = Field(
        default=1,
        ge=1,
        le=6,
        description="Number of structurally distinct valid alternatives to generate (1-6).",
    )
    enable_refinement: bool = Field(
        default=True,
        description="Whether to run the closed-loop iterative refinement agent on validation warnings/errors.",
    )
    max_refinement_iterations: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum refinement iterations before terminating.",
    )
    enable_rendering: bool = Field(
        default=True,
        description="Whether to render publication-grade floor-plan images (PNG).",
    )
    enable_exports: bool = Field(
        default=True,
        description="Whether to export complete project bundles (JSON, Markdown, rendered images).",
    )
    create_zip: bool = Field(
        default=False,
        description="Whether to create an optional ZIP archive of the complete export bundle.",
    )
    output_dir: str = Field(
        default="outputs",
        description="Root output directory where export bundles are stored.",
    )


class ValidationSummarySchema(BaseModel):
    """High-level summary of authoritative validation results."""
    overall_valid: bool
    overall_score: float
    total_errors: int
    total_warnings: int


class AlternativeSummarySchema(BaseModel):
    """Summary of an individual generated architectural design alternative."""
    alternative_id: str
    index: int
    strategy: str
    is_valid: bool
    characteristics: List[str] = Field(default_factory=list)
    diversity_scores: Dict[str, float] = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    """Structured response returned by the floor-plan generation endpoint."""
    project_id: str
    project_name: str
    status: str  # "completed", "incomplete_requirements", "failed"
    is_success: bool
    is_valid: bool
    stage_statuses: Dict[str, str] = Field(default_factory=dict)
    validation_summary: Optional[ValidationSummarySchema] = None
    alternatives: List[AlternativeSummarySchema] = Field(default_factory=list)
    export_bundle_path: Optional[str] = None
    decision_trace_available: bool = False
    missing_fields: List[str] = Field(default_factory=list)
    missing_floors: List[int] = Field(default_factory=list)
    clarification_questions: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    """System diagnostic and health status."""
    status: str = "ok"
    service: str = "PlanForge AI"
    version: str = "0.1.0"
    llm_provider: str = "unknown"
    device: str = "CPU (headless Agg)"


class ExportFileItem(BaseModel):
    """Metadata describing an exported project artifact."""
    filename: str
    relative_path: str
    size_bytes: int
    media_type: str


class ExportResponse(BaseModel):
    """Export bundle inventory response."""
    project_id: str
    bundle_path: str
    total_files: int
    files: List[ExportFileItem] = Field(default_factory=list)


class ProjectDetailResponse(BaseModel):
    """Summary record of a stored generated project."""
    project_id: str
    project_name: str
    status: str
    is_valid: bool
    created_at: Optional[str] = None
    validation_summary: Optional[ValidationSummarySchema] = None
    alternatives_count: int = 0
    export_bundle_path: Optional[str] = None
    decision_trace_available: bool = False


class QuestionCardSchema(BaseModel):
    """Dynamic question card schema for conversational requirement prompts."""
    question: str
    input_type: str  # "single_choice" | "multi_choice" | "direction" | "number" | "text" | "confirmation"
    options: List[str] = Field(default_factory=list)
    field_key: Optional[str] = None
    default_value: Optional[Any] = None


class RequirementProgressItem(BaseModel):
    """Single item in the requirement progress checklist."""
    name: str
    status: str  # "completed" | "current" | "pending"
    value: Optional[str] = None


class ChatHistoryItem(BaseModel):
    """One prior chat message, supplied by the client to give the conversational LLM context."""
    role: str = Field(default="user", description="'user' or 'assistant'. Other roles are ignored.")
    text: str = Field(default="", max_length=4000)


class ChatTurnRequest(BaseModel):
    """Client message payload for multi-turn requirement chatting and conversation."""
    message: str = Field(default="", max_length=8000, description="User natural language message or card selection.")
    existing_brief: Optional[str] = Field(default=None, description="Accumulated canonical brief from previous turns.")
    project_name: str = Field(default="PlanForge Residential Project", description="Project title.")
    project_id: Optional[str] = Field(default=None, description="Optional project identifier.")
    history: List[ChatHistoryItem] = Field(
        default_factory=list,
        max_length=60,
        description="Recent conversation turns (oldest first, excluding this message). The server keeps only a bounded window.",
    )
    active_floor: Optional[int] = Field(default=None, ge=1, le=20, description="Floor the user is currently viewing.")
    alternative_index: Optional[int] = Field(default=None, ge=1, le=50, description="1-based design alternative the user is viewing.")
    input_source: str = Field(default="text", description="'card' when the text came from a question-card option, else 'text'.")


class ChatRoutePreview(BaseModel):
    """Where a chat message WOULD be handled (no execution, no LLM call)."""
    route: str
    uses_llm: bool
    reason: str = ""


class ChatTurnResponse(BaseModel):
    """Assistant turn reply containing narrative, dynamic card, and requirement checklist."""
    message: str
    question_card: Optional[QuestionCardSchema] = None
    is_ready_for_generation: bool = False
    requirements_text: str = ""
    requirements_summary: Optional[Dict[str, Any]] = None
    progress: List[RequirementProgressItem] = Field(default_factory=list)
    remaining_count: int = 0
    project_name: str = "PlanForge Residential Project"
    status: str = "NEEDS_CLARIFICATION"
    # --- Traceability: proves whether a real LLM produced `message` -------------
    route: str = Field(default="requirement", description="requirement | requirement_removal | conversation | plan_modification")
    llm_used: bool = Field(default=False, description="True only if `message` is a real LLM response.")
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_latency_ms: Optional[int] = None
    turn_id: Optional[str] = None
    plan_modified: bool = Field(default=False, description="Always False for chat replies: only the pipeline changes the plan.")

