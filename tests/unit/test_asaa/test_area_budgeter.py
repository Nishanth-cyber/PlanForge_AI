"""Unit tests for ASAA area budgeting and infeasibility detection."""

import pytest
from app.asaa.area_budgeter import AreaBudgeter
from app.asaa.exceptions import InfeasibleAllocationError
from app.models.planning import RoomSpec


def test_proportional_area_budgeting():
    """Test proportional area distribution matching target areas."""
    r1 = RoomSpec(room_type="living", target_area_sqm=25.0, priority="high")
    r2 = RoomSpec(room_type="kitchen", target_area_sqm=12.0, priority="normal")
    r3 = RoomSpec(room_type="bedroom", target_area_sqm=16.0, priority="normal")

    budget = AreaBudgeter.compute_budget(
        buildable_area_sqm=100.0,
        room_specs=[r1, r2, r3],
        floor_number=1,
        circulation_ratio=0.12,
    )

    assert budget.buildable_area_sqm == 100.0
    assert budget.circulation_area_sqm >= 10.0
    # All rooms allocated
    assert r1.id in budget.room_budgets
    assert r2.id in budget.room_budgets
    assert r3.id in budget.room_budgets
    # High priority living room receives close to or exceeding target
    assert budget.room_budgets[r1.id] >= 20.0
    assert budget.total_allocated_rooms_sqm + budget.circulation_area_sqm <= 100.01


def test_minimum_area_enforced_strictly():
    """Test that explicit min_area_sqm is never reduced."""
    r1 = RoomSpec(room_type="master_bedroom", target_area_sqm=20.0, min_area_sqm=18.0)
    r2 = RoomSpec(room_type="bathroom", target_area_sqm=6.0, min_area_sqm=5.0)

    # Tight buildable space: 30 sqm
    budget = AreaBudgeter.compute_budget(
        buildable_area_sqm=30.0,
        room_specs=[r1, r2],
        floor_number=1,
    )
    # Master bedroom must receive at least 18.0, bathroom at least 5.0
    assert budget.room_budgets[r1.id] >= 18.0
    assert budget.room_budgets[r2.id] >= 5.0


def test_maximum_area_capping():
    """Test that max_area_sqm caps surplus area allocation."""
    r1 = RoomSpec(room_type="study", target_area_sqm=10.0, max_area_sqm=12.0)
    # Very large space: 200 sqm
    budget = AreaBudgeter.compute_budget(
        buildable_area_sqm=200.0,
        room_specs=[r1],
        floor_number=1,
    )
    assert budget.room_budgets[r1.id] <= 12.01


def test_infeasible_area_raises_exception_with_deficit():
    """Test that impossible room requests raise InfeasibleAllocationError with details."""
    # 3 bedrooms needing 20m² min each = 60m², but buildable area is only 40m²
    r1 = RoomSpec(room_type="bedroom_1", target_area_sqm=25.0, min_area_sqm=20.0)
    r2 = RoomSpec(room_type="bedroom_2", target_area_sqm=25.0, min_area_sqm=20.0)
    r3 = RoomSpec(room_type="bedroom_3", target_area_sqm=25.0, min_area_sqm=20.0)

    with pytest.raises(InfeasibleAllocationError) as exc_info:
        AreaBudgeter.compute_budget(
            buildable_area_sqm=40.0,
            room_specs=[r1, r2, r3],
            floor_number=1,
        )

    err = exc_info.value
    assert err.available_area_sqm == 40.0
    assert err.requested_min_area_sqm == 60.0
    assert err.deficit_sqm == 20.0
    assert len(err.offending_rooms) == 3
    assert err.floor_number == 1


def test_staircase_reservation_subtracted():
    """Test that multi-floor staircase allowance is reserved from available room area."""
    r1 = RoomSpec(room_type="living", target_area_sqm=30.0, min_area_sqm=25.0)

    budget = AreaBudgeter.compute_budget(
        buildable_area_sqm=50.0,
        room_specs=[r1],
        has_staircase=True,
        staircase_area_sqm=8.0,
    )
    assert budget.staircase_area_sqm == 8.0
    assert budget.total_allocated_rooms_sqm + budget.staircase_area_sqm + budget.circulation_area_sqm <= 50.01
