"""Configuration data structures for the PlanForge orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.rendering.options import RenderOptions


@dataclass
class OrchestrationConfig:
    """Configuration options governing an end-to-end floor plan generation pipeline run."""

    # Refinement options
    enable_refinement: bool = True
    max_refinement_iterations: int = 5

    # Multi-design diversity options
    num_alternatives: int = 1
    candidate_budget: int = 4
    minimum_diversity_distance: float = 0.20
    strategies: Optional[List[str]] = None

    # Export & Rendering options
    enable_rendering: bool = True
    enable_exports: bool = True
    create_zip: bool = False
    output_dir: str = "outputs"
    render_options: Optional[RenderOptions] = None

    # Execution controls
    mode: str = "pipeline"  # "pipeline" (default, original baseline) | "agentic" (opt-in foundation)
    use_llm: bool = True  # In agentic mode, whether to use the LLM action selector
    llm_client: Optional[Any] = None
    llm_config: Optional[Any] = None
    timeout_seconds: float = 120.0
    allow_partial_results: bool = True
    budget: Optional[Any] = None
    interactive: bool = False  # Phase 7 interactive clarification mode
    seed: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enable_refinement": self.enable_refinement,
            "max_refinement_iterations": self.max_refinement_iterations,
            "num_alternatives": self.num_alternatives,
            "candidate_budget": self.candidate_budget,
            "minimum_diversity_distance": self.minimum_diversity_distance,
            "strategies": self.strategies,
            "enable_rendering": self.enable_rendering,
            "enable_exports": self.enable_exports,
            "create_zip": self.create_zip,
            "output_dir": self.output_dir,
            "mode": self.mode,
            "use_llm": self.use_llm,
            "timeout_seconds": self.timeout_seconds,
            "allow_partial_results": self.allow_partial_results,
            "interactive": self.interactive,
            "seed": self.seed,
        }
