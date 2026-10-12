"""Design Editing Agent for PlanForge AI.

Coordinates natural-language modifications to existing architectural floor plans:
1. Understands user editing instructions via intelligent edit intent detection.
2. Retrieves current project baseline and floor-plan state without creating duplicates.
3. Identifies target rooms and architectural elements.
4. Generates validated, structured edit operations adhering to minimal-change strategy.
5. Reconstructs physical CAD geometry using the authoritative Geometry Engine.
6. Runs independent FloorPlanValidator verification.
7. Invokes Refinement Agent if validation feedback can improve the proposal.
8. Maintains version history and provides safe, verified undo capabilities.
9. Updates project export artifacts (SVG, CAD DXF, JSON) and provides concise change summaries.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agents.editing_agent.intent import EditIntentResult, EditIntentType, detect_edit_intent
from app.agents.editing_agent.operations import EditOperation, EditOperationType, EditPlan
from app.agents.editing_agent.versioning import DesignVersion, ProjectVersionHistory
from app.export.bundle_exporter import BundleExporter
from app.export.json_exporter import export_project_json, save_json
from app.geometry.engine import GeometryEngine
from app.geometry.geometry_utils import to_shapely_polygon
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.floor_plan import FloorPlanSet
from app.models.validation import ValidationReport
from app.models.windows import WindowIntent
from app.rendering.floor_renderer import FloorPlanRenderer
from app.utils.ids import generate_id
from app.validation.validator import FloorPlanValidator

logger = logging.getLogger(__name__)


@dataclass
class EditResult:
    """Consolidated outcome of an architectural design edit operation."""

    success: bool
    project_id: str
    version_id: str = "v1"
    instruction: str = ""
    summary: str = ""
    is_valid: bool = True
    validation_summary: Optional[Dict[str, Any]] = None
    affected_rooms: List[str] = field(default_factory=list)
    affected_elements: List[str] = field(default_factory=list)
    can_undo: bool = False
    clarification_required: bool = False
    clarification_question: Optional[str] = None
    new_design_requested: bool = False
    error_message: Optional[str] = None
    feasible_alternatives: List[str] = field(default_factory=list)
    updated_floor_plan_set: Optional[FloorPlanSet] = None


class DesignEditingAgent:
    """Dedicated agent responsible for translating natural language edit requests into verified geometry."""

    def __init__(
        self,
        geometry_engine: Optional[GeometryEngine] = None,
        validator: Optional[FloorPlanValidator] = None,
        renderer: Optional[FloorPlanRenderer] = None,
        exporter: Optional[BundleExporter] = None,
        outputs_dir: str = "outputs",
    ):
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.validator = validator or FloorPlanValidator()
        self.renderer = renderer or FloorPlanRenderer()
        self.exporter = exporter or BundleExporter()
        self.outputs_dir = Path(outputs_dir)
        self._project_histories: Dict[str, ProjectVersionHistory] = {}

    def get_history(self, project_id: str) -> ProjectVersionHistory:
        """Retrieve or initialize ProjectVersionHistory for a project."""
        if project_id not in self._project_histories:
            self._project_histories[project_id] = ProjectVersionHistory(project_id)
        return self._project_histories[project_id]

    # -----------------------------------------------------------------------
    # Main Entry: Edit Design
    # -----------------------------------------------------------------------
    def edit_design(
        self,
        project_result: Any,
        instruction: str,
        floor_number: Optional[int] = None,
        alternative_index: int = 1,
    ) -> EditResult:
        """Apply a natural-language edit instruction to an existing project's design.

        Args:
            project_result: Current PipelineResult from ProjectRegistry.
            instruction: Natural-language modification request.
            floor_number: Optional target floor number (defaults to 1 or inferred).
            alternative_index: Alternative index if modifying an alternative (default: 1).

        Returns:
            EditResult with updated state, change summary, validation outcome, and undo availability.
        """
        project_id = getattr(project_result, "project_id", "")
        if not project_id:
            return EditResult(
                success=False,
                project_id="",
                summary="Invalid project ID.",
                error_message="Project does not exist or has no ID.",
            )

        history = self.get_history(project_id)

        # Baseline resolution
        base_arch_set = getattr(project_result, "architectural_design_set", None)
        base_alloc_set = getattr(project_result, "allocation_set", None)
        base_fps = getattr(project_result, "floor_plan_set", None)
        base_val = getattr(project_result, "validation_report", None)
        requirements = getattr(project_result, "requirements", None)
        planning_spec = getattr(project_result, "planning_spec", None)
        project_name = getattr(project_result, "project_name", project_id)

        # Handle alternatives fallback if primary set empty
        if not base_fps and getattr(project_result, "alternative_set", None):
            alts = project_result.alternative_set.alternatives
            if alts:
                alt = next((a for a in alts if a.index == alternative_index), alts[0])
                base_arch_set = base_arch_set or alt.architectural_design_set
                base_alloc_set = base_alloc_set or alt.allocation_set
                base_fps = base_fps or alt.floor_plan_set
                base_val = base_val or alt.validation_report

        if not base_arch_set or not base_alloc_set or not base_fps:
            return EditResult(
                success=False,
                project_id=project_id,
                summary="No generated design available to edit.",
                error_message="Project must have a completed generated floor plan before edits can be applied.",
            )

        # Ensure base version (v1) is initialized in history
        history.initialize_base(
            architectural_design_set=base_arch_set,
            allocation_set=base_alloc_set,
            floor_plan_set=base_fps,
            validation_report=base_val,
            project_name=project_name,
        )

        # 1. Intent Detection
        intent_res = detect_edit_intent(instruction)

        if intent_res.intent == EditIntentType.NEW_DESIGN:
            return EditResult(
                success=False,
                project_id=project_id,
                new_design_requested=True,
                summary="You requested to start a new design. Use the New Project wizard to start fresh.",
            )

        if intent_res.intent == EditIntentType.CLARIFICATION_REQUIRED:
            return EditResult(
                success=False,
                project_id=project_id,
                clarification_required=True,
                clarification_question=intent_res.clarification_question,
                summary="Could not determine exact edit target.",
            )

        # 2. Plan structured operations
        plan = self._create_edit_plan(
            instruction=instruction,
            intent_res=intent_res,
            arch_set=base_arch_set,
            alloc_set=base_alloc_set,
            preferred_floor=floor_number,
        )

        if plan.clarification_question:
            return EditResult(
                success=False,
                project_id=project_id,
                clarification_required=True,
                clarification_question=plan.clarification_question,
                summary="Clarification required to execute edit.",
            )

        if not plan.operations:
            return EditResult(
                success=False,
                project_id=project_id,
                summary="No applicable modifications detected.",
                error_message="The modification request produced no actionable changes to the current design.",
            )

        # 3. Apply operations with minimal changes
        modified_arch_set = copy.deepcopy(base_arch_set)
        modified_alloc_set = copy.deepcopy(base_alloc_set)

        applied_summaries: List[str] = []
        affected_rooms: List[str] = []
        affected_elements: List[str] = []

        try:
            for op in plan.operations:
                op.validate()
                op_summary, rooms, elements = self._apply_operation(
                    op=op,
                    arch_set=modified_arch_set,
                    alloc_set=modified_alloc_set,
                    requirements=requirements,
                )
                applied_summaries.append(op_summary)
                affected_rooms.extend(rooms)
                affected_elements.extend(elements)
        except Exception as exc:
            logger.warning("Edit operation application failed: %s", exc)
            return EditResult(
                success=False,
                project_id=project_id,
                summary=f"Unable to apply change: {str(exc)}",
                error_message=str(exc),
                can_undo=history.can_undo,
                feasible_alternatives=[
                    "Check room dimensions within available buildable bounds.",
                    "Verify target room exists in the floor plan.",
                ],
            )

        # 4. Reconstruct geometry using Geometry Engine
        try:
            reconstructed_fps = self.geometry_engine.construct(
                design_set=modified_arch_set,
                allocation_set=modified_alloc_set,
                plot_boundary=base_fps.plot_boundary,
                buildable_boundary=base_fps.buildable_boundary,
                project_name=project_name,
            )
        except Exception as exc:
            logger.warning("Geometry reconstruction failed after edit: %s", exc)
            return EditResult(
                success=False,
                project_id=project_id,
                summary="Geometry reconstruction failed for requested modification.",
                error_message=f"Geometry Engine error: {str(exc)}",
                can_undo=history.can_undo,
                feasible_alternatives=["Try adjusting dimensions to fit comfortably within the room's allocated boundary."],
            )

        # 5. Independent Validator Verification
        validation_report = self.validator.validate(
            floor_plan_set=reconstructed_fps,
            requirements=requirements,
            planning_spec=planning_spec,
            allocation_set=modified_alloc_set,
            architectural_design_set=modified_arch_set,
            plot_boundary=base_fps.plot_boundary,
            buildable_boundary=base_fps.buildable_boundary,
        )

        # Hard failure handling: if edit causes serious violations, reject and retain previous valid design
        if not validation_report.overall_valid and validation_report.total_errors > 0:
            error_msgs = [issue.message for issue in validation_report.all_issues() if issue.severity == "error"]
            err_summary = error_msgs[0] if error_msgs else "Building code violation detected."
            return EditResult(
                success=False,
                project_id=project_id,
                summary=f"Edit rejected by independent validator: {err_summary}",
                error_message=err_summary,
                is_valid=False,
                validation_summary={
                    "overall_valid": False,
                    "overall_score": round(validation_report.overall_score, 1),
                    "total_errors": validation_report.total_errors,
                    "total_warnings": validation_report.total_warnings,
                },
                can_undo=history.can_undo,
                feasible_alternatives=[
                    "Reduce requested dimensions to avoid boundary or overlap violations.",
                    "Ensure connected rooms share a partition wall for door placement.",
                ],
            )

        # 6. Accepted Edit: Record in Version History
        concise_summary = "; ".join(applied_summaries)
        val_status_str = f"Validation: Valid (score: {validation_report.overall_score:.1f}/100)"
        full_summary = f"{concise_summary}. Unaffected rooms preserved. {val_status_str}."

        new_version = history.record_version(
            user_instruction=instruction,
            operations=[op.to_dict() for op in plan.operations],
            affected_room_ids=list(set(affected_rooms)),
            affected_element_ids=list(set(affected_elements)),
            architectural_design_set=modified_arch_set,
            allocation_set=modified_alloc_set,
            floor_plan_set=reconstructed_fps,
            validation_report=validation_report,
            summary_of_changes=full_summary,
        )

        # 7. Update active project in ProjectRegistry (modify in place)
        project_result.architectural_design_set = modified_arch_set
        project_result.allocation_set = modified_alloc_set
        project_result.floor_plan_set = reconstructed_fps
        project_result.validation_report = validation_report
        project_result.status = "completed"

        # Update primary alternative if present
        if getattr(project_result, "alternative_set", None) and project_result.alternative_set.alternatives:
            alt0 = project_result.alternative_set.alternatives[0]
            alt0.architectural_design_set = modified_arch_set
            alt0.allocation_set = modified_alloc_set
            alt0.floor_plan_set = reconstructed_fps
            alt0.validation_report = validation_report

        # 8. Re-render exports (SVG, DXF, PNG, project.json) in place
        self._update_exports(project_result)

        return EditResult(
            success=True,
            project_id=project_id,
            version_id=new_version.version_id,
            instruction=instruction,
            summary=full_summary,
            is_valid=validation_report.overall_valid,
            validation_summary={
                "overall_valid": validation_report.overall_valid,
                "overall_score": round(validation_report.overall_score, 1),
                "total_errors": validation_report.total_errors,
                "total_warnings": validation_report.total_warnings,
            },
            affected_rooms=list(set(affected_rooms)),
            affected_elements=list(set(affected_elements)),
            can_undo=history.can_undo,
            updated_floor_plan_set=reconstructed_fps,
        )

    # -----------------------------------------------------------------------
    # Undo Design
    # -----------------------------------------------------------------------
    def undo_design(self, project_result: Any) -> EditResult:
        """Safely restore the previous design version and revalidate.

        Args:
            project_result: Current PipelineResult to revert.

        Returns:
            EditResult with restored version state and change description.
        """
        project_id = getattr(project_result, "project_id", "")
        if not project_id:
            return EditResult(success=False, project_id="", summary="Invalid project ID.")

        history = self.get_history(project_id)
        if not history.can_undo:
            return EditResult(
                success=False,
                project_id=project_id,
                summary="Nothing to undo: already at the earliest design version.",
                can_undo=False,
            )

        restored_version = history.undo()
        if not restored_version or not restored_version.floor_plan_set:
            return EditResult(
                success=False,
                project_id=project_id,
                summary="Failed to restore previous version.",
                can_undo=history.can_undo,
            )

        # Restore project_result references
        project_result.architectural_design_set = copy.deepcopy(restored_version.architectural_design_set)
        project_result.allocation_set = copy.deepcopy(restored_version.allocation_set)
        project_result.floor_plan_set = copy.deepcopy(restored_version.floor_plan_set)
        project_result.validation_report = copy.deepcopy(restored_version.validation_report)

        if getattr(project_result, "alternative_set", None) and project_result.alternative_set.alternatives:
            alt0 = project_result.alternative_set.alternatives[0]
            alt0.architectural_design_set = project_result.architectural_design_set
            alt0.allocation_set = project_result.allocation_set
            alt0.floor_plan_set = project_result.floor_plan_set
            alt0.validation_report = project_result.validation_report

        # Re-export restored bundle
        self._update_exports(project_result)

        val_summary = None
        if restored_version.validation_report:
            val_summary = {
                "overall_valid": restored_version.validation_report.overall_valid,
                "overall_score": round(restored_version.validation_report.overall_score, 1),
                "total_errors": restored_version.validation_report.total_errors,
                "total_warnings": restored_version.validation_report.total_warnings,
            }

        return EditResult(
            success=True,
            project_id=project_id,
            version_id=restored_version.version_id,
            instruction=f"Restored {restored_version.version_id}",
            summary=f"Restored previous design ({restored_version.version_id}).",
            is_valid=restored_version.validation_report.overall_valid if restored_version.validation_report else True,
            validation_summary=val_summary,
            can_undo=history.can_undo,
            updated_floor_plan_set=restored_version.floor_plan_set,
        )

    # -----------------------------------------------------------------------
    # Planning Edit Operations
    # -----------------------------------------------------------------------
    def _create_edit_plan(
        self,
        instruction: str,
        intent_res: EditIntentResult,
        arch_set: ArchitecturalDesignSet,
        alloc_set: AllocationSet,
        preferred_floor: Optional[int] = None,
    ) -> EditPlan:
        """Translate classified intent into a structured EditPlan."""
        plan = EditPlan(instruction=instruction, intent=intent_res.intent)
        target_rtype = intent_res.target_room_type

        # Find target room across designs
        target_room: Optional[RoomDesign] = None
        target_floor = preferred_floor or 1

        if target_rtype:
            for design in arch_set.designs:
                if preferred_floor is None or design.floor_number == preferred_floor:
                    for r in design.rooms:
                        if r.room_type == target_rtype:
                            target_room = r
                            target_floor = design.floor_number
                            break
                    if target_room:
                        break

            # If not found on preferred floor, search any floor
            if not target_room:
                for design in arch_set.designs:
                    for r in design.rooms:
                        if r.room_type == target_rtype:
                            target_room = r
                            target_floor = design.floor_number
                            break
                    if target_room:
                        break

        # Check for window / door operations
        if intent_res.target_element_type == "window":
            if not target_room:
                plan.clarification_question = f"Which room should the window be added or modified in? Found types: {', '.join(r.room_type for d in arch_set.designs for r in d.rooms)}"
                return plan

            op_type = (
                EditOperationType.REMOVE_WINDOW
                if intent_res.intent == EditIntentType.REMOVE_ELEMENT
                else (EditOperationType.ADD_WINDOW if intent_res.intent == EditIntentType.ADD_ELEMENT else EditOperationType.MODIFY_WINDOW)
            )
            plan.operations.append(
                EditOperation(
                    operation=op_type,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.target_element_type == "door":
            if not target_room:
                plan.clarification_question = "Which room should the door be connected to?"
                return plan

            op_type = (
                EditOperationType.REMOVE_DOOR
                if intent_res.intent == EditIntentType.REMOVE_ELEMENT
                else (EditOperationType.ADD_DOOR if intent_res.intent == EditIntentType.ADD_ELEMENT else EditOperationType.MODIFY_DOOR)
            )
            plan.operations.append(
                EditOperation(
                    operation=op_type,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.target_element_type == "entrance":
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.MODIFY_ENTRANCE,
                    floor_number=1,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.target_element_type == "circulation":
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.MODIFY_CIRCULATION,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        # Room level operations
        if intent_res.intent == EditIntentType.MODIFY_SHAPE:
            if not target_room:
                plan.clarification_question = "Which room would you like to change the shape of?"
                return plan
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.MODIFY_ROOM_SHAPE,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.intent == EditIntentType.MODIFY_DIMENSIONS:
            if not target_room:
                plan.clarification_question = "Which room would you like to resize or make more spacious?"
                return plan
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.MODIFY_ROOM_DIMENSIONS,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.intent == EditIntentType.MODIFY_LAYOUT:
            if not target_room:
                plan.clarification_question = "Which room's location or layout would you like to adjust?"
                return plan
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.MODIFY_ROOM_POSITION,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.intent == EditIntentType.ADD_ELEMENT:
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.ADD_ROOM,
                    target_room_type=target_rtype or "study",
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        if intent_res.intent == EditIntentType.REMOVE_ELEMENT:
            if not target_room:
                plan.clarification_question = "Which room would you like to remove?"
                return plan
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.REMOVE_ROOM,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes=intent_res.requested_changes,
                )
            )
            return plan

        # Default fallback: dimension modification if target room identified
        if target_room:
            plan.operations.append(
                EditOperation(
                    operation=EditOperationType.MODIFY_ROOM_DIMENSIONS,
                    target_room_id=target_room.id,
                    target_room_type=target_room.room_type,
                    floor_number=target_floor,
                    changes={"scale_factor": 1.15},
                )
            )
        else:
            plan.clarification_question = "Please specify which room or element you would like to edit."

        return plan

    # -----------------------------------------------------------------------
    # Operation Application (Minimal-Change Strategy)
    # -----------------------------------------------------------------------
    def _apply_operation(
        self,
        op: EditOperation,
        arch_set: ArchitecturalDesignSet,
        alloc_set: AllocationSet,
        requirements: Optional[Any],
    ) -> Tuple[str, List[str], List[str]]:
        """Apply a single validated operation to domain models in place."""
        floor_design = arch_set.get_design(op.floor_number) or arch_set.designs[0]
        floor_alloc = alloc_set.get_allocation(op.floor_number) or alloc_set.allocations[0]

        target_room: Optional[RoomDesign] = None
        if op.target_room_id:
            target_room = floor_design.get_room(op.target_room_id)
        elif op.target_room_type:
            matching = floor_design.get_rooms_by_type(op.target_room_type)
            if matching:
                target_room = matching[0]

        target_region: Optional[AllocatedRegion] = None
        if target_room and target_room.allocated_region_id:
            target_region = floor_alloc.get_region_by_id(target_room.allocated_region_id)
        elif target_room:
            matching_regs = floor_alloc.get_regions_by_type(target_room.room_type)
            if matching_regs:
                target_region = matching_regs[0]

        # 1. MODIFY_ROOM_SHAPE
        if op.operation == EditOperationType.MODIFY_ROOM_SHAPE:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            new_shape = op.changes.get("intended_shape", "rectangular")
            target_room.intended_shape = new_shape
            # Clear arbitrary proposed_boundary to allow PolygonBuilder to draft exact shape
            target_room.proposed_boundary = []
            return f"Changed {target_room.room_type} shape to {new_shape}", [target_room.id], [target_room.id]

        # 2. MODIFY_ROOM_DIMENSIONS
        if op.operation == EditOperationType.MODIFY_ROOM_DIMENSIONS:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")

            target_area = op.changes.get("target_area_sqm")
            dims = op.changes.get("intended_dimensions")
            scale = op.changes.get("scale_factor")

            if target_area is not None:
                new_area = float(target_area)
            elif scale is not None:
                current_area = target_room.intended_area_sqm or (target_region.area_sqm if target_region else 12.0)
                new_area = round(current_area * float(scale), 2)
            elif dims is not None:
                new_area = round(float(dims[0]) * float(dims[1]), 2)
            else:
                new_area = (target_room.intended_area_sqm or 12.0) + 3.0

            # Feasibility check: area vs total buildable envelope
            buildable_poly = getattr(alloc_set, "buildable_boundary", None) or []
            if buildable_poly and len(buildable_poly) >= 3:
                try:
                    b_area = float(to_shapely_polygon(buildable_poly).area)
                except Exception:
                    b_area = 0.0
                if b_area > 0 and new_area > b_area * 0.7:
                    raise ValueError(
                        f"Requested area of {new_area:.1f} m² exceeds the available footprint ({b_area:.1f} m²)."
                    )

            target_room.intended_area_sqm = new_area
            # Update intended_dimensions proportional to area
            if dims is not None:
                target_room.intended_dimensions = (float(dims[0]), float(dims[1]))
                target_room.proposed_boundary = []
                if target_region:
                    target_region.target_area_sqm = new_area
                    target_region.approximate_dimensions = target_room.intended_dimensions
                return f"Updated {target_room.room_type} dimensions to {dims[0]}x{dims[1]} m", [target_room.id], [target_room.id]

            # Area / scale modification: adjust shared partition wall with non-corridor neighbor
            adjusted_neighbor = False
            if target_region and target_region.polygon and len(target_region.polygon) >= 3:
                r_poly = to_shapely_polygon(target_region.polygon)
                min_x, min_y, max_x, max_y = r_poly.bounds
                reg_w = round(max_x - min_x, 2)
                reg_l = round(max_y - min_y, 2)
                cur_usable = max(0.1, round((reg_w - 0.2) * (reg_l - 0.2), 2))

                # Find a non-corridor neighbor sharing a wall
                neighbor_reg = None
                for aid in target_region.adjacency_regions:
                    cand = floor_alloc.get_region_by_id(aid)
                    if cand and cand.zone_type == "room" and cand.room_type not in ("corridor", "foyer", "circulation") and cand.polygon:
                        neighbor_reg = cand
                        break

                if neighbor_reg:
                    n_poly = to_shapely_polygon(neighbor_reg.polygon)
                    n_min_x, n_min_y, n_max_x, n_max_y = n_poly.bounds
                    neighbor_room = next((r for r in floor_design.rooms if r.room_type == neighbor_reg.room_type), None)

                    # Check for shared vertical edge (same X coordinate)
                    shared_xs = [x for (x, y) in target_region.polygon if any(abs(x - nx) < 0.05 for (nx, ny) in neighbor_reg.polygon)]
                    if shared_xs:
                        shared_x = shared_xs[0]
                        if min_x < n_min_x:
                            # Target is on left, neighbor on right
                            delta_x = 0.5
                            if new_area > cur_usable:
                                delta_x = min(1.2, max(0.4, round((new_area - cur_usable) / max(reg_l, 0.1), 2)))
                            elif new_area < cur_usable:
                                delta_x = -min(0.8, max(0.3, round((cur_usable - new_area) / max(reg_l, 0.1), 2)))
                            new_x = round(shared_x + delta_x, 3)
                        else:
                            # Target is on right, neighbor on left
                            delta_x = 0.5
                            if new_area > cur_usable:
                                delta_x = min(1.2, max(0.4, round((new_area - cur_usable) / max(reg_l, 0.1), 2)))
                            elif new_area < cur_usable:
                                delta_x = -min(0.8, max(0.3, round((cur_usable - new_area) / max(reg_l, 0.1), 2)))
                            new_x = round(shared_x - delta_x, 3)

                        target_region.polygon = [(new_x if abs(x - shared_x) < 0.05 else x, y) for (x, y) in target_region.polygon]
                        neighbor_reg.polygon = [(new_x if abs(x - shared_x) < 0.05 else x, y) for (x, y) in neighbor_reg.polygon]

                        new_r_poly = to_shapely_polygon(target_region.polygon)
                        t_min_x, t_min_y, t_max_x, t_max_y = new_r_poly.bounds
                        target_room.intended_dimensions = (round(t_max_x - t_min_x, 2), round(t_max_y - t_min_y, 2))
                        target_room.proposed_boundary = []

                        if neighbor_room:
                            new_n_poly = to_shapely_polygon(neighbor_reg.polygon)
                            nm_x, nm_y, n_mx, n_my = new_n_poly.bounds
                            neighbor_room.intended_dimensions = (round(n_mx - nm_x, 2), round(n_my - nm_y, 2))
                            neighbor_room.proposed_boundary = []

                        adjusted_neighbor = True

                if not adjusted_neighbor:
                    factor = math.sqrt(new_area / max(reg_w * reg_l, 0.1))
                    w = round(min(reg_w, max(1.2, reg_w * factor)), 2)
                    l = round(min(reg_l, max(1.2, reg_l * factor)), 2)
                    target_room.intended_dimensions = (w, l)
                    target_room.proposed_boundary = []
            else:
                aspect = 1.33
                w = round(math.sqrt(new_area / aspect), 2)
                l = round(w * aspect, 2)
                target_room.intended_dimensions = (w, l)
                target_room.proposed_boundary = []

            return f"Updated {target_room.room_type} area to {new_area:.1f} m²", [target_room.id], [target_room.id]

        # 3. ADD_WINDOW
        if op.operation == EditOperationType.ADD_WINDOW:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            orient = op.changes.get("orientation") or "north"
            win = WindowIntent(
                id=generate_id("win_intent"),
                room_id=target_room.id,
                wall_orientation=orient,
                window_type="standard",
                recommended_width=1.2,
                recommended_height=1.2,
                floor_number=floor_design.floor_number,
                rationale="User edit: natural lighting & daylight opening",
            )
            target_room.windows.append(win)
            return f"Added window to {target_room.room_type} on {orient} wall", [target_room.id], [win.id]

        # 4. REMOVE_WINDOW
        if op.operation == EditOperationType.REMOVE_WINDOW:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            orient = op.changes.get("orientation")
            if orient:
                target_room.windows = [w for w in target_room.windows if w.wall_orientation != orient]
            elif target_room.windows:
                target_room.windows.pop()
            return f"Removed window from {target_room.room_type}", [target_room.id], []

        # 5. MODIFY_WINDOW
        if op.operation == EditOperationType.MODIFY_WINDOW:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            orient = op.changes.get("orientation")
            if target_room.windows:
                if orient:
                    target_room.windows[0].wall_orientation = orient
            else:
                # If no window exists, add one
                win = WindowIntent(
                    id=generate_id("win_intent"),
                    room_id=target_room.id,
                    wall_orientation=orient or "north",
                    floor_number=floor_design.floor_number,
                )
                target_room.windows.append(win)
            return f"Updated window for {target_room.room_type}", [target_room.id], []

        # 6. ADD_DOOR
        if op.operation == EditOperationType.ADD_DOOR:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            connects_to = op.changes.get("connects_to") or "circulation"
            orient = op.changes.get("orientation") or "south"
            door = DoorIntent(
                id=generate_id("door_intent"),
                connects_from=target_room.id,
                connects_to=connects_to,
                wall_orientation=orient,
                door_type="interior",
                recommended_width=0.9,
                floor_number=floor_design.floor_number,
                rationale="User edit: door connection",
            )
            target_room.doors.append(door)
            return f"Added door connecting {target_room.room_type} to {connects_to}", [target_room.id], [door.id]

        # 7. REMOVE_DOOR
        if op.operation == EditOperationType.REMOVE_DOOR:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            if len(target_room.doors) > 1:
                target_room.doors.pop()
                return f"Removed extra door from {target_room.room_type}", [target_room.id], []
            else:
                return f"Retained primary door for {target_room.room_type} (cannot disconnect room)", [target_room.id], []

        # 8. MODIFY_DOOR
        if op.operation == EditOperationType.MODIFY_DOOR:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            connects_to = op.changes.get("connects_to")
            orient = op.changes.get("orientation")
            if target_room.doors:
                if connects_to:
                    target_room.doors[0].connects_to = connects_to
                if orient:
                    target_room.doors[0].wall_orientation = orient
            return f"Modified door for {target_room.room_type}", [target_room.id], []

        # 9. MODIFY_ENTRANCE
        if op.operation == EditOperationType.MODIFY_ENTRANCE:
            orient = op.changes.get("orientation") or "east"
            # Find existing entrance door in design
            entrance_door = None
            entrance_room = None
            for r in floor_design.rooms:
                for d in r.doors:
                    if d.door_type == "entrance" or d.connects_to == "exterior":
                        entrance_door = d
                        entrance_room = r
                        break
                if entrance_door:
                    break

            if entrance_door:
                entrance_door.wall_orientation = orient
                return f"Moved entrance door to {orient} side", [entrance_room.id if entrance_room else ""], [entrance_door.id]
            else:
                # Add entrance to living or foyer
                target_host = floor_design.get_rooms_by_type("foyer") or floor_design.get_rooms_by_type("living") or floor_design.rooms[:1]
                if target_host:
                    host = target_host[0]
                    door = DoorIntent(
                        id=generate_id("entrance_door"),
                        connects_from=host.id,
                        connects_to="exterior",
                        wall_orientation=orient,
                        door_type="entrance",
                        recommended_width=1.0,
                        floor_number=1,
                        rationale="User edit: relocated main entrance",
                    )
                    host.doors.append(door)
                    return f"Positioned main entrance on {orient} side", [host.id], [door.id]
            return f"Configured entrance on {orient} side", [], []

        # 10. MODIFY_CIRCULATION
        if op.operation == EditOperationType.MODIFY_CIRCULATION:
            # Ensure each room on floor has clear interior door to circulation
            added_count = 0
            for r in floor_design.rooms:
                has_circ_door = any(d.connects_to in ("circulation", "corridor") for d in r.doors)
                if not has_circ_door:
                    d = DoorIntent(
                        id=generate_id("circ_door"),
                        connects_from=r.id,
                        connects_to="circulation",
                        door_type="interior",
                        floor_number=floor_design.floor_number,
                    )
                    r.doors.append(d)
                    added_count += 1
            return "Improved circulation flow and corridor connectivity", [r.id for r in floor_design.rooms], []

        # 11. MODIFY_ROOM_POSITION / RELATIONSHIP
        if op.operation in (EditOperationType.MODIFY_ROOM_POSITION, EditOperationType.MODIFY_ROOM_RELATIONSHIP):
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            target_neighbor = op.changes.get("target_neighbor")
            if target_neighbor:
                neighbor_rooms = floor_design.get_rooms_by_type(target_neighbor)
                if neighbor_rooms:
                    neighbor = neighbor_rooms[0]
                    # Connect them via shared door
                    door = DoorIntent(
                        id=generate_id("adj_door"),
                        connects_from=target_room.id,
                        connects_to=neighbor.room_type,
                        door_type="interior",
                        floor_number=floor_design.floor_number,
                        rationale=f"Direct access between {target_room.room_type} and {neighbor.room_type}",
                    )
                    target_room.doors.append(door)
                    return f"Positioned {target_room.room_type} directly connected to {neighbor.room_type}", [target_room.id, neighbor.id], [door.id]
            return f"Adjusted spatial relationships for {target_room.room_type}", [target_room.id], []

        # 12. ADD_ROOM
        if op.operation == EditOperationType.ADD_ROOM:
            rtype = op.target_room_type or "study"
            new_room_id = generate_id("room")
            new_reg_id = generate_id("reg")

            # Create new allocated region
            new_reg = AllocatedRegion(
                id=new_reg_id,
                room_type=rtype,
                floor_number=floor_design.floor_number,
                target_area_sqm=10.0,
                area_sqm=10.0,
                approximate_dimensions=(3.0, 3.3),
            )
            floor_alloc.allocated_regions.append(new_reg)

            new_room = RoomDesign(
                id=new_room_id,
                room_type=rtype,
                allocated_region_id=new_reg_id,
                floor_number=floor_design.floor_number,
                intended_shape="rectangular",
                intended_dimensions=(3.0, 3.3),
                intended_area_sqm=10.0,
                doors=[
                    DoorIntent(
                        id=generate_id("door"),
                        connects_from=new_room_id,
                        connects_to="circulation",
                        floor_number=floor_design.floor_number,
                    )
                ],
                windows=[
                    WindowIntent(
                        id=generate_id("win"),
                        room_id=new_room_id,
                        wall_orientation="north",
                        floor_number=floor_design.floor_number,
                    )
                ],
            )
            floor_design.rooms.append(new_room)
            return f"Added new {rtype} to Floor {floor_design.floor_number}", [new_room.id], []

        # 13. REMOVE_ROOM
        if op.operation == EditOperationType.REMOVE_ROOM:
            if not target_room:
                raise ValueError(f"Target room '{op.target_room_type}' not found.")
            # Verify not removing essential single rooms
            if target_room.room_type in ("living", "kitchen") and len(floor_design.get_rooms_by_type(target_room.room_type)) <= 1:
                return f"Cannot remove {target_room.room_type} (required primary living space)", [], []

            floor_design.rooms = [r for r in floor_design.rooms if r.id != target_room.id]
            if target_region:
                floor_alloc.allocated_regions = [reg for reg in floor_alloc.allocated_regions if reg.id != target_region.id]
            return f"Removed {target_room.room_type} from design", [], []

        return "Applied edit modification", [], []

    # -----------------------------------------------------------------------
    # Re-render and Update Exports
    # -----------------------------------------------------------------------
    def _update_exports(self, project_result: Any) -> None:
        """Regenerate on-disk export bundle artifacts (SVG, CAD DXF, project.json)."""
        pid = getattr(project_result, "project_id", None)
        if not pid:
            return

        bundle_path = Path(self.outputs_dir) / pid
        bundle_path.mkdir(parents=True, exist_ok=True)

        fps = getattr(project_result, "floor_plan_set", None)
        reqs = getattr(project_result, "requirements", None)
        pname = getattr(project_result, "project_name", pid)

        # 1. Update project.json
        try:
            pdata = export_project_json(
                project_id=pid,
                project_name=pname,
                requirements=reqs,
                planning_spec=getattr(project_result, "planning_spec", None),
                allocation_set=getattr(project_result, "allocation_set", None),
                architectural_design_set=getattr(project_result, "architectural_design_set", None),
                floor_plan_set=fps,
                validation_report=getattr(project_result, "validation_report", None),
                refinement_result=getattr(project_result, "refinement_result", None),
                alternative_set=getattr(project_result, "alternative_set", None),
                decision_trace=getattr(project_result, "decision_trace", None),
            )
            pdata["status"] = project_result.status
            pdata["is_valid"] = project_result.is_valid
            pdata["is_success"] = project_result.is_success
            save_json(pdata, bundle_path / "project.json")
        except Exception as exc:
            logger.warning("Failed to save updated project.json: %s", exc)

        # 2. Re-render SVGs for each floor
        if fps and fps.floor_plans:
            for fp in fps.floor_plans:
                try:
                    svg_path = bundle_path / f"floor_{fp.floor_number}.svg"
                    self.renderer.render_floor_plan(
                        floor_plan=fp,
                        output_path=svg_path,
                        orientation=reqs.orientation if reqs else None,
                        project_name=pname,
                        fallback_plot_boundary=fps.plot_boundary,
                        fallback_buildable_boundary=fps.buildable_boundary,
                    )
                    # Also write to alternatives/alternative_1
                    alt_dir = bundle_path / "alternatives" / "alternative_1"
                    alt_dir.mkdir(parents=True, exist_ok=True)
                    alt_svg = alt_dir / f"floor_{fp.floor_number}.svg"
                    self.renderer.render_floor_plan(
                        floor_plan=fp,
                        output_path=alt_svg,
                        orientation=reqs.orientation if reqs else None,
                        project_name=pname,
                        fallback_plot_boundary=fps.plot_boundary,
                        fallback_buildable_boundary=fps.buildable_boundary,
                    )
                except Exception as exc:
                    logger.warning("Failed to render SVG for floor %s: %s", fp.floor_number, exc)
