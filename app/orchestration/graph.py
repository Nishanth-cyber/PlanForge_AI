"""Dependency graph and state machine transitions for the PlanForge workflow.

Tracks the DAG of artifact dependencies and provides clean downstream invalidation
when an agent chooses to replan, reallocate, or revise an upstream decision.
"""

from __future__ import annotations

from typing import Dict, List, Set

# Artifact dependency mapping: key depends on values
ARTIFACT_DEPENDENCIES: Dict[str, List[str]] = {
    "requirements": [],
    "planning_spec": ["requirements"],
    "allocation_set": ["planning_spec"],
    "architectural_design_set": ["planning_spec", "allocation_set", "requirements"],
    "floor_plan_set": ["architectural_design_set", "allocation_set"],
    "validation_report": ["floor_plan_set"],
    "alternative_set": ["planning_spec", "allocation_set", "requirements"],
    "export_bundle_path": ["floor_plan_set"],
}

# Reverse mapping: key invalidates values
ARTIFACT_INVALIDATES: Dict[str, List[str]] = {
    "requirements": ["planning_spec", "allocation_set", "architectural_design_set", "floor_plan_set", "validation_report", "alternative_set", "export_bundle_path"],
    "planning_spec": ["allocation_set", "architectural_design_set", "floor_plan_set", "validation_report", "alternative_set"],
    "allocation_set": ["architectural_design_set", "floor_plan_set", "validation_report", "alternative_set"],
    "architectural_design_set": ["floor_plan_set", "validation_report"],
    "floor_plan_set": ["validation_report", "export_bundle_path"],
}


def get_downstream_invalidations(artifact_key: str) -> List[str]:
    """Return all downstream artifacts that must be invalidated if `artifact_key` is revised."""
    return ARTIFACT_INVALIDATES.get(artifact_key, [])
