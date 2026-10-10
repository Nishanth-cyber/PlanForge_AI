"""Requirement Pipeline — executes the sequential requirement processing flow.

Pipeline:
RAW USER INPUT
      ↓
INPUT PARSING (RequirementParser)
      ↓
STRUCTURED REQUIREMENTS (Requirements, FloorRequirement, RoomRequirement)
      ↓
NORMALIZATION (RequirementNormalizer)
      ↓
COMPLETENESS CHECK & MULTI-FLOOR GATING (CompletenessGate)
      ↓
REQUIREMENT VALIDATION (RequirementValidator)
      ↓
READY FOR PLANNING (Planning-compatible Output)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.agents.requirement_agent.parser import RequirementParser
from app.agents.requirement_agent.normalizer import RequirementNormalizer
from app.agents.requirement_agent.completeness_gate import (
    CompletenessGate,
    CompletenessResult,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_AMBIGUOUS,
    STATUS_INVALID,
)
from app.agents.requirement_agent.validator import RequirementValidator, RequirementValidationResult


@dataclass
class PipelineResult:
    """Consolidated result of the requirement pipeline."""
    requirements: Requirements
    completeness: CompletenessResult
    validation: RequirementValidationResult
    can_proceed_to_planning: bool
    status: str  # "READY_FOR_PLANNING", "NEEDS_CLARIFICATION", "INVALID", "VALIDATION_FAILED"

    def summary(self) -> str:
        """Human-readable diagnostic summary for explainability."""
        lines = [f"Status: {self.status}"]
        if self.can_proceed_to_planning:
            lines.append("Requirements are complete and valid. Ready for Planning Agent.")
        else:
            if not self.completeness.is_complete:
                lines.append(f"Missing required items: {', '.join(self.completeness.missing_fields)}")
                if self.completeness.missing_floors:
                    lines.append(f"Missing room specs for floors: {self.completeness.missing_floors}")
            if not self.validation.is_valid:
                lines.append(f"Validation errors ({len(self.validation.errors)}):")
                for err in self.validation.errors:
                    lines.append(f"  - [{err.field}] {err.message}")
        return "\n".join(lines)


class RequirementPipeline:
    """Orchestrates parsing, normalization, completeness gating, and validation."""

    def __init__(self) -> None:
        self.parser = RequirementParser()
        self.normalizer = RequirementNormalizer()
        self.completeness_gate = CompletenessGate()
        self.validator = RequirementValidator()

    def process(
        self,
        user_input: str,
        project_name: str = "PlanForge Project",
        allow_suggestions: bool = False,
    ) -> PipelineResult:
        """Run the end-to-end requirement pipeline on user input."""
        # 1. Parsing
        reqs = self.parser.parse(user_input, project_name=project_name)

        # 2. Normalization pass
        self._normalize_requirements(reqs)

        # 3. Completeness check with multi-floor gating
        comp_res = self.completeness_gate.check(reqs, allow_suggestions=allow_suggestions)

        # 4. Semantic validation
        val_res = self.validator.validate(reqs)

        # 5. Overall status
        can_proceed = comp_res.can_proceed and val_res.is_valid

        if not val_res.is_valid:
            status = "VALIDATION_FAILED"
        elif not comp_res.is_complete:
            status = "NEEDS_CLARIFICATION" if comp_res.status == STATUS_INCOMPLETE else comp_res.status
        else:
            status = "READY_FOR_PLANNING"

        return PipelineResult(
            requirements=reqs,
            completeness=comp_res,
            validation=val_res,
            can_proceed_to_planning=can_proceed,
            status=status,
        )

    def update(
        self,
        existing: Requirements,
        additional_input: str,
        allow_suggestions: bool = False,
        active_floor: Optional[int] = None,
    ) -> PipelineResult:
        """Incrementally update existing requirements with additional user input (multi-turn).

        Preserves existing valid rooms and floors while incorporating new clarifications.
        """
        new_reqs = self.parser.parse(
            additional_input,
            project_name=existing.project_name,
            active_floor=active_floor,
        )

        # Merge plot
        if new_reqs.plot_shape:
            existing.plot_shape = new_reqs.plot_shape
            existing.plot_dimensions = None
            if new_reqs.plot_area_sqm:
                existing.plot_area_sqm = new_reqs.plot_area_sqm
        elif new_reqs.plot_dimensions:
            existing.plot_dimensions = new_reqs.plot_dimensions
            existing.plot_area_sqm = new_reqs.plot_area_sqm
        elif new_reqs.plot_area_sqm and not existing.plot_area_sqm:
            existing.plot_area_sqm = new_reqs.plot_area_sqm

        if new_reqs.orientation:
            existing.orientation = new_reqs.orientation
        if new_reqs.entrance_facing:
            existing.entrance_facing = new_reqs.entrance_facing
        if new_reqs.setbacks:
            existing.setbacks.update(new_reqs.setbacks)
        if new_reqs.target_floors:
            existing.target_floors = new_reqs.target_floors

        # Merge floors
        for nf in new_reqs.floors:
            if not nf.room_requirements:
                continue
            effective_fn = (
                active_floor
                if (active_floor and active_floor > 1 and len(new_reqs.floors) == 1 and nf.floor_number == 1)
                else nf.floor_number
            )
            existing_f = existing.get_floor(effective_fn)
            if existing_f:
                # Add or update rooms
                existing_types = {r.room_type: r for r in existing_f.room_requirements}
                for nr in nf.room_requirements:
                    if nr.room_type in existing_types:
                        # Update counts/areas
                        er = existing_types[nr.room_type]
                        er.min_count = max(er.min_count, nr.min_count)
                        if nr.preferred_area_sqm:
                            er.preferred_area_sqm = nr.preferred_area_sqm
                        if nr.min_area_sqm:
                            er.min_area_sqm = nr.min_area_sqm
                        if nr.max_area_sqm:
                            er.max_area_sqm = nr.max_area_sqm
                        if nr.user_dimensions:
                            er.user_dimensions = nr.user_dimensions
                        if nr.adjacency:
                            for a in nr.adjacency:
                                if a not in er.adjacency:
                                    er.adjacency.append(a)
                        if nr.separation:
                            for s in nr.separation:
                                if s not in er.separation:
                                    er.separation.append(s)
                        if nr.attached_to:
                            er.attached_to = nr.attached_to
                    else:
                        existing_f.room_requirements.append(nr)
            else:
                nf.floor_number = effective_fn
                nf.floor_name = self.parser._floor_name(effective_fn)
                existing.floors.append(nf)

        # Sort floors
        existing.floors.sort(key=lambda f: f.floor_number)
        existing.raw_input = f"{existing.raw_input}\n{additional_input}".strip()

        # Re-run pipeline checks
        self._normalize_requirements(existing)
        comp_res = self.completeness_gate.check(existing, allow_suggestions=allow_suggestions)
        val_res = self.validator.validate(existing)
        can_proceed = comp_res.can_proceed and val_res.is_valid

        status = "READY_FOR_PLANNING" if can_proceed else ("NEEDS_CLARIFICATION" if not comp_res.is_complete else "VALIDATION_FAILED")

        return PipelineResult(
            requirements=existing,
            completeness=comp_res,
            validation=val_res,
            can_proceed_to_planning=can_proceed,
            status=status,
        )

    def _normalize_requirements(self, reqs: Requirements) -> None:
        """Apply secondary normalization across all fields."""
        if reqs.orientation:
            reqs.orientation = self.normalizer.normalize_direction(reqs.orientation)
        if reqs.entrance_facing:
            reqs.entrance_facing = self.normalizer.normalize_direction(reqs.entrance_facing)

        for f in reqs.floors:
            for r in f.room_requirements:
                canonical = self.normalizer.canonical_room_type(r.room_type)
                if canonical:
                    r.room_type = canonical
                # Clean relationships
                r.adjacency = [
                    self.normalizer.canonical_room_type(adj) or adj
                    for adj in r.adjacency
                    if adj != r.room_type
                ]
                r.separation = [
                    self.normalizer.canonical_room_type(sep) or sep
                    for sep in r.separation
                    if sep != r.room_type
                ]
                if r.attached_to:
                    r.attached_to = self.normalizer.canonical_room_type(r.attached_to) or r.attached_to
