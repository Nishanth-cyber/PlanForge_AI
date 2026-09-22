"""Unit tests for multi-run deterministic reproducibility auditor."""

from __future__ import annotations

import pytest
from app.evaluation.benchmark import BenchmarkRegistry
from app.evaluation.reproducibility import ReproducibilityAuditor
from app.orchestration.orchestrator import PlanForgeOrchestrator


def test_reproducibility_auditor_deterministic_case(tmp_path):
    """Verify ReproducibilityAuditor confirms bitwise identical stage outputs across runs."""
    auditor = ReproducibilityAuditor(runs_count=2, seed=42)
    orchestrator = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    res = auditor.audit_case(
        case=case,
        orchestrator=orchestrator,
        output_dir=str(tmp_path / "repro_test"),
    )

    assert res.num_runs == 2
    assert res.is_identical is True
    assert res.divergence_stage is None
    assert len(set(res.hashes)) == 1
