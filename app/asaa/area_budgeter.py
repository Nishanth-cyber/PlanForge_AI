"""Area budgeter for ASAA.

Implements two-pass area allocation (minimum-first + priority-weighted remainder)
and explicit infeasibility detection without silent room dropping or area reductions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.asaa.exceptions import InfeasibleAllocationError
from app.models.planning import RoomSpec


@dataclass
class FloorBudget:
    """Area budget breakdown for a single floor."""
    buildable_area_sqm: float
    circulation_area_sqm: float
    staircase_area_sqm: float
    room_budgets: dict[str, float] = field(default_factory=dict)  # room_spec.id -> area_sqm
    total_allocated_rooms_sqm: float = 0.0
    floor_number: int = 1


class AreaBudgeter:
    """Computes realistic area distribution per floor."""

    PRIORITY_WEIGHTS = {
        "high": 1.5,
        "normal": 1.0,
        "low": 0.7,
    }

    @staticmethod
    def compute_budget(
        buildable_area_sqm: float,
        room_specs: list[RoomSpec],
        floor_number: int = 1,
        circulation_ratio: float = 0.12,
        has_staircase: bool = False,
        staircase_area_sqm: float = 8.0,
    ) -> FloorBudget:
        """Compute area budget for all rooms on a floor.

        Args:
            buildable_area_sqm: Total usable buildable area for the floor.
            room_specs: List of RoomSpec objects assigned to this floor.
            floor_number: Floor index (1-based).
            circulation_ratio: Fraction of buildable area reserved for corridors/foyer (default 12%).
            has_staircase: Whether a staircase core must be reserved on this floor.
            staircase_area_sqm: Reserved area for staircase zone (default 8 m²).

        Returns:
            FloorBudget object.

        Raises:
            InfeasibleAllocationError: When minimum room requirements exceed available space.
        """
        if not room_specs:
            return FloorBudget(
                buildable_area_sqm=buildable_area_sqm,
                circulation_area_sqm=0.0,
                staircase_area_sqm=staircase_area_sqm if has_staircase else 0.0,
                room_budgets={},
                total_allocated_rooms_sqm=0.0,
                floor_number=floor_number,
            )

        # 1. Determine circulation and vertical core allowances
        actual_staircase_sqm = staircase_area_sqm if has_staircase else 0.0
        # Circulation allowance: at least 10% of buildable area, or at least 4 sqm per 3 rooms
        min_circ_sqm = max(4.0, buildable_area_sqm * circulation_ratio)
        avail_for_rooms = buildable_area_sqm - actual_staircase_sqm - min_circ_sqm

        # 2. Check minimum area feasibility
        total_min_required = 0.0
        min_areas: dict[str, float] = {}
        for rs in room_specs:
            count = max(1, rs.count)
            # If explicit min_area_sqm is provided, use it strictly.
            # Otherwise use target_area_sqm * 0.8 as the baseline minimum.
            if rs.min_area_sqm is not None and rs.min_area_sqm > 0:
                base_min = rs.min_area_sqm
            else:
                base_min = rs.target_area_sqm * 0.8 if rs.target_area_sqm > 0 else 6.0

            total_room_min = base_min * count
            min_areas[rs.id] = base_min
            total_min_required += total_room_min

        # Infeasibility check: if rooms cannot fit even at minimum area
        if total_min_required > (buildable_area_sqm - actual_staircase_sqm):
            deficit = total_min_required - (buildable_area_sqm - actual_staircase_sqm)
            offending = [
                f"{rs.room_type} (min {min_areas[rs.id]}m²)"
                for rs in room_specs
            ]
            raise InfeasibleAllocationError(
                f"Floor {floor_number}: Total minimum room area ({total_min_required:.1f} m²) "
                f"exceeds available buildable area ({buildable_area_sqm - actual_staircase_sqm:.1f} m²) "
                f"by deficit of {deficit:.1f} m²",
                available_area_sqm=buildable_area_sqm - actual_staircase_sqm,
                requested_min_area_sqm=total_min_required,
                deficit_sqm=deficit,
                offending_rooms=offending,
                floor_number=floor_number,
            )

        # If available for rooms after circulation is tight, adjust circulation to minimum required
        if avail_for_rooms < total_min_required:
            avail_for_rooms = max(total_min_required, buildable_area_sqm - actual_staircase_sqm - 2.0)
            actual_circ_sqm = max(0.0, buildable_area_sqm - actual_staircase_sqm - avail_for_rooms)
        else:
            actual_circ_sqm = min_circ_sqm

        # 3. Two-pass allocation
        # Pass 1: Assign minimum required areas
        allocated: dict[str, float] = {}
        for rs in room_specs:
            allocated[rs.id] = min_areas[rs.id]

        remainder = avail_for_rooms - total_min_required

        # Pass 2: Distribute remainder proportionally to target area gap and priority
        if remainder > 0.1:
            # Calculate demand weights
            weights: dict[str, float] = {}
            total_weight = 0.0
            for rs in room_specs:
                target = rs.target_area_sqm if rs.target_area_sqm > 0 else min_areas[rs.id] * 1.25
                gap = max(0.0, target - min_areas[rs.id])
                p_weight = AreaBudgeter.PRIORITY_WEIGHTS.get(rs.priority, 1.0)
                w = (gap + 1.0) * p_weight
                weights[rs.id] = w
                total_weight += w

            if total_weight > 0:
                for rs in room_specs:
                    share = remainder * (weights[rs.id] / total_weight)
                    new_val = allocated[rs.id] + share
                    # Cap by max_area_sqm if specified
                    if rs.max_area_sqm is not None and rs.max_area_sqm > 0:
                        new_val = min(new_val, rs.max_area_sqm)
                    # Don't exceed target area unless significant surplus
                    allocated[rs.id] = round(new_val, 2)

        # Re-verify that no room was reduced below its explicit min_area_sqm
        for rs in room_specs:
            if rs.min_area_sqm is not None:
                allocated[rs.id] = max(allocated[rs.id], rs.min_area_sqm)

        total_allocated = sum(allocated[rs.id] * rs.count for rs in room_specs)
        # Remaining area becomes part of circulation
        final_circ = max(0.0, buildable_area_sqm - actual_staircase_sqm - total_allocated)

        return FloorBudget(
            buildable_area_sqm=round(buildable_area_sqm, 2),
            circulation_area_sqm=round(final_circ, 2),
            staircase_area_sqm=round(actual_staircase_sqm, 2),
            room_budgets=allocated,
            total_allocated_rooms_sqm=round(total_allocated, 2),
            floor_number=floor_number,
        )
