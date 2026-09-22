"""Completeness Gate for structured Requirements.

The Completeness Gate answers one question: *do we have enough information
to hand off to the Planning Agent?*

Classifies requirements into four states:
- COMPLETE:  All required fields are present and every floor has rooms specified.
- INCOMPLETE: Essential fields (plot, floors, rooms per floor) are missing.
- AMBIGUOUS:  Contradictory or conflicting requirements detected.
- INVALID:    Requirements violate fundamental physical sanity (e.g. non-positive values).

Multi-Floor Requirement Gating:
If the user requests N floors, EVERY floor 1..N must have explicit room requirements,
or an explicit user authorization allowing suggestions. If a floor is unspecified,
the gate reports it as missing and produces structured clarification questions.
Under no circumstances are rooms silently invented for missing floors!
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models.requirements import Requirements


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_COMPLETE = "COMPLETE"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_INVALID = "INVALID"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompletenessResult:
    """Result of a completeness check on a ``Requirements`` object.

    Attributes:
        is_complete:             ``True`` only when all required information is present.
        status:                  One of 'COMPLETE', 'INCOMPLETE', 'AMBIGUOUS', 'INVALID'.
        missing_fields:          List of missing required field names.
        missing_floors:          List of floor numbers that lack room requirements.
        clarification_questions: Structured questions to ask the user.
        suggestions:             Suggested room lists ONLY if user explicitly opted in.
        warnings:                Advisory messages about recommended but optional fields.
        requirements:            The original ``Requirements`` instance (never mutated).
        can_proceed:             Alias for ``is_complete``; True only when ready for Planning.
    """

    is_complete: bool
    status: str = STATUS_COMPLETE
    missing_fields: list[str] = field(default_factory=list)
    missing_floors: list[int] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requirements: Requirements = field(default_factory=Requirements)

    @property
    def can_proceed(self) -> bool:
        """``True`` only when ``is_complete`` is ``True`` and status is COMPLETE."""
        return self.is_complete and self.status == STATUS_COMPLETE


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

class CompletenessGate:
    """Validates whether a ``Requirements`` object is ready for the Planning Agent.

    Enforces the strict no-invention rule across single and multi-floor buildings.
    """

    #: Field labels reported in ``missing_fields``
    FIELD_PLOT_DIMENSIONS = "plot_dimensions"
    FIELD_TARGET_FLOORS = "target_floors"
    FIELD_FLOORS_WITH_ROOMS = "floors_with_rooms"

    def check(
        self,
        requirements: Requirements,
        allow_suggestions: bool = False,
    ) -> CompletenessResult:
        """Evaluate *requirements* for completeness and multi-floor gating.

        Args:
            requirements:      A ``Requirements`` object.
            allow_suggestions: If True, user explicitly authorized system suggestions
                               for missing details. If False (default), missing items
                               must be asked via clarification without inventing defaults.

        Returns:
            ``CompletenessResult`` describing status, missing items, and questions.
        """
        missing: list[str] = []
        missing_floors: list[int] = []
        questions: list[str] = []
        suggestions: list[str] = []
        warnings: list[str] = []

        # 1. Check for physical invalidity (INVALID status)
        if requirements.plot_dimensions:
            w, d = requirements.plot_dimensions
            if w <= 0 or d <= 0:
                return CompletenessResult(
                    is_complete=False,
                    status=STATUS_INVALID,
                    missing_fields=["valid_plot_dimensions"],
                    warnings=["Plot width and depth must be positive numbers."],
                    requirements=requirements,
                )

        if requirements.target_floors is not None and requirements.target_floors <= 0:
            return CompletenessResult(
                is_complete=False,
                status=STATUS_INVALID,
                missing_fields=["valid_target_floors"],
                warnings=["Target floors must be a positive integer."],
                requirements=requirements,
            )

        # 2. Required: Plot dimensions, area, or explicit boundary polygon
        has_plot_polygon = bool(requirements.plot_shape and len(requirements.plot_shape) >= 3)
        if requirements.plot_dimensions is None and requirements.plot_area_sqm is None and not has_plot_polygon:
            missing.append(self.FIELD_PLOT_DIMENSIONS)
            questions.append("What are the dimensions or total area of your plot (e.g., '30ft x 40ft' or '150 sqm')?")

        # 3. Required: Target floors
        if requirements.target_floors is None:
            missing.append(self.FIELD_TARGET_FLOORS)
            questions.append("How many floors do you want to build (e.g., 'single storey', '2 floors')?")

        # 4. Required: Each target floor must have explicit rooms
        effective_floors = requirements.target_floors or len(requirements.floors)
        if effective_floors > 0:
            for fn in range(1, effective_floors + 1):
                f_req = requirements.get_floor(fn)
                if f_req is None or len(f_req.room_requirements) == 0:
                    missing_floors.append(fn)

            if missing_floors:
                if self.FIELD_FLOORS_WITH_ROOMS not in missing:
                    missing.append(self.FIELD_FLOORS_WITH_ROOMS)
                for mfn in missing_floors:
                    fname = f"Floor {mfn}" if mfn > 1 else "Ground Floor"
                    questions.append(
                        f"What rooms would you like on {fname}? Please specify room types (e.g., bedrooms, bathrooms, living room)."
                    )
                    if allow_suggestions:
                        # Only provide suggestions when explicitly authorized
                        if mfn == 2:
                            suggestions.append("Floor 2 option: 2 bedrooms, 1 bathroom, study room, and balcony.")
                        elif mfn == 1:
                            suggestions.append("Ground floor option: Living room, dining room, kitchen, and 1 bedroom.")
        else:
            missing.append(self.FIELD_FLOORS_WITH_ROOMS)
            questions.append("What rooms would you like in your house?")

        # 5. Advisory warnings (non-blocking)
        if requirements.orientation is None:
            warnings.append(
                "No plot orientation specified (e.g. 'north-facing'). Orientation helps optimize room placement."
            )

        if requirements.entrance_facing is None:
            warnings.append(
                "No entrance facing direction specified (e.g. 'entrance from east')."
            )

        if not requirements.setbacks:
            warnings.append(
                "No setbacks specified. Standard municipal setbacks will be used by the Planning Agent."
            )

        all_rooms = requirements.all_room_requirements()
        if all_rooms and not any(
            r.preferred_area_sqm or r.min_area_sqm or r.max_area_sqm for r in all_rooms
        ):
            warnings.append(
                "No area hints were detected for any room. Providing preferred room sizes produces more accurate layouts."
            )

        # 6. Status determination
        if missing:
            status = STATUS_INCOMPLETE
            is_complete = False
        else:
            status = STATUS_COMPLETE
            is_complete = True

        return CompletenessResult(
            is_complete=is_complete,
            status=status,
            missing_fields=missing,
            missing_floors=missing_floors,
            clarification_questions=questions,
            suggestions=suggestions,
            warnings=warnings,
            requirements=requirements,
        )
