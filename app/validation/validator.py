"""FloorPlanValidator coordinator for independent deterministic verification.

Orchestrates all specialized validators across structural completeness, boundary containment,
ASAA allocation compliance, room geometry, overlap prevention, relationships, doors, windows,
staircases, and BFS door-graph connectivity.
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.validation.boundary_validator import BoundaryValidator
from app.validation.circulation_validator import CirculationValidator
from app.validation.connectivity_validator import ConnectivityValidator
from app.validation.dimension_validator import DimensionValidator
from app.validation.door_validator import DoorValidator
from app.validation.overlap_validator import OverlapValidator
from app.validation.relationship_validator import RelationshipValidator
from app.validation.room_validator import RoomValidator
from app.validation.staircase_validator import StaircaseValidator
from app.validation.window_validator import WindowValidator

Point2D = Tuple[float, float]

# Comprehensive set of evaluated categories
EVALUATED_CATEGORIES = [
    "boundary",
    "overlap",
    "completeness",
    "room_geometry",
    "allocation",
    "dimension",
    "relationship",
    "door",
    "window",
    "staircase",
    "connectivity",
    "circulation",
    "multi_floor",
]


class FloorPlanValidator:
    """Independent deterministic verification coordinator for PlanForge AI floor plans."""

    def __init__(
        self,
        boundary_tolerance: float = 0.05,
        max_overlap_sqm: float = 0.05,
        min_shared_boundary_m: float = 0.3,
    ):
        """Initialize FloorPlanValidator with specialized component validators."""
        self.boundary_validator = BoundaryValidator(tolerance=boundary_tolerance)
        self.overlap_validator = OverlapValidator(max_allowed_overlap_sqm=max_overlap_sqm)
        self.room_validator = RoomValidator(containment_tolerance=boundary_tolerance)
        self.dimension_validator = DimensionValidator()
        self.relationship_validator = RelationshipValidator(min_shared_boundary_m=min_shared_boundary_m)
        self.door_validator = DoorValidator()
        self.window_validator = WindowValidator()
        self.staircase_validator = StaircaseValidator()
        self.connectivity_validator = ConnectivityValidator()
        self.circulation_validator = CirculationValidator()

    def validate_floor(
        self,
        floor_plan: FloorPlan,
        requirements: Optional[Requirements] = None,
        planning_spec: Optional[PlanningSpec] = None,
        allocation_set: Optional[AllocationSet] = None,
        architectural_design_set: Optional[ArchitecturalDesignSet] = None,
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
    ) -> ValidationResult:
        """Validate a single FloorPlan independently.

        Args:
            floor_plan: Constructed FloorPlan to inspect.
            requirements: Upstream Requirements.
            planning_spec: Upstream PlanningSpec.
            allocation_set: Upstream AllocationSet.
            architectural_design_set: Upstream ArchitecturalDesignSet.
            plot_boundary: Property plot boundary.
            buildable_boundary: Setback-adjusted buildable envelope.

        Returns:
            ValidationResult containing all issues and pass/fail category breakdown.
        """
        geometry = floor_plan.geometry
        floor_num = floor_plan.floor_number

        result = ValidationResult(
            floor_number=floor_num,
            is_valid=True,
            score=100.0,
        )

        if not geometry:
            result.add_issue(
                ValidationIssue(
                    severity="error",
                    category="completeness",
                    check="missing_geometry",
                    message=f"FloorPlan for Floor {floor_num} has no constructed Geometry",
                    floor_number=floor_num,
                )
            )
            floor_plan.validation = result
            floor_plan.is_valid = False
            return result

        # Resolve floor-specific contexts
        floor_reqs = requirements.get_floor_requirements(floor_num) if requirements else None
        floor_plan_spec = planning_spec.get_floor_spec(floor_num) if planning_spec else None
        allocation = allocation_set.get_allocation(floor_num) if allocation_set else None
        floor_design = architectural_design_set.get_design(floor_num) if architectural_design_set else None

        plot_coords = plot_boundary or geometry.plot_polygon
        buildable_coords = buildable_boundary or geometry.buildable_polygon

        if not plot_coords and requirements:
            if requirements.plot_shape:
                plot_coords = list(requirements.plot_shape)
            elif requirements.plot_dimensions:
                w, d = requirements.plot_dimensions
                plot_coords = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]

        if not buildable_coords and requirements:
            sb = requirements.setbacks or {}
            front = sb.get("front", 0.0)
            rear = sb.get("rear", 0.0)
            left = sb.get("left", 0.0)
            right = sb.get("right", 0.0)
            if requirements.plot_dimensions:
                w, d = requirements.plot_dimensions
                min_x = left
                max_x = w - right
                min_y = front
                max_y = d - rear
                if max_x > min_x and max_y > min_y:
                    buildable_coords = [
                        (min_x, min_y),
                        (max_x, min_y),
                        (max_x, max_y),
                        (min_x, max_y),
                    ]

        is_stair_req = False
        if requirements and (requirements.target_floors or 0) >= 2:
            is_stair_req = True
        elif floor_plan_spec and floor_plan_spec.staircase_intent and floor_plan_spec.staircase_intent.get("required"):
            is_stair_req = True

        # 1. Boundary Validation (Check Group 2)
        for issue in self.boundary_validator.validate(geometry, plot_coords, buildable_coords):
            result.add_issue(issue)

        # 2. Overlap Validation (Check Group 5)
        for issue in self.overlap_validator.validate(geometry):
            result.add_issue(issue)

        # 3. Room Completeness, Allocation Containment & Topology (Check Groups 1, 3, 4, 18)
        for issue in self.room_validator.validate_floor(
            geometry=geometry,
            floor_reqs=floor_reqs,
            floor_plan_spec=floor_plan_spec,
            allocation=allocation,
            floor_design=floor_design,
        ):
            result.add_issue(issue)

        # 4. Usable Dimensions & Areas (Check Group 4)
        for issue in self.dimension_validator.validate(
            geometry=geometry,
            floor_plan_spec=floor_plan_spec,
            floor_reqs=floor_reqs,
        ):
            result.add_issue(issue)

        # 5. Spatial Relationships: Required/Preferred Adjacency, Separation, Suites (Check Groups 6, 7, 8, 9)
        for issue in self.relationship_validator.validate(
            geometry=geometry,
            floor_plan_spec=floor_plan_spec,
            floor_reqs=floor_reqs,
        ):
            result.add_issue(issue)

        # 6. Physical Doors & Swing Geometry (Check Groups 10, 11)
        for issue in self.door_validator.validate(geometry, buildable_coords):
            result.add_issue(issue)

        # 7. Physical Windows & Orientations (Check Group 12)
        for issue in self.window_validator.validate(geometry, floor_design):
            result.add_issue(issue)

        # 8. Staircase Geometry & Allocation (Check Group 13)
        for issue in self.staircase_validator.validate_floor(
            geometry=geometry,
            allocation=allocation,
            is_staircase_required=is_stair_req,
        ):
            result.add_issue(issue)

        # 9. Connectivity & Reachability (Check Group 14)
        for issue in self.connectivity_validator.validate(geometry):
            result.add_issue(issue)

        # 10. Corridor Network (Check Group 14)
        for issue in self.circulation_validator.validate_corridors(geometry):
            result.add_issue(issue)

        # Record passed checks for categories with zero errors
        for cat in EVALUATED_CATEGORIES:
            if cat not in result.checks_failed:
                result.record_passed_check(cat)

        # Calculate explainable score: 100 base, -15 per error, -3 per warning
        score = max(0.0, 100.0 - (15.0 * result.error_count) - (3.0 * result.warning_count))
        result.score = round(score, 1)

        # Update FloorPlan object state
        floor_plan.validation = result
        floor_plan.is_valid = result.is_valid

        return result

    def validate(
        self,
        floor_plan_set: FloorPlanSet,
        requirements: Optional[Requirements] = None,
        planning_spec: Optional[PlanningSpec] = None,
        allocation_set: Optional[AllocationSet] = None,
        architectural_design_set: Optional[ArchitecturalDesignSet] = None,
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
        iteration: int = 0,
    ) -> ValidationReport:
        """Validate complete multi-floor FloorPlanSet independently.

        Args:
            floor_plan_set: Complete FloorPlanSet to inspect.
            requirements: Upstream Requirements.
            planning_spec: Upstream PlanningSpec.
            allocation_set: Upstream AllocationSet.
            architectural_design_set: Upstream ArchitecturalDesignSet.
            plot_boundary: Plot boundary coordinates.
            buildable_boundary: Buildable envelope coordinates.
            iteration: Current refinement iteration index.

        Returns:
            Authoritative ValidationReport across all floors.
        """
        report = ValidationReport(iteration=iteration)

        plot_coords = plot_boundary or (floor_plan_set.plot_boundary if floor_plan_set.plot_boundary else None)
        buildable_coords = buildable_boundary or (floor_plan_set.buildable_boundary if floor_plan_set.buildable_boundary else None)

        if not plot_coords and requirements:
            if requirements.plot_shape:
                plot_coords = list(requirements.plot_shape)
            elif requirements.plot_dimensions:
                w, d = requirements.plot_dimensions
                plot_coords = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]

        if not buildable_coords and requirements:
            sb = requirements.setbacks or {}
            front = sb.get("front", 0.0)
            rear = sb.get("rear", 0.0)
            left = sb.get("left", 0.0)
            right = sb.get("right", 0.0)
            if requirements.plot_dimensions:
                w, d = requirements.plot_dimensions
                min_x = left
                max_x = w - right
                min_y = front
                max_y = d - rear
                if max_x > min_x and max_y > min_y:
                    buildable_coords = [
                        (min_x, min_y),
                        (max_x, min_y),
                        (max_x, max_y),
                        (min_x, max_y),
                    ]

        # 1. Validate each floor independently
        for fp in sorted(floor_plan_set.floor_plans, key=lambda f: f.floor_number):
            floor_result = self.validate_floor(
                floor_plan=fp,
                requirements=requirements,
                planning_spec=planning_spec,
                allocation_set=allocation_set,
                architectural_design_set=architectural_design_set,
                plot_boundary=plot_coords,
                buildable_boundary=buildable_coords,
            )
            report.results.append(floor_result)

        # 2. Multi-Floor Vertical Core Alignment (Check Group 13 & 15)
        stair_alignment_issues = self.staircase_validator.validate_multi_floor_alignment(floor_plan_set)
        for issue in stair_alignment_issues:
            # Assign to target floor result
            target_res = report.get_result(issue.floor_number)
            if target_res:
                target_res.add_issue(issue)
            elif report.results:
                report.results[0].add_issue(issue)

        # 3. Multi-Floor Consistency (Check Group 15)
        multi_floor_issues = self.circulation_validator.validate_multi_floor_consistency(
            floor_plan_set=floor_plan_set,
            requirements=requirements,
        )
        for issue in multi_floor_issues:
            if report.results:
                report.results[0].add_issue(issue)

        # Update FloorPlanSet validation report
        floor_plan_set.validation_report = report

        return report


# Authoritative alias
Validator = FloorPlanValidator
