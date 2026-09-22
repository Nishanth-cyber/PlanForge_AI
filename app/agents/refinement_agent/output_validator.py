"""Output validator and change tracker for LLM Refinement Agent responses.

Enforces strict structural constraints on refined architectural proposals:
- No invented rooms
- No missing/deleted rooms
- No allocation modification or movement
- No floor assignment changes
- No raw polygon/CAD coordinates
- Accurate change extraction for provenance and research evaluation
"""

from __future__ import annotations
from typing import Any, Optional, Tuple

from app.agents.architectural_agent.structured_output import (
    AllocationMismatchError,
    ArchitecturalLLMError,
    DimensionExceedsAllocationError,
    InvalidShapeError,
    MalformedLLMResponseError,
    RoomCoverageError,
)
from app.models.allocation import Allocation
from app.models.architectural_design import ArchitecturalDesign, RoomDesign
from app.models.doors import DoorIntent
from app.models.refinement import RefinementChange
from app.models.windows import WindowIntent


class RefinementOutputValidator:
    """Validates raw LLM refinement responses against architectural invariants and tracks changes."""

    ALLOWED_SHAPES = {"rectangular", "square", "l_shaped", "custom"}

    @classmethod
    def validate_and_parse(
        cls,
        raw_dict: dict[str, Any],
        current_floor_design: ArchitecturalDesign,
        allocation: Allocation,
    ) -> Tuple[list[RoomDesign], list[RefinementChange], str]:
        """Validate raw refinement JSON and extract revised RoomDesigns with change records.

        Args:
            raw_dict: Parsed JSON dictionary from LLM response.
            current_floor_design: Current architectural design for the floor.
            allocation: ASAA Allocation for this floor.

        Returns:
            Tuple of:
            - list[RoomDesign]: Validated revised room designs
            - list[RefinementChange]: Granular change records
            - str: Overall refinement rationale

        Raises:
            MalformedLLMResponseError: If JSON structure is invalid.
            RoomCoverageError: If rooms are invented or missing.
            AllocationMismatchError: If allocation IDs are changed.
            DimensionExceedsAllocationError: If room exceeds allocation limits.
            InvalidShapeError: If shape type is invalid.
        """
        if not isinstance(raw_dict, dict):
            raise MalformedLLMResponseError(f"Expected JSON object, got {type(raw_dict).__name__}")

        rooms_data = raw_dict.get("rooms")
        if not isinstance(rooms_data, list):
            raise MalformedLLMResponseError("Refinement response missing 'rooms' list")

        refinement_rationale = str(raw_dict.get("refinement_rationale", "")).strip()

        # Build lookup of current rooms
        current_room_map = {r.id: r for r in current_floor_design.rooms}
        allocation_region_map = {reg.id: reg for reg in allocation.allocated_regions}

        # 1. Check for raw geometry keys (strictly prohibited in refinement output)
        forbidden_keys = {"polygon", "usable_polygon", "built_polygon", "vertices", "coordinates", "walls"}
        for r_dict in rooms_data:
            if not isinstance(r_dict, dict):
                raise MalformedLLMResponseError("Each room proposal must be a JSON dictionary")
            present_forbidden = forbidden_keys.intersection(r_dict.keys())
            if present_forbidden:
                raise MalformedLLMResponseError(
                    f"Refinement output contains forbidden raw geometry keys: {present_forbidden}. "
                    "Only design-intent level attributes are permitted."
                )

        # 2. Check for Invented or Missing Rooms
        output_room_ids = [r_dict.get("id") for r_dict in rooms_data if isinstance(r_dict, dict)]

        # Check for unrequested/invented rooms
        for r_id in output_room_ids:
            if not r_id or r_id not in current_room_map:
                raise RoomCoverageError(
                    f"Refinement response contains an invented or unrequested room ID '{r_id}'. "
                    f"Expected existing rooms: {list(current_room_map.keys())}"
                )

        # Check for duplicate room IDs in response
        if len(output_room_ids) != len(set(output_room_ids)):
            raise RoomCoverageError("Refinement response contains duplicate room IDs")

        # Check for missing rooms
        missing_ids = set(current_room_map.keys()) - set(output_room_ids)
        if missing_ids:
            raise RoomCoverageError(
                f"Refinement response dropped required existing rooms: {sorted(list(missing_ids))}. "
                "All existing rooms must be preserved."
            )

        revised_rooms: list[RoomDesign] = []
        changes: list[RefinementChange] = []

        # 3. Process each room and validate constraints
        for r_dict in rooms_data:
            r_id = r_dict["id"]
            current_room = current_room_map[r_id]

            # Invariant: Allocation ID cannot be modified by refinement
            alloc_id = r_dict.get("allocated_region_id") or current_room.allocated_region_id
            if alloc_id != current_room.allocated_region_id:
                raise AllocationMismatchError(
                    f"Room '{r_id}' attempted to change allocated_region_id from "
                    f"'{current_room.allocated_region_id}' to '{alloc_id}'. "
                    "ASAA allocations are immutable during refinement."
                )

            region = allocation_region_map.get(alloc_id)
            if not region:
                raise AllocationMismatchError(
                    f"Room '{r_id}' references unknown allocated_region_id '{alloc_id}'"
                )

            # Validate shape
            intended_shape = r_dict.get("intended_shape", current_room.intended_shape)
            if intended_shape not in cls.ALLOWED_SHAPES:
                raise InvalidShapeError(
                    f"Room '{r_id}' has invalid shape '{intended_shape}'. Allowed: {cls.ALLOWED_SHAPES}"
                )

            # Validate dimensions
            dims_raw = r_dict.get("intended_dimensions")
            if dims_raw:
                if not (isinstance(dims_raw, (list, tuple)) and len(dims_raw) == 2):
                    raise DimensionExceedsAllocationError(
                        f"Room '{r_id}' dimensions must be a [width, length] pair, got {dims_raw}"
                    )
                w, l = float(dims_raw[0]), float(dims_raw[1])
                if w <= 0.1 or l <= 0.1:
                    raise DimensionExceedsAllocationError(
                        f"Room '{r_id}' has non-positive dimensions ({w}x{l})"
                    )
                intended_dims = (w, l)
                intended_area = round(w * l, 2)
            else:
                intended_dims = current_room.intended_dimensions
                intended_area = current_room.intended_area_sqm

            # Check bounds against allocated region
            if region.approximate_dimensions and intended_dims:
                reg_w, reg_l = region.approximate_dimensions
                max_dim = max(reg_w, reg_l) * 1.15
                min_dim = min(reg_w, reg_l) * 1.15
                w, l = intended_dims
                if min(w, l) > min_dim or max(w, l) > max_dim:
                    raise DimensionExceedsAllocationError(
                        f"Room '{r_id}' dimensions ({w:.2f}x{l:.2f}m) exceed ASAA allocated region bounds "
                        f"({reg_w:.2f}x{reg_l:.2f}m)"
                    )

            # Parse DoorIntents
            doors: list[DoorIntent] = []
            for d_data in r_dict.get("doors", []):
                doors.append(
                    DoorIntent(
                        connects_from=current_room.id,
                        wall_orientation=d_data.get("wall_orientation", "south"),
                        connects_to=d_data.get("connects_to", ""),
                        door_type=d_data.get("door_type", "interior"),
                        recommended_width=float(d_data.get("recommended_width", 0.9)),
                        recommended_height=float(d_data.get("recommended_height", 2.1)),
                        floor_number=current_room.floor_number,
                        rationale=d_data.get("rationale", ""),
                    )
                )

            # Parse WindowIntents
            is_bath = current_room.room_type in {"bathroom", "toilet", "wc", "powder_room"}
            def_win_w = 0.6 if is_bath else 1.2
            def_win_h = 0.6 if is_bath else 1.2
            def_sill = 1.5 if is_bath else 0.9

            windows: list[WindowIntent] = []
            for w_data in r_dict.get("windows", []):
                windows.append(
                    WindowIntent(
                        room_id=current_room.id,
                        wall_orientation=w_data.get("wall_orientation", "north"),
                        window_type=w_data.get("window_type", "standard"),
                        recommended_width=float(w_data.get("recommended_width", def_win_w)),
                        recommended_height=float(w_data.get("recommended_height", def_win_h)),
                        sill_height=float(w_data.get("sill_height", def_sill)),
                        floor_number=current_room.floor_number,
                        rationale=w_data.get("rationale", ""),
                    )
                )

            design_rationale = str(r_dict.get("design_rationale", current_room.design_rationale)).strip()

            # Construct revised RoomDesign
            revised_room = RoomDesign(
                id=current_room.id,
                room_type=current_room.room_type,
                allocated_region_id=current_room.allocated_region_id,
                floor_number=current_room.floor_number,
                intended_shape=intended_shape,
                intended_dimensions=intended_dims,
                intended_area_sqm=intended_area,
                proposed_boundary=current_room.proposed_boundary,
                doors=doors,
                windows=windows,
                connected_spaces=current_room.connected_spaces,
                design_rationale=design_rationale,
            )
            revised_rooms.append(revised_room)

            # Track changes against current_room
            cls._record_room_changes(current_room, revised_room, changes)

        return revised_rooms, changes, refinement_rationale

    @classmethod
    def _record_room_changes(
        cls,
        old_room: RoomDesign,
        new_room: RoomDesign,
        changes_list: list[RefinementChange],
    ) -> None:
        """Compare old and new RoomDesign objects and append change records."""
        # 1. Dimensions
        if old_room.intended_dimensions != new_room.intended_dimensions:
            changes_list.append(
                RefinementChange(
                    room_id=old_room.id,
                    field_changed="intended_dimensions",
                    old_value=list(old_room.intended_dimensions) if old_room.intended_dimensions else None,
                    new_value=list(new_room.intended_dimensions) if new_room.intended_dimensions else None,
                    reason=new_room.design_rationale or "Adjusted room dimensions to satisfy validation",
                )
            )

        # 2. Shape
        if old_room.intended_shape != new_room.intended_shape:
            changes_list.append(
                RefinementChange(
                    room_id=old_room.id,
                    field_changed="intended_shape",
                    old_value=old_room.intended_shape,
                    new_value=new_room.intended_shape,
                    reason=new_room.design_rationale or "Adjusted room shape to satisfy validation",
                )
            )

        # 3. Doors
        old_doors = [(d.wall_orientation, d.connects_to, d.door_type) for d in old_room.doors]
        new_doors = [(d.wall_orientation, d.connects_to, d.door_type) for d in new_room.doors]
        if old_doors != new_doors:
            changes_list.append(
                RefinementChange(
                    room_id=old_room.id,
                    field_changed="doors",
                    old_value=[{"wall": d[0], "to": d[1], "type": d[2]} for d in old_doors],
                    new_value=[{"wall": d[0], "to": d[1], "type": d[2]} for d in new_doors],
                    reason=new_room.design_rationale or "Adjusted door intents to resolve connectivity/adjacency",
                )
            )

        # 4. Windows
        old_windows = [(w.wall_orientation, getattr(w, "window_type", "standard")) for w in old_room.windows]
        new_windows = [(w.wall_orientation, getattr(w, "window_type", "standard")) for w in new_room.windows]
        if old_windows != new_windows:
            changes_list.append(
                RefinementChange(
                    room_id=old_room.id,
                    field_changed="windows",
                    old_value=[{"wall": w[0], "type": w[1]} for w in old_windows],
                    new_value=[{"wall": w[0], "type": w[1]} for w in new_windows],
                    reason=new_room.design_rationale or "Adjusted window intents to resolve lighting/orientation",
                )
            )
