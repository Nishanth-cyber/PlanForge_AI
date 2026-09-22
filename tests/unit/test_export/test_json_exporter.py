"""Unit tests for structured JSON export and ID preservation."""

import copy
import json
from pathlib import Path
import pytest

from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.models.planning import PlanningSpec, FloorPlanSpec, RoomSpec
from app.models.allocation import AllocationSet, Allocation, AllocatedRegion
from app.models.architectural_design import ArchitecturalDesignSet, ArchitecturalDesign, RoomDesign
from app.models.floor_plan import FloorPlanSet, FloorPlan
from app.models.geometry import Geometry, GeoRoom, GeoWall
from app.models.validation import ValidationReport, ValidationResult, ValidationIssue
from app.models.refinement import RefinementResult, RefinementChange, RefinementStatus
from app.models.alternatives import DesignAlternative, DesignAlternativeSet, DesignStrategy, AlternativeStatus
from app.explainability.models import DecisionTrace, DecisionEvent, StageName, DecisionType
from app.export.errors import InvalidExportInputError
from app.export.json_exporter import export_project_json, export_alternative_json, save_json


def test_json_export_with_full_id_preservation(tmp_path: Path):
    """Verify that export_project_json preserves every identifier across the pipeline."""
    req = Requirements(
        id="req_proj_1",
        project_name="ID Preservation Test",
        plot_dimensions=(15.0, 20.0),
        floors=[
            FloorRequirement(
                id="freq_1",
                floor_number=1,
                room_requirements=[RoomRequirement(id="rreq_living", room_type="living", target_area_sqm=30.0)],
            )
        ],
    )
    plan = PlanningSpec(
        id="plan_1",
        floors=[
            FloorPlanSpec(
                id="fplan_1",
                floor_number=1,
                room_specs=[RoomSpec(id="rspec_living", room_type="living", target_area_sqm=30.0, source_requirement_id="rreq_living")],
            )
        ],
    )
    alloc = AllocationSet(
        id="alloc_set_1",
        allocations=[
            Allocation(
                id="alloc_1",
                floor_number=1,
                allocated_regions=[AllocatedRegion(id="region_living", room_type="living", room_spec_id="rspec_living", area_sqm=32.0)],
            )
        ],
    )
    arch = ArchitecturalDesignSet(
        id="arch_set_1",
        designs=[
            ArchitecturalDesign(
                id="arch_d_1",
                floor_number=1,
                rooms=[RoomDesign(id="room_design_living", room_type="living", allocated_region_id="region_living")],
            )
        ],
    )
    geom = Geometry(
        id="geom_1",
        floor_number=1,
        rooms=[GeoRoom(id="georoom_living", room_type="living", architectural_room_id="room_design_living", area_sqm=31.5)],
    )
    fps = FloorPlanSet(
        id="fps_1",
        floor_plans=[FloorPlan(id="fp_1", floor_number=1, geometry=geom, is_valid=True)],
    )
    val = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                issues=[ValidationIssue(check="R_TEST", message="Test pass", severity="info", target_id="georoom_living")],
            )
        ],
    )
    ref = RefinementResult(
        id="ref_res_1",
        status=RefinementStatus.VALID_ON_INITIAL_PASS,
        changes=[RefinementChange(id="chg_1", room_id="room_design_living", field_changed="doors", validation_issue_ids=["issue_1"])],
    )
    alt = DesignAlternative(
        alternative_id="alt_01",
        index=1,
        strategy=DesignStrategy.SOCIAL_CENTRIC.value,
        status=AlternativeStatus.VALIDATED,
        diversity_scores={"alt_02": 0.42},
    )
    alt_set = DesignAlternativeSet(
        id="alt_set_1",
        alternatives=[alt],
    )
    trace = DecisionTrace(
        trace_id="trace_01",
        stages=[],
    )

    data = export_project_json(
        project_id="proj_preserve",
        requirements=req,
        planning_spec=plan,
        allocation_set=alloc,
        architectural_design_set=arch,
        floor_plan_set=fps,
        validation_report=val,
        refinement_result=ref,
        alternative_set=alt_set,
        decision_trace=trace,
    )

    # Convert to JSON string and verify all IDs are strictly present
    json_str = json.dumps(data)
    assert "req_proj_1" in json_str
    assert "rreq_living" in json_str
    assert "rspec_living" in json_str
    assert "region_living" in json_str
    assert "room_design_living" in json_str
    assert "georoom_living" in json_str
    assert "chg_1" in json_str
    assert "alt_01" in json_str
    assert "trace_01" in json_str

    # Save and reload
    out_file = tmp_path / "project.json"
    saved_path = save_json(data, out_file)
    assert saved_path.exists()

    with open(saved_path, "r", encoding="utf-8") as f:
        reloaded = json.load(f)
    assert reloaded["project_metadata"]["project_id"] == "proj_preserve"


def test_alternative_json_export():
    """Verify single alternative JSON serialization."""
    alt = DesignAlternative(
        alternative_id="alt_test",
        index=2,
        strategy="corridor_centric",
        status=AlternativeStatus.VALIDATED,
        characteristics=["central circulation"],
        diversity_scores={"alt_1": 0.35},
    )
    data = export_alternative_json(alt)
    assert data["alternative_id"] == "alt_test"
    assert data["index"] == 2
    assert data["strategy"] == "corridor_centric"
    assert data["status"] == "validated"
    assert data["is_valid"] is True
    assert data["diversity_scores"] == {"alt_1": 0.35}


def test_missing_optional_fields_handling():
    """Verify clean serialization when optional pipeline stages are omitted."""
    req = Requirements(id="req_only", project_name="Minimal Project")
    data = export_project_json(project_id="p_min", requirements=req)

    assert data["project_metadata"]["project_id"] == "p_min"
    assert "requirements" in data
    assert "planning_spec" not in data
    assert "allocation_set" not in data


def test_export_immutability():
    """Verify that exporting never mutates input objects."""
    req = Requirements(id="req_immut", project_name="Immutable")
    req_copy = copy.deepcopy(req)

    export_project_json(project_id="p_immut", requirements=req)

    assert req.id == req_copy.id
    assert req.project_name == req_copy.project_name


def test_invalid_export_input_error():
    """Verify that export_alternative_json raises InvalidExportInputError on None."""
    with pytest.raises(InvalidExportInputError):
        export_alternative_json(None)  # type: ignore
