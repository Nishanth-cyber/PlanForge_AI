"""Integration tests for Phase 11 Export & Rendering Pipeline.

Verifies end-to-end execution:
User Brief -> Requirement -> Planning -> ASAA -> Architectural LLM ->
Geometry Engine -> Independent Validator -> Multi-Design Generator ->
Decision Trace -> Floor Plan Renderer -> Bundle Exporter -> Integrity Verification.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.diversity_agent import MultiDesignGenerator
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.explainability.builder import DecisionTraceBuilder
from app.export.bundle_exporter import export_project_bundle
from app.export.integrity import verify_export_integrity
from app.geometry.engine import GeometryEngine
from app.rendering.floor_renderer import FloorPlanRenderer
from app.rendering.options import RenderOptions
from app.validation.validator import FloorPlanValidator


PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def test_end_to_end_single_floor_bundle(tmp_path: Path):
    """Verify end-to-end pipeline export of a single floor project with full decision trace."""
    brief = """
    Single floor modern home on a 40 feet by 50 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    - 1 kitchen of 150 sq ft
    - 1 master bedroom of 200 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Pipeline Single Floor")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    arch_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        strategy="social_centric",
    )

    geom_engine = GeometryEngine()
    floor_plans = geom_engine.construct(arch_set, allocation_set)

    validator = FloorPlanValidator()
    val_rep = validator.validate(floor_plans, reqs, planning_spec, allocation_set, arch_set)

    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=arch_set,
        geometry_set=floor_plans,
        validation_report=val_rep,
        project_name="Pipeline Single Floor",
    )

    out_dir = tmp_path / "exports"
    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_single_e2e",
        project_name="Pipeline Single Floor",
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=arch_set,
        floor_plan_set=floor_plans,
        validation_report=val_rep,
        decision_trace=trace,
        render_options=RenderOptions(dpi=100),
        create_zip=False,
    )

    # 1. Structural file checks
    assert bundle_path.exists()
    assert (bundle_path / "project.json").is_file()
    assert (bundle_path / "summary.md").is_file()
    assert (bundle_path / "decision_trace.json").is_file()
    assert (bundle_path / "explanations" / "project_summary.md").is_file()

    # Verify room explanations generated
    exp_rooms = list((bundle_path / "explanations" / "rooms").glob("*.md"))
    assert len(exp_rooms) >= 3

    # Verify rendered floor image exists under floors/
    floor1_png = bundle_path / "floors" / "floor_1.png"
    assert floor1_png.is_file()
    with open(floor1_png, "rb") as f:
        header = f.read(8)
        assert header == PNG_HEADER, "Output file is not a valid PNG image"

    # 2. Integrity Verification
    integrity = verify_export_integrity(bundle_path, check_trace=True)
    assert integrity.is_valid is True
    assert len(integrity.errors) == 0

    # 3. ID Preservation in exported JSON
    with open(bundle_path / "project.json", "r", encoding="utf-8") as f:
        pdata = json.load(f)

    assert pdata["project_id"] == "proj_single_e2e"
    # Ensure all planned room IDs are traceable in exported geometry
    exported_rooms = pdata["floor_plan_set"]["floor_plans"][0]["geometry"]["rooms"]
    exported_arch_ids = {r["architectural_room_id"] for r in exported_rooms if r.get("architectural_room_id")}
    rd_to_alloc = {
        rd["id"]: rd.get("allocated_region_id")
        for rd in pdata["architectural_design_set"]["designs"][0]["rooms"]
    }
    alloc_to_spec = {
        ar["id"]: ar.get("room_spec_id")
        for ar in pdata["allocation_set"]["allocations"][0]["allocated_regions"]
    }
    linked_spec_ids = {
        alloc_to_spec.get(rd_to_alloc.get(r["architectural_room_id"]))
        for r in exported_rooms if r.get("architectural_room_id")
    }
    for r_spec in planning_spec.floors[0].room_specs:
        assert r_spec.id in linked_spec_ids


def test_end_to_end_multi_design_alternatives_bundle(tmp_path: Path):
    """Verify end-to-end export of multi-design alternatives with neutral presentation and ZIP archive."""
    brief = """
    Single floor home on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 280 sq ft
    - 1 dining room of 140 sq ft
    - 1 kitchen of 120 sq ft
    - 1 bedroom of 180 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Multi-Design Villa")
    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)
    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    generator = MultiDesignGenerator()
    alt_set = generator.generate(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
        num_alternatives=2,
        candidate_budget=4,
        minimum_diversity_distance=0.15,
        project_name="Multi-Design Villa",
    )
    assert len(alt_set.alternatives) == 2

    # Build trace covering alternatives
    primary = alt_set.alternatives[0]
    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=primary.architectural_design,
        geometry_set=primary.floor_plan_set,
        validation_report=primary.validation_report,
        alternative_set=alt_set,
        project_name="Multi-Design Villa",
    )

    out_dir = tmp_path / "exports_multi"
    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_multi_e2e",
        project_name="Multi-Design Villa",
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=primary.architectural_design,
        floor_plan_set=primary.floor_plan_set,
        validation_report=primary.validation_report,
        alternative_set=alt_set,
        decision_trace=trace,
        render_options=RenderOptions(dpi=100),
        create_zip=True,
    )

    # 1. Verify per-alternative directory layout
    alt1_dir = bundle_path / "alternatives" / "alternative_1"
    alt2_dir = bundle_path / "alternatives" / "alternative_2"

    assert alt1_dir.is_dir()
    assert alt2_dir.is_dir()
    assert (alt1_dir / "floor_1.png").is_file()
    assert (alt2_dir / "floor_1.png").is_file()
    assert (alt1_dir / "design.json").is_file()
    assert (alt2_dir / "design.json").is_file()
    assert (alt1_dir / "explanation.md").is_file()
    assert (alt2_dir / "explanation.md").is_file()

    # 2. Verify neutral presentation (no "winner" or "best design")
    summary_text = (bundle_path / "summary.md").read_text(encoding="utf-8").lower()
    assert "best design" not in summary_text
    assert "winner" not in summary_text
    assert "optimal alternative" not in summary_text

    # 3. Verify ZIP archive exists and is valid
    zip_path = out_dir / "proj_multi_e2e.zip"
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert any("alternative_1/floor_1.png" in name for name in namelist)
        assert any("alternative_2/floor_1.png" in name for name in namelist)
        assert any("project.json" in name for name in namelist)

    # 4. Verify export integrity
    integrity = verify_export_integrity(bundle_path, expected_alternatives=2, check_trace=True)
    assert integrity.is_valid is True
    assert len(integrity.errors) == 0


def test_end_to_end_publication_mode_rendering(tmp_path: Path):
    """Verify publication mode rendering produces high quality monochrome floor plans."""
    brief = """
    Single floor residence on a 40 feet by 50 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 260 sq ft
    - 1 kitchen of 120 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Publication Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    arch_set = arch_agent.design(planning_spec=planning_spec, allocation_set=allocation_set)

    geom_engine = GeometryEngine()
    floor_plans = geom_engine.construct(arch_set, allocation_set)

    renderer = FloorPlanRenderer()
    out_dir = tmp_path / "pub_render"
    pub_options = RenderOptions(
        dpi=150,
        publication_mode=True,
        show_dimensions=True,
        show_room_areas=True,
    )

    rendered_floors = renderer.render_floor_plan_set(
        floor_plan_set=floor_plans,
        output_dir=out_dir,
        options=pub_options,
        orientation=reqs.orientation,
        project_name="Publication Mode Test",
    )

    assert len(rendered_floors) == 1
    rf = rendered_floors[0]
    assert rf.image_path.exists()
    assert rf.image_path.stat().st_size > 1000
    assert rf.rendered_room_count >= 2
    assert rf.width_px > 0 and rf.height_px > 0
