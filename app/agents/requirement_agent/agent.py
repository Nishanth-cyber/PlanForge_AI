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

    def parse(self, user_input: str, project_name: str = "PlanForge Project") -> Requirements:
        """Parse *user_input* into a structured ``Requirements`` object.

        Args:
            user_input:   Raw, unprocessed text from the user.
            project_name: Optional project label stored on the result.

        Returns:
            ``Requirements`` containing only what the user explicitly stated.
        """
        result = self.pipeline.process(user_input, project_name=project_name)
        return result.requirements

    def process(
        self,
        user_input: str,
        project_name: str = "PlanForge Project",
        allow_suggestions: bool = False,
    ) -> PipelineResult:
        """Run full requirement pipeline including parsing, normalization, completeness, and validation.

        Args:
            user_input:        Raw input text.
            project_name:      Optional project name.
            allow_suggestions: If True, provides room suggestions for missing floors.

        Returns:
            ``PipelineResult`` with requirements, completeness, validation, and gating status.
        """
        return self.pipeline.process(
            user_input,
            project_name=project_name,
            allow_suggestions=allow_suggestions,
        )

    def update(
        self,
        existing_reqs: Requirements,
        additional_input: str,
        allow_suggestions: bool = False,
    ) -> PipelineResult:
        """Multi-turn update to incrementally supply missing requirements."""
        return self.pipeline.update(
            existing_reqs,
            additional_input,
            allow_suggestions=allow_suggestions,
        )