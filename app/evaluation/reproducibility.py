"""Deterministic multi-run reproducibility auditor for PlanForge research evaluation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional
from app.evaluation.models import BenchmarkCase, ReproducibilityResult
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.pipeline import PipelineResult


class ReproducibilityAuditor:
    """Audits pipeline execution across repeated runs to verify deterministic reproducibility."""

    def __init__(self, runs_count: int = 3, seed: int = 42) -> None:
        self.runs_count = runs_count
        self.seed = seed

    def audit_case(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        output_dir: str = "results/reproducibility",
    ) -> ReproducibilityResult:
        """Run the case multiple times and compare canonicalized stage artifacts."""
        cfg = OrchestrationConfig(
            output_dir=output_dir,
            enable_refinement=True,
            enable_rendering=False,
            enable_exports=False,
        )

        canonical_runs: List[Dict[str, str]] = []
        hashes: List[str] = []

        for r_idx in range(self.runs_count):
            res = orchestrator.generate(case.brief, project_name=f"{case.name}_Repro", config=cfg)
            canon = self._canonicalize_result(res)
            canonical_runs.append(canon)

            # Combined run hash
            full_str = json.dumps(canon, sort_keys=True)
            h = hashlib.sha256(full_str.encode("utf-8")).hexdigest()[:16]
            hashes.append(h)

        # Check equivalence across runs
        is_identical = len(set(hashes)) == 1
        divergence_stage: Optional[str] = None

        if not is_identical:
            # Pinpoint the first stage that diverged
            stages_to_check = [
                "REQUIREMENTS",
                "PLANNING",
                "ASAA",
                "GEOMETRY",
                "VALIDATION",
            ]
            for st in stages_to_check:
                stage_hashes = [r.get(st, "") for r in canonical_runs]
                if len(set(stage_hashes)) > 1:
                    divergence_stage = st
                    break

        return ReproducibilityResult(
            case_id=case.case_id,
            num_runs=self.runs_count,
            is_identical=is_identical,
            divergence_stage=divergence_stage,
            hashes=hashes,
            details={
                "all_hashes": hashes,
                "stages_evaluated": ["REQUIREMENTS", "PLANNING", "ASAA", "GEOMETRY", "VALIDATION"],
            },
        )

    def _canonicalize_result(self, res: PipelineResult) -> Dict[str, str]:
        """Strip volatile non-deterministic fields (IDs, timestamps) into deterministic stage fingerprints."""
        out: Dict[str, str] = {}

        # 1. Requirements fingerprint
        if res.requirements:
            req_data = {
                "target_floors": res.requirements.target_floors,
                "plot_dimensions": res.requirements.plot_dimensions,
                "plot_shape": res.requirements.plot_shape,
                "floors": [
                    {
                        "floor_number": f.floor_number,
                        "rooms": sorted(
                            [
                                (
                                    r.room_type,
                                    getattr(r, "min_count", 1) or 1,
                                    r.min_area_sqm,
                                )
                                for r in f.room_requirements
                            ]
                        ),
                    }
                    for f in res.requirements.floors
                ],
            }
            out["REQUIREMENTS"] = hashlib.md5(json.dumps(req_data, sort_keys=True).encode()).hexdigest()

        # 2. Planning fingerprint
        if res.planning_spec:
            plan_data = {
                "floors": [
                    {
                        "floor_number": f.floor_number,
                        "rooms": sorted(
                            [
                                (
                                    r.room_type,
                                    getattr(r, "room_category", "social"),
                                    r.priority,
                                    r.min_area_sqm,
                                    r.target_area_sqm,
                                    r.attached_to_room_id,
                                )
                                for r in f.room_specs
                            ]
                        ),
                        "adjacency_matrix": sorted(
                            (k, sorted(v)) for k, v in f.adjacency_matrix.items()
                        ),
                        "avoid_matrix": sorted(
                            (k, sorted(v)) for k, v in f.avoid_matrix.items()
                        ),
                    }
                    for f in res.planning_spec.floors
                ],
            }
            out["PLANNING"] = hashlib.md5(json.dumps(plan_data, sort_keys=True).encode()).hexdigest()

        # 3. ASAA fingerprint
        if res.allocation_set:
            alloc_data = [
                {
                    "floor_number": a.floor_number,
                    "regions": sorted(
                        [
                            (
                                r.room_type,
                                round(r.area_sqm, 2),
                                [round(c, 2) for pt in r.polygon for c in pt],
                            )
                            for r in a.allocated_regions
                        ]
                    ),
                }
                for a in res.allocation_set.allocations
            ]
            out["ASAA"] = hashlib.md5(json.dumps(alloc_data, sort_keys=True).encode()).hexdigest()

        # 4. Geometry fingerprint
        if res.floor_plan_set:
            geo_data = [
                {
                    "floor_number": fp.floor_number,
                    "room_areas": sorted([round(r.area_sqm, 2) for r in fp.geometry.rooms]) if fp.geometry else [],
                    "wall_count": len(fp.geometry.walls) if fp.geometry else 0,
                    "door_count": len(fp.geometry.doors) if fp.geometry else 0,
                    "window_count": len(fp.geometry.windows) if fp.geometry else 0,
                }
                for fp in res.floor_plan_set.floor_plans
            ]
            out["GEOMETRY"] = hashlib.md5(json.dumps(geo_data, sort_keys=True).encode()).hexdigest()

        # 5. Validation fingerprint
        if res.validation_report:
            val_data = {
                "overall_valid": res.validation_report.overall_valid,
                "error_count": res.validation_report.total_errors,
                "warning_count": res.validation_report.total_warnings,
                "issue_categories": sorted(
                    [i.category for r in res.validation_report.results for i in r.issues if i.severity == "error"]
                ),
            }
            out["VALIDATION"] = hashlib.md5(json.dumps(val_data, sort_keys=True).encode()).hexdigest()

        return out
