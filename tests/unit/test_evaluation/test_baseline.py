"""Unit tests for BaselineSpatialAllocator reference implementation."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.exceptions import InfeasibleAllocationError
from app.evaluation.baselines import BaselineSpatialAllocator


def test_baseline_allocator_single_floor():
    """Verify BaselineSpatialAllocator partitions buildable boundary for single floor."""
    req_agent = RequirementAgent()
    planning_agent = PlanningAgent()
    allocator = BaselineSpatialAllocator()

    brief = """
    Single floor residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 260 sq ft
    - 1 kitchen of 140 sq ft
    - 1 bedroom of 160 sq ft
    """

    reqs = req_agent.parse(brief)
    spec = planning_agent.plan(reqs)

    alloc_set = allocator.allocate(spec)

    assert len(alloc_set.allocations) == 1
    alloc = alloc_set.allocations[0]
    assert alloc.floor_number == 1
    assert len(alloc.allocated_regions) == 3
    assert alloc.total_area_sqm > 50.0

    # Verify all regions have non-empty polygons
    for r in alloc.allocated_regions:
        poly = Polygon(r.polygon)
        assert poly.is_valid
        assert poly.area > 5.0


def test_baseline_allocator_multi_floor_staircase():
    """Verify BaselineSpatialAllocator coordinates vertical staircase across floors."""
    req_agent = RequirementAgent()
    planning_agent = PlanningAgent()
    allocator = BaselineSpatialAllocator()

    brief = """
    Two floor residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 240 sq ft
    - 1 kitchen of 130 sq ft
    Floor 2:
    - 2 bedrooms of 160 sq ft each
    """

    reqs = req_agent.parse(brief)
    spec = planning_agent.plan(reqs)

    alloc_set = allocator.allocate(spec)

    assert len(alloc_set.allocations) == 2
    assert alloc_set.staircase_aligned is True

    # Check both floors have a staircase region
    f1_stairs = [r for r in alloc_set.allocations[0].allocated_regions if r.zone_type == "staircase"]
    f2_stairs = [r for r in alloc_set.allocations[1].allocated_regions if r.zone_type == "staircase"]

    assert len(f1_stairs) == 1
    assert len(f2_stairs) == 1
    assert f1_stairs[0].polygon == f2_stairs[0].polygon


def test_baseline_allocator_infeasible_deficit():
    """Verify BaselineSpatialAllocator raises InfeasibleAllocationError when space is insufficient."""
    req_agent = RequirementAgent()
    planning_agent = PlanningAgent()
    allocator = BaselineSpatialAllocator()

    brief = """
    Single floor residence on a 15 feet by 15 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 500 sq ft
    - 1 dining room of 300 sq ft
    """

    reqs = req_agent.parse(brief)
    spec = planning_agent.plan(reqs)

    with pytest.raises(InfeasibleAllocationError):
        allocator.allocate(spec)
