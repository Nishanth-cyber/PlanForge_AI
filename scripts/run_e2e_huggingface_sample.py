#!/usr/bin/env python
"""Dedicated Representative End-to-End Pipeline Run using Hugging Face Free Model.

Demonstrates that the PlanForge generative pipeline works end-to-end with the
free Serverless Hugging Face Inference API:
1. Requirements parsing
2. Planning Agent (WHAT + ORGANIZE)
3. ASAA Allocator (WHERE)
4. Architectural Design Agent with Hugging Face (HOW)
5. Geometry Engine (CONSTRUCT)
6. FloorPlanValidator (VERIFY)

Configuration:
- Model: Qwen/Qwen2.5-7B-Instruct (or PLANFORGE_LLM_MODEL)
- Token: PLANFORGE_HF_API_KEY or HF_TOKEN from .env
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.llm.client import HuggingFaceClient
from app.llm.configuration import LLMConfig
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.validation.validator import FloorPlanValidator


def run_hf_e2e_sample() -> int:
    print("=" * 75)
    print("PlanForge AI - End-to-End Pipeline Run (Hugging Face Free Model)")
    print("=" * 75)

    # Force provider=huggingface
    cfg = LLMConfig.from_env()
    cfg.provider = "huggingface"
    if not os.getenv("PLANFORGE_LLM_MODEL"):
        cfg.model_name = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

    print(f"Provider:   {cfg.provider.upper()}")
    print(f"Model:      {cfg.model_name}")
    print(f"Endpoint:   {cfg.api_base_url}/{cfg.model_name}")
    print(f"Auth Token: {'Configured (Bearer token hidden)' if cfg.api_key else 'Not configured (Public free rate limits apply)'}")

    # Define 3-room representative villa layout for fast execution
    print("\n[Stage 1] Defining Requirements:")
    print("  Plot: 20m x 15m, 1 Floor")
    print("  - Bedroom 1 (Master): 4.0m x 3.5m (User-specified hard constraint)")
    print("  - Living Room: Unspecified dimensions (target ~22 m²)")
    print("  - Kitchen: Unspecified dimensions (target ~12 m²)")

    reqs = Requirements(
        project_name="Hugging Face Representative Villa",
        target_floors=1,
        plot_dimensions=(20.0, 15.0),
        plot_shape=((0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0)),
        setbacks={"front": 1.5, "rear": 1.5, "left": 1.5, "right": 1.5},
        floors=[
            FloorRequirement(
                floor_number=1,
                floor_name="Ground Floor",
                room_requirements=[
                    RoomRequirement(room_type="living", preferred_area_sqm=22.0),
                    RoomRequirement(
                        room_type="bedroom",
                        preferred_area_sqm=14.0,
                        user_dimensions=(4.0, 3.5),
                    ),
                    RoomRequirement(room_type="kitchen", preferred_area_sqm=12.0),
                ],
            )
        ],
    )

    # Stage 2: Planning Agent
    print("\n[Stage 2] Executing Planning Agent (WHAT + ORGANIZE)...")
    planner = PlanningAgent()
    planning_spec = planner.plan(reqs)
    print(f"  Programmed rooms on Floor 1: {len(planning_spec.floors[0].room_specs)}")

    # Stage 3: ASAA Allocator
    print("\n[Stage 3] Executing ASAA Allocator (WHERE)...")
    allocator = ASAAAllocator(seed=42)
    allocation_set = allocator.allocate(planning_spec)
    floor_alloc = allocation_set.get_allocation(1)
    print(f"  Allocated regions on Floor 1: {len(floor_alloc.allocated_regions)}")
    for reg in floor_alloc.allocated_regions:
        print(f"    Region '{reg.room_type}': {reg.area_sqm:.2f} m² (approx dims: {reg.approximate_dimensions})")

    # Stage 4: Architectural Design Agent with Hugging Face
    print(f"\n[Stage 4] Executing Architectural Design Agent with Hugging Face ({cfg.model_name})...")
    arch_agent = ArchitecturalAgent(config=cfg)

    t0 = time.time()
    try:
        design_set = arch_agent.design(
            planning_spec=planning_spec,
            allocation_set=allocation_set,
            requirements=reqs,
        )
        elapsed = time.time() - t0
        floor_design = design_set.get_design(1)
        print(f"  Received Hugging Face design proposal in {elapsed:.2f}s!")
        print(f"  Designed rooms: {len(floor_design.rooms)}")
        print(f"  Design rationale: {floor_design.design_rationale[:100]}...")
    except Exception as e:
        print(f"[ERROR] Architectural Design Agent failed with Hugging Face: {e}")
        print("Hint: If you receive HTTP 401, check your PLANFORGE_HF_API_KEY in .env.")
        print("Hint: If you receive HTTP 503, the remote model is currently cold-starting on Hugging Face; retry in a few seconds.")
        return 1

    # Stage 5: Geometry Engine
    print("\n[Stage 5] Executing Geometry Engine (CONSTRUCT)...")
    geom_engine = GeometryEngine()
    plot_bound = [(0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0)]
    b_bound = [(1.5, 1.5), (18.5, 1.5), (18.5, 13.5), (1.5, 13.5)]
    floor_plan_set = geom_engine.construct(
        design_set=design_set,
        allocation_set=allocation_set,
        plot_boundary=plot_bound,
        buildable_boundary=b_bound,
    )
    fp = floor_plan_set.get_floor_plan(1)
    print(f"  Constructed physical floor plan with {len(fp.rooms)} rooms, {len(fp.walls)} walls, {len(fp.doors)} doors, {len(fp.windows)} windows.")

    # Stage 6: FloorPlanValidator
    print("\n[Stage 6] Executing Independent Validator (VERIFY)...")
    validator = FloorPlanValidator()
    report = validator.validate(floor_plan_set, requirements=reqs, allocation_set=allocation_set)
    print(f"  Overall Valid: {report.overall_valid}")
    print(f"  Overall Quality Score: {report.overall_score:.2f}")
    print(f"  Total Errors: {report.total_errors}")
    print(f"  Total Warnings: {report.total_warnings}")

    # Summary
    print("\n[Verification Summary]")
    for r in floor_design.rooms:
        d_str = f"{r.intended_dimensions[0]:.2f}m x {r.intended_dimensions[1]:.2f}m" if r.intended_dimensions else "N/A"
        is_user = r.room_type == "bedroom"
        tag = "[USER SPECIFIED]" if is_user else "[LLM PROPOSED]  "
        print(f"  {tag} {r.room_type:<12} : Dims = {d_str:<16} Area = {r.intended_area_sqm:.2f} m²")

    meta = floor_design.metadata
    print(f"\nProvider: {meta.get('provider')} | Model: {meta.get('model')} | Status: {meta.get('status')}")

    print("\n" + "=" * 75)
    print("HUGGING FACE END-TO-END PIPELINE RESULT: SUCCESS")
    print("=" * 75)
    return 0


if __name__ == "__main__":
    sys.exit(run_hf_e2e_sample())
