"""Structured output schemas, exceptions, and validation for the Architectural LLM."""

from __future__ import annotations
from typing import Any, Optional
from app.agents.architectural_agent.context import FloorDesignContext, RoomDesignContext
from app.models.architectural_design import RoomDesign
from app.models.doors import DoorIntent
from app.models.windows import WindowIntent
from app.utils.ids import generate_id


class ArchitecturalLLMError(ValueError):
    """Base exception for Architectural LLM failures."""
    pass


class MalformedLLMResponseError(ArchitecturalLLMError):
    """Raised when LLM response is not valid JSON or misses expected top-level schema."""
    pass


class RoomCoverageError(ArchitecturalLLMError):
    """Raised when an allocated room is missing or an unrequested room is invented."""
    pass


class AllocationMismatchError(ArchitecturalLLMError):
    """Raised when a proposed room design does not match its ASAA allocated region or floor."""
    pass


class DimensionExceedsAllocationError(ArchitecturalLLMError):
    """Raised when proposed room dimensions exceed ASAA allocation limits or are invalid."""
    pass


class UserDimensionConstraintViolationError(ArchitecturalLLMError):
    """Raised when proposed room dimensions violate explicit user-specified dimensions."""
    pass


class InvalidShapeError(ArchitecturalLLMError):
    """Raised when an unsupported or invalid semantic shape type is proposed."""
    pass


class ArchitecturalOutputValidator:
    """Validates raw LLM response dictionaries against architectural constraints."""

    ALLOWED_SHAPES = {"rectangular", "square", "l_shaped", "custom"}


    @staticmethod
    def validate_and_parse(
        raw_dict: dict[str, Any],
        context: FloorDesignContext,
    ) -> list[RoomDesign]:
        """Validate and parse raw LLM JSON response into a list of RoomDesign objects.

        Args:
            raw_dict: Parsed JSON dictionary from the LLM.
            context: FloorDesignContext for the target floor.

        Returns:
            List of validated RoomDesign proposals.

        Raises:
            MalformedLLMResponseError: If dictionary lacks 'rooms' list.
            RoomCoverageError: If rooms are missing or invented.
            AllocationMismatchError: If allocation IDs or floor numbers mismatch.
            DimensionExceedsAllocationError: If proposed area exceeds allocation or dimensions are non-positive.
            InvalidShapeError: If shape type is not in ALLOWED_SHAPES.
        """
        if not isinstance(raw_dict, dict):
            raise MalformedLLMResponseError(f"Expected JSON object, got {type(raw_dict).__name__}")

        rooms_data = raw_dict.get("rooms")
        if not isinstance(rooms_data, list):
            raise MalformedLLMResponseError("LLM response missing 'rooms' list")

        expected_room_map = {r.room_id: r for r in context.rooms}
        provided_room_ids: set[str] = set()
        validated_rooms: list[RoomDesign] = []

        for r_entry in rooms_data:
            if not isinstance(r_entry, dict):
                raise MalformedLLMResponseError("Room entry must be a dictionary")

            # 1. Room Identification & Coverage Check
            room_id = r_entry.get("room_id")
            if not room_id:
                raise MalformedLLMResponseError("Room entry missing 'room_id'")

            if room_id in provided_room_ids:
                raise RoomCoverageError(f"Duplicate room proposal for room_id '{room_id}'")
            provided_room_ids.add(room_id)

            if room_id not in expected_room_map:
                raise RoomCoverageError(
                    f"Invented room detected: '{room_id}' was not in the ASAA planning context"
                )

            room_ctx = expected_room_map[room_id]

            # 2. Allocation Reference Check
            alloc_reg_id = r_entry.get("allocated_region_id")
            if alloc_reg_id and alloc_reg_id != room_ctx.allocated_region_id:
                raise AllocationMismatchError(
                    f"Room '{room_id}' allocation reference mismatch: "
                    f"expected '{room_ctx.allocated_region_id}', got '{alloc_reg_id}'"
                )

            floor_num = r_entry.get("floor_number", context.floor_number)
            if floor_num != context.floor_number:
                raise AllocationMismatchError(
                    f"Room '{room_id}' floor mismatch: expected floor {context.floor_number}, got {floor_num}"
                )

            # 3. Shape Validation
            shape_type = str(r_entry.get("intended_shape", "rectangular")).lower()
            if shape_type not in ArchitecturalOutputValidator.ALLOWED_SHAPES:
                raise InvalidShapeError(
                    f"Room '{room_id}' proposed unsupported shape: '{shape_type}'. "
                    f"Supported shapes: {ArchitecturalOutputValidator.ALLOWED_SHAPES}"
                )

            # 4. Dimensions & Area Validation
            dims = r_entry.get("intended_dimensions")
            width, length = None, None
            if dims is not None:
                if not isinstance(dims, (list, tuple)) or len(dims) != 2:
                    raise DimensionExceedsAllocationError(
                        f"Room '{room_id}' invalid intended_dimensions format: {dims}"
                    )
                w, l = float(dims[0]), float(dims[1])
                if w <= 0 or l <= 0:
                    raise DimensionExceedsAllocationError(
                        f"Room '{room_id}' dimensions must be positive, got ({w}, {l})"
                    )
                width, length = w, l

            proposed_area = float(r_entry.get("intended_area_sqm", 0.0))

            # Check user-specified dimensions (hard constraint)
            if getattr(room_ctx, "user_specified_dimensions", None) is not None:

                uw, ul = room_ctx.user_specified_dimensions
                if width is None or length is None:
                    width, length = uw, ul
                    proposed_area = round(uw * ul, 2)
                else:
                    # Allow either orientation: (w~uw and l~ul) or (w~ul and l~uw)
                    matches = (
                        (abs(width - uw) <= 0.1 and abs(length - ul) <= 0.1) or
                        (abs(width - ul) <= 0.1 and abs(length - uw) <= 0.1)
                    )
                    if not matches:
                        raise UserDimensionConstraintViolationError(
                            f"Room '{room_id}' violated user-specified dimensions: "
                            f"expected ({uw}, {ul}), got ({width}, {length})"
                        )

            if proposed_area <= 0 and width and length:
                proposed_area = width * length

            if proposed_area <= 0:
                raise DimensionExceedsAllocationError(
                    f"Room '{room_id}' must have positive intended_area_sqm"
                )

            # Check against ASAA allocated area (+5% tolerance for rounding)
            max_permitted_area = room_ctx.allocated_area_sqm * 1.05
            if proposed_area > max_permitted_area:
                raise DimensionExceedsAllocationError(
                    f"Room '{room_id}' proposed area ({proposed_area:.2f} m²) exceeds "
                    f"ASAA allocated region area ({room_ctx.allocated_area_sqm:.2f} m²)"
                )

            # Check against explicit user minimum if specified
            if room_ctx.min_area_sqm is not None and proposed_area < (room_ctx.min_area_sqm - 0.2):
                raise DimensionExceedsAllocationError(
                    f"Room '{room_id}' proposed area ({proposed_area:.2f} m²) is below "
                    f"explicit user minimum area ({room_ctx.min_area_sqm:.2f} m²)"
                )

            # 5. Parse Door Intents
            door_intents: list[DoorIntent] = []
            for d in r_entry.get("doors", []):
                if isinstance(d, dict):
                    to_target = str(d.get("connects_to", "circulation"))
                    door_intents.append(
                        DoorIntent(
                            id=generate_id("door"),
                            connects_from=room_id,
                            connects_to=to_target,
                            wall_orientation=d.get("wall_orientation"),
                            door_type=str(d.get("door_type", "interior")),
                            recommended_width=float(d.get("recommended_width", 0.9)),
                            recommended_height=float(d.get("recommended_height", 2.1)),
                            floor_number=context.floor_number,
                            rationale=str(d.get("rationale", "")),
                        )
                    )

            # 6. Parse Window Intents
            window_intents: list[WindowIntent] = []
            for w in r_entry.get("windows", []):
                if isinstance(w, dict):
                    window_intents.append(
                        WindowIntent(
                            id=generate_id("window"),
                            room_id=room_id,
                            wall_orientation=str(w.get("wall_orientation", "")),
                            window_type=str(w.get("window_type", "standard")),
                            recommended_width=float(w.get("recommended_width", 1.2)),
                            recommended_height=float(w.get("recommended_height", 1.2)),
                            sill_height=float(w.get("sill_height", 0.9)),
                            floor_number=context.floor_number,
                            rationale=str(w.get("rationale", "")),
                        )
                    )

            connected_spaces = list(r_entry.get("connected_spaces", []))
            rationale = str(r_entry.get("design_rationale", ""))

            room_design = RoomDesign(
                id=generate_id("room_design"),
                room_type=room_ctx.room_type,
                allocated_region_id=room_ctx.allocated_region_id,
                floor_number=context.floor_number,
                intended_shape=shape_type,
                intended_dimensions=(width, length) if width and length else None,
                intended_area_sqm=round(proposed_area, 2),
                proposed_boundary=[],  # Abstract proposal; Geometry Engine builds real geometry
                doors=door_intents,
                windows=window_intents,
                connected_spaces=connected_spaces,
                design_rationale=rationale,
            )
            validated_rooms.append(room_design)

        # 7. Check for Missing Rooms
        missing_room_ids = set(expected_room_map.keys()) - provided_room_ids
        if missing_room_ids:
            missing_names = [expected_room_map[rid].room_type for rid in missing_room_ids]
            raise RoomCoverageError(
                f"Missing room proposals for: {missing_names} (IDs: {list(missing_room_ids)})"
            )

        return validated_rooms
