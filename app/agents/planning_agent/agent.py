"""Planning Agent — transforms structured Requirements into a strategic PlanningSpec.

Responsibilities:
1. Room identification with stable traceable IDs
2. Room categorization into functional zones
3. Floor assignment preservation
4. Explainable room priority calculation
5. 4-tier relationship graph construction (Required, Preferred, Avoid, Attached)
6. Circulation intent formulation without corridor geometry
7. Entrance intent representation without door geometry
8. Multi-floor vertical staircase connectivity intent without stair geometry
9. Global planning constraints formulation
10. Strict gating against incomplete requirements (never invents rooms)
"""

from __future__ import annotations

from typing import Optional

from app.models.planning import (
    IncompleteRequirementsError,
    RoomSpec,
    FloorPlanSpec,
    PlanningSpec,
)
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.agents.requirement_agent.completeness_gate import CompletenessGate
from app.agents.planning_agent.categorizer import RoomCategorizer
from app.agents.planning_agent.priority_calculator import PriorityCalculator
from app.agents.planning_agent.relationship_graph import RelationshipGraphBuilder
from app.agents.planning_agent.circulation_planner import CirculationPlanner
from app.utils.ids import generate_id


class PlanningAgent:
    """Authoritative agent for organizing requirements into a spatial planning program."""

    def __init__(self) -> None:
        self.completeness_gate = CompletenessGate()
        self.categorizer = RoomCategorizer()
        self.priority_calculator = PriorityCalculator()
        self.relationship_builder = RelationshipGraphBuilder()
        self.circulation_planner = CirculationPlanner()

    def plan(self, requirements: Requirements) -> PlanningSpec:
        """Create a PlanningSpec from validated Requirements.

        Args:
            requirements: Validated, complete Requirements from Requirement Agent.

        Returns:
            A structured PlanningSpec ready for ASAA spatial allocation.

        Raises:
            IncompleteRequirementsError: If requirements are incomplete or unfeasible.
        """
        # 1. Gate check: Incomplete requirements must NOT be planned
        comp_res = self.completeness_gate.check(requirements)
        if not comp_res.can_proceed:
            missing_desc = ", ".join(comp_res.missing_fields)
            if comp_res.missing_floors:
                missing_desc += f" (Missing floors: {comp_res.missing_floors})"
            raise IncompleteRequirementsError(
                f"Cannot plan incomplete requirements. Missing: {missing_desc}. "
                "The system will not invent unspecified rooms or floors."
            )

        spec = PlanningSpec(
            id=generate_id(prefix="plan_spec"),
            project_name=requirements.project_name or "PlanForge Project",
            source_requirements_id=requirements.id,
        )

        total_floors = requirements.target_floors or len(requirements.floors)
        is_multi_floor = total_floors > 1

        # 2. Plan each floor independently, preserving exact floor assignments
        for floor_req in requirements.floors:
            floor_spec = self._plan_floor(
                floor_req=floor_req,
                requirements=requirements,
                total_floors=total_floors,
                is_multi_floor=is_multi_floor,
            )
            spec.floors.append(floor_spec)

        # 3. Formulate global architectural constraints for downstream ASAA
        spec.global_constraints = self._build_global_constraints(requirements, is_multi_floor)

        return spec

    def _plan_floor(
        self,
        floor_req: FloorRequirement,
        requirements: Requirements,
        total_floors: int,
        is_multi_floor: bool,
    ) -> FloorPlanSpec:
        """Plan a single floor according to user specifications."""
        fn = floor_req.floor_number
        floor_spec = FloorPlanSpec(
            id=generate_id(prefix=f"floor_{fn}"),
            floor_number=fn,
            floor_name=floor_req.floor_name or f"Floor {fn}",
            total_area_sqm=floor_req.total_area_sqm,
        )

        # Step A: Create RoomSpec instances with categories and priorities
        room_specs: list[RoomSpec] = []
        for r_req in floor_req.room_requirements:
            category = self.categorizer.get_functional_zone(r_req.room_type)
            priority, rationale = self.priority_calculator.calculate_priority(
                room_type=r_req.room_type,
                attached_to=r_req.attached_to,
                has_adjacencies=len(r_req.adjacency) > 0,
            )
            target_area = r_req.preferred_area_sqm or r_req.min_area_sqm or 0.0

            r_spec = RoomSpec(
                id=generate_id(prefix="room"),
                room_type=r_req.room_type,
                room_category=category,
                floor_number=fn,
                count=r_req.min_count,
                target_area_sqm=round(target_area, 3),
                min_area_sqm=r_req.min_area_sqm,
                max_area_sqm=r_req.max_area_sqm,
                adjacency=list(r_req.adjacency),
                avoid=list(r_req.separation),
                user_dimensions=r_req.user_dimensions,
                priority=priority,

                priority_rationale=rationale,
                original_name=r_req.description or r_req.room_type,
                source_requirement_id=r_req.id,
            )
            room_specs.append(r_spec)

        # Step B: Link attached rooms (e.g. ensuite attached to master bedroom)
        attached_pairs: list[tuple[str, str]] = []
        for r_req, r_spec in zip(floor_req.room_requirements, room_specs):
            if r_req.attached_to:
                # Find matching parent room on this floor
                parent_candidates = [
                    s for s in room_specs
                    if s.room_type == r_req.attached_to or (s.room_type in ("master_bedroom", "bedroom") and r_req.attached_to == "bedroom")
                ]
                if parent_candidates:
                    parent = parent_candidates[0]
                    r_spec.attached_to_room_id = parent.id
                    attached_pairs.append((parent.room_type, r_spec.room_type))

        floor_spec.room_specs = room_specs

        # Step C: Build normalized relationship matrices
        adj_matrix, avoid_matrix = self.relationship_builder.build_matrices(
            room_specs=room_specs,
            attached_pairs=attached_pairs,
        )
        floor_spec.adjacency_matrix = adj_matrix
        floor_spec.avoid_matrix = avoid_matrix

        # Step D: Plan circulation zones and notes
        zones, notes = self.circulation_planner.plan_circulation_zones(
            floor_number=fn,
            room_specs=room_specs,
            is_multi_floor=is_multi_floor,
        )
        floor_spec.circulation_zones = zones
        floor_spec.circulation_notes = notes

        # Step E: Entrance intent (Ground floor only)
        floor_spec.entrance_intent = self.circulation_planner.plan_entrance_intent(
            floor_number=fn,
            orientation=requirements.orientation,
            entrance_facing=requirements.entrance_facing,
            entrance_room_type=requirements.entrance_room_type,
        )

        # Step F: Staircase intent (Multi-floor)
        floor_spec.staircase_intent = self.circulation_planner.plan_staircase_intent(
            floor_number=fn,
            total_floors=total_floors,
            staircase_required=floor_req.staircase_required or is_multi_floor,
        )

        return floor_spec

    def _build_global_constraints(self, requirements: Requirements, is_multi_floor: bool) -> dict:
        """Formulate project-level architectural constraints for ASAA."""
        return {
            "plot_dimensions": requirements.plot_dimensions,
            "plot_shape": requirements.plot_shape,
            "plot_area_sqm": requirements.plot_area_sqm,
            "orientation": requirements.orientation,
            "entrance_facing": requirements.entrance_facing,
            "setbacks": requirements.setbacks,
            "target_floors": requirements.target_floors,
            "staircase_aligned": is_multi_floor,
            "privacy_buffering": True,
            "circulation_continuity": True,
        }