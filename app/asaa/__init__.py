"""ASAA (Adaptive Space Allocation Algorithm) package."""

from app.asaa.allocator import ASAAAllocator
from app.asaa.area_budgeter import AreaBudgeter, FloorBudget
from app.asaa.boundary import BuildableBoundary, BuildableBoundaryCalculator
from app.asaa.candidate_generator import CandidateAllocation, CandidateGenerator
from app.asaa.exceptions import BoundaryConstraintError, InfeasibleAllocationError
from app.asaa.refiner import AdaptiveRefiner
from app.asaa.scoring import (
    CandidateScorer,
    calculate_adjacency_score,
    score_allocation,
    score_region,
)
from app.asaa.spatial_partitioner import PartitionItem, SpatialPartitioner

__all__ = [
    "ASAAAllocator",
    "AreaBudgeter",
    "FloorBudget",
    "BuildableBoundary",
    "BuildableBoundaryCalculator",
    "CandidateAllocation",
    "CandidateGenerator",
    "CandidateScorer",
    "AdaptiveRefiner",
    "PartitionItem",
    "SpatialPartitioner",
    "InfeasibleAllocationError",
    "BoundaryConstraintError",
    "score_region",
    "score_allocation",
    "calculate_adjacency_score",
]
