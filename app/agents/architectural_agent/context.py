"""Architectural context models and builder.

Constructs an immutable, structured context payload for the Architectural LLM,
linking PlanningSpec strategic intent and ASAA AllocatedRegions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple
from app.models.allocation import Allocation, AllocationSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.requirements import Requirements


@dataclass(frozen=True)
class RoomDesignContext:
    """Context information for designing a single room."""
    room_id: str
    room_type: str
    floor_number: int
    priority: str
    category: str
    target_area_sqm: float
    min_area_sqm: Optional[float]
    max_area_sqm: Optional[float]
    allocated_region_id: str
    allocated_area_sqm: float
    approximate_dimensions: Tuple[float, float]
    allocated_polygon: tuple[Tuple[float, float], ...]
    adjacent_region_ids: tuple[str, ...]
    adjacent_room_types: tuple[str, ...]
    user_required_adjacencies: tuple[str, ...]
    system_preferred_adjacencies: tuple[str, ...]
    avoid_rooms: tuple[str, ...]
    attached_to_room_id: Optional[str]
    user_specified_dimensions: Optional[Tuple[float, float]] = None


@dataclass(frozen=True)
class FloorDesignContext:
    """Context information for designing a single floor."""
    floor_number: int
    floor_name: str
    rooms: tuple[RoomDesignContext, ...]
    circulation_zones: tuple[str, ...]
    circulation_notes: str
    entrance_intent: Optional[dict]
    staircase_intent: Optional[dict]
    staircase_region_id: Optional[str]
    plot_orientation: str
    strategy: Optional[str] = None
    alternative_index: int = 0

    def get_room_context(self, room_id: str) -> Optional[RoomDesignContext]:
        """Find a room context by ID."""
        for r in self.rooms:
            if r.room_id == room_id:
                return r
        return None

    def get_room_context_by_region_id(self, region_id: str) -> Optional[RoomDesignContext]:
        """Find a room context by allocated region ID."""
        for r in self.rooms:
            if r.allocated_region_id == region_id:
                return r
        return None


@dataclass(frozen=True)
class ArchitecturalContext:
    """Complete structured context payload passed to the Architectural LLM."""
    project_name: str
    floors: tuple[FloorDesignContext, ...]
    global_constraints: dict
    strategy: Optional[str] = None
    alternative_index: int = 0

    def get_floor_context(self, floor_number: int) -> Optional[FloorDesignContext]:
        """Retrieve floor context by floor number."""
        for f in self.floors:
            if f.floor_number == floor_number:
                return f
        return None


class ContextBuilder:
    """Builds ArchitecturalContext from PlanningSpec and AllocationSet."""

    @staticmethod
    def build(
        planning_spec: PlanningSpec,
        allocation_set: AllocationSet,
        requirements: Optional[Requirements] = None,
        strategy: Optional[str] = None,
        alternative_index: int = 0,
    ) -> ArchitecturalContext:
        """Build structured architectural context.

        Args:
            planning_spec: Planning specification from Planning Agent.
            allocation_set: Allocation set from ASAA.
            requirements: Optional structured user requirements for provenance tracking.
            strategy: Optional design strategy (e.g. social_centric, corridor_centric).
            alternative_index: Index of the alternative being generated.

        Returns:
            Immutable ArchitecturalContext.
        """
        floor_contexts = []
        plot_orientation = str(planning_spec.global_constraints.get("orientation", "north"))

        # Extract user vs system provenance if requirements available
        user_req_adj_map: dict[str, list[str]] = {}
        if requirements:
            for fr in requirements.floors:
                for rr in fr.room_requirements:
                    if rr.adjacency:
                        user_req_adj_map[rr.room_type] = list(rr.adjacency)

        for floor_spec in planning_spec.floors:
            allocation = allocation_set.get_allocation(floor_spec.floor_number)
            if not allocation:
                continue

            room_contexts = []
            staircase_region_id = None
            stair_reg = allocation.get_staircase_region()
            if stair_reg:
                staircase_region_id = stair_reg.id

            # Map allocated regions
            for room_spec in floor_spec.room_specs:
                # Find matching allocated region by room_spec_id or room_type
                matched_region = None
                for reg in allocation.allocated_regions:
                    if reg.room_spec_id == room_spec.id:
                        matched_region = reg
                        break
                if not matched_region:
                    for reg in allocation.allocated_regions:
                        if reg.room_type == room_spec.room_type:
                            matched_region = reg
                            break

                if not matched_region:
                    continue

                # Determine adjacent room types
                adj_types = []
                for adj_id in matched_region.adjacency_regions:
                    adj_r = allocation.get_region_by_id(adj_id)
                    if adj_r and adj_r.room_type and adj_r.room_type not in adj_types:
                        adj_types.append(adj_r.room_type)

                # Provenance: user required vs system preferred
                user_adj = user_req_adj_map.get(room_spec.room_type, [])
                sys_adj = [
                    a for a in floor_spec.adjacency_matrix.get(room_spec.room_type, [])
                    if a not in user_adj
                ]

                user_dims = getattr(room_spec, "user_dimensions", None)

                r_ctx = RoomDesignContext(
                    room_id=room_spec.id,
                    room_type=room_spec.room_type,
                    floor_number=floor_spec.floor_number,
                    priority=room_spec.priority,
                    category=getattr(room_spec, "room_category", getattr(room_spec, "category", "social")),
                    target_area_sqm=room_spec.target_area_sqm,
                    min_area_sqm=room_spec.min_area_sqm,
                    max_area_sqm=room_spec.max_area_sqm,
                    allocated_region_id=matched_region.id,
                    allocated_area_sqm=matched_region.area_sqm,
                    approximate_dimensions=matched_region.approximate_dimensions or (0.0, 0.0),
                    allocated_polygon=tuple(matched_region.polygon),
                    adjacent_region_ids=tuple(matched_region.adjacency_regions),
                    adjacent_room_types=tuple(adj_types),
                    user_required_adjacencies=tuple(user_adj),
                    system_preferred_adjacencies=tuple(sys_adj),
                    avoid_rooms=tuple(floor_spec.avoid_matrix.get(room_spec.room_type, [])),
                    attached_to_room_id=room_spec.attached_to_room_id,
                    user_specified_dimensions=user_dims,
                )
                room_contexts.append(r_ctx)



            f_ctx = FloorDesignContext(
                floor_number=floor_spec.floor_number,
                floor_name=floor_spec.floor_name or f"Floor {floor_spec.floor_number}",
                rooms=tuple(room_contexts),
                circulation_zones=tuple(floor_spec.circulation_zones),
                circulation_notes=floor_spec.circulation_notes,
                entrance_intent=floor_spec.entrance_intent,
                staircase_intent=floor_spec.staircase_intent,
                staircase_region_id=staircase_region_id,
                plot_orientation=plot_orientation,
                strategy=strategy,
                alternative_index=alternative_index,
            )
            floor_contexts.append(f_ctx)

        return ArchitecturalContext(
            project_name=planning_spec.project_name or "PlanForge Project",
            floors=tuple(floor_contexts),
            global_constraints=dict(planning_spec.global_constraints),
            strategy=strategy,
            alternative_index=alternative_index,
        )
