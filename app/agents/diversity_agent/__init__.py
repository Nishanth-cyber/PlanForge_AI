"""Architectural Diversity and Multi-Design Alternative Generation package."""

from app.agents.diversity_agent.generator import MultiDesignGenerator
from app.agents.diversity_agent.metrics import (
    calculate_diversity_distance,
    is_duplicate,
    is_near_duplicate,
)
from app.agents.diversity_agent.signature import DesignSignatureBuilder

__all__ = [
    "DesignSignatureBuilder",
    "MultiDesignGenerator",
    "calculate_diversity_distance",
    "is_duplicate",
    "is_near_duplicate",
]
