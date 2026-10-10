"""Requirement Agent — converts freeform user text into structured Requirements.

Design principles
-----------------
1.  **Never invent.**  Only requirements the user explicitly stated are
    recorded.  ``source`` is always ``"user"`` for an extracted requirement.
2.  **Single entry point.**  ``RequirementAgent.parse()`` and ``RequirementAgent.process()``
    are the authoritative ways to convert text into structured ``Requirements``.
3.  **Strict multi-floor gating.** If user requests N floors, every floor must
    have explicit room requirements or an explicit user confirmation.
4.  **Rule-based primary, LLM-ready secondary.** Deterministic extraction,
    canonical synonym resolution, completeness gating, and semantic validation.
"""

from __future__ import annotations

from typing import Optional

from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.agents.requirement_agent.normalizer import (
    RequirementNormalizer,
    ROOM_SYNONYMS,
    WORD_NUMBERS,
    FLOOR_LABEL_TO_NUMBER,
    CARDINAL_DIRECTIONS,
)
from app.agents.requirement_agent.parser import RequirementParser
from app.agents.requirement_agent.pipeline import RequirementPipeline, PipelineResult
from app.agents.requirement_agent.completeness_gate import CompletenessGate, CompletenessResult
from app.agents.requirement_agent.validator import RequirementValidator, RequirementValidationResult


class RequirementAgent:
    """Authoritative agent for extracting and verifying user requirements."""

    def __init__(self) -> None:
        self.pipeline = RequirementPipeline()
        self.parser = self.pipeline.parser
        self.normalizer = self.pipeline.normalizer
        self.completeness_gate = self.pipeline.completeness_gate
        self.validator = self.pipeline.validator

    def parse(
        self,
        user_input: str,
        project_name: str = "PlanForge Project",
        active_floor: Optional[int] = None,
    ) -> Requirements:
        """Parse *user_input* into a structured ``Requirements`` object.

        Args:
            user_input:   Raw, unprocessed text from the user.
            project_name: Optional project label stored on the result.
            active_floor: Optional target floor number for room requirements.

        Returns:
            ``Requirements`` containing only what the user explicitly stated.
        """
        reqs = self.parser.parse(user_input, project_name=project_name, active_floor=active_floor)
        self.pipeline._normalize_requirements(reqs)
        return reqs

    def process(
        self,
        user_input: str,
        project_name: str = "PlanForge Project",
        allow_suggestions: bool = False,
        active_floor: Optional[int] = None,
    ) -> PipelineResult:
        """Run full requirement pipeline including parsing, normalization, completeness, and validation.

        Args:
            user_input:        Raw input text.
            project_name:      Optional project name.
            allow_suggestions: If True, provides room suggestions for missing floors.
            active_floor:      Optional target floor number.

        Returns:
            ``PipelineResult`` with requirements, completeness, validation, and gating status.
        """
        reqs = self.parser.parse(user_input, project_name=project_name, active_floor=active_floor)
        self.pipeline._normalize_requirements(reqs)
        comp_res = self.completeness_gate.check(reqs, allow_suggestions=allow_suggestions)
        val_res = self.validator.validate(reqs)
        can_proceed = comp_res.can_proceed and val_res.is_valid
        status = "READY_FOR_PLANNING" if can_proceed else ("NEEDS_CLARIFICATION" if not comp_res.is_complete else "VALIDATION_FAILED")
        return PipelineResult(
            requirements=reqs,
            completeness=comp_res,
            validation=val_res,
            can_proceed_to_planning=can_proceed,
            status=status,
        )

    def update(
        self,
        existing_reqs: Requirements,
        additional_input: str,
        allow_suggestions: bool = False,
        active_floor: Optional[int] = None,
    ) -> PipelineResult:
        """Multi-turn update to incrementally supply missing requirements."""
        return self.pipeline.update(
            existing_reqs,
            additional_input,
            allow_suggestions=allow_suggestions,
            active_floor=active_floor,
        )