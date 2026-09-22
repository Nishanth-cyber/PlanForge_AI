"""Central benchmark runner for PlanForge research evaluation."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import List, Optional

from app.evaluation.ablation import AblationStudyCoordinator
from app.evaluation.aggregation import MetricAggregator
from app.evaluation.baselines import BaselineSpatialAllocator
from app.evaluation.benchmark import BenchmarkRegistry
from app.evaluation.metrics import MetricCalculator
from app.evaluation.models import (
    CaseEvaluationResult,
    EvaluationConfig,
    ExperimentRun,
)
from app.evaluation.plotting import EvaluationPlotter
from app.evaluation.reporting import EvaluationReporter
from app.evaluation.reproducibility import ReproducibilityAuditor
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Executes full-system research evaluation and benchmarking experiments."""

    def __init__(
        self,
        config: Optional[EvaluationConfig] = None,
        orchestrator: Optional[PlanForgeOrchestrator] = None,
    ) -> None:
        self.config = config or EvaluationConfig()
        self.orchestrator = orchestrator or PlanForgeOrchestrator()
        self.ablation_coordinator = AblationStudyCoordinator(seed=self.config.seed)
        self.repro_auditor = ReproducibilityAuditor(
            runs_count=self.config.reproducibility_runs,
            seed=self.config.seed,
        )

    def run(self) -> ExperimentRun:
        """Execute the configured benchmark evaluation suite."""
        run_id = generate_id("eval_run")
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Select benchmark cases
        if self.config.benchmark_case_ids:
            cases = BenchmarkRegistry.filter_by_ids(self.config.benchmark_case_ids)
        elif self.config.tags:
            cases = BenchmarkRegistry.filter_by_tags(self.config.tags)
        else:
            cases = BenchmarkRegistry.get_all_cases()

        logger.info("Executing benchmark run %s across %d cases...", run_id, len(cases))

        case_results: List[CaseEvaluationResult] = []
        out_base = Path(self.config.output_dir)
        out_base.mkdir(parents=True, exist_ok=True)

        # 2. Execute primary evaluation per case
        for case in cases:
            logger.info("Evaluating case: %s (%s)...", case.case_id, case.name)
            orch_cfg = OrchestrationConfig(
                output_dir=str(out_base / "raw_projects" / case.case_id),
                num_alternatives=self.config.num_alternatives,
                enable_refinement=True,
                enable_rendering=False,
                enable_exports=False,
            )

            res = self.orchestrator.generate(case.brief, project_name=case.name, config=orch_cfg)

            # Compute the 20 research metrics
            metrics = MetricCalculator.calculate_all(res, expected_props=case.expected_properties)

            timings = {k: getattr(v, "duration_ms", 0.0) for k, v in res.stage_records.items()}
            statuses = {k: getattr(v, "status").name for k, v in res.stage_records.items()}

            case_eval = CaseEvaluationResult(
                case_id=case.case_id,
                name=case.name,
                tags=[t.value for t in case.tags],
                status=res.status,
                is_success=res.is_success,
                overall_valid=res.is_valid,
                error_message=res.error_message,
                metrics=metrics,
                stage_timings_ms=timings,
                stage_statuses=statuses,
            )
            case_results.append(case_eval)

        # 3. Controlled Ablations
        ablation_results = []
        if self.config.run_ablation:
            logger.info("Running controlled ablation studies...")
            # Select representative cases for ablations (small, medium, multi-floor, attached suite)
            preferred_ids = [
                "case_01_small_single_floor",
                "case_02_medium_single_floor",
                "case_04_two_floor_family",
                "case_09_attached_suite",
            ]
            ablation_cases = [c for c in cases if c.case_id in preferred_ids]
            if not ablation_cases:
                ablation_cases = [c for c in cases if not c.has_tag("INFEASIBLE")][:4]
            for c in ablation_cases:
                # Ablation B: ASAA vs Baseline
                ab_asaa = self.ablation_coordinator.evaluate_asaa_ablation(
                    case=c,
                    full_orchestrator=self.orchestrator,
                    output_dir=str(out_base / "ablation_raw"),
                )
                ablation_results.append(ab_asaa)

                # Ablation C: Refinement Impact
                ab_ref = self.ablation_coordinator.evaluate_refinement_ablation(
                    case=c,
                    orchestrator=self.orchestrator,
                    output_dir=str(out_base / "ablation_raw"),
                )
                ablation_results.append(ab_ref)

                # Ablation D: Diversity Counts
                ab_div = self.ablation_coordinator.evaluate_diversity_ablation(
                    case=c,
                    orchestrator=self.orchestrator,
                    counts=[1, 3],
                    output_dir=str(out_base / "ablation_raw"),
                )
                ablation_results.append(ab_div)

        # 4. Multi-Run Reproducibility Checks
        reproducibility_results = []
        if self.config.run_reproducibility:
            logger.info("Auditing deterministic reproducibility across repeated runs...")
            repro_cases = [c for c in cases if not c.has_tag("INFEASIBLE")][:2]
            for c in repro_cases:
                rep_res = self.repro_auditor.audit_case(
                    case=c,
                    orchestrator=self.orchestrator,
                    output_dir=str(out_base / "repro_raw"),
                )
                reproducibility_results.append(rep_res)

        # 5. Statistical Aggregation
        summary_metrics = MetricAggregator.aggregate_cases(case_results)

        experiment_run = ExperimentRun(
            run_id=run_id,
            timestamp=timestamp,
            config=self.config,
            case_results=case_results,
            ablation_results=ablation_results,
            reproducibility_results=reproducibility_results,
            summary_metrics=summary_metrics,
        )

        # 6. Export Reports and Tables
        EvaluationReporter.export_all(experiment_run, self.config.output_dir)

        # 7. Generate Research Plots
        if self.config.export_plots:
            EvaluationPlotter.plot_all(
                summary=summary_metrics,
                ablation_results=ablation_results,
                output_dir=self.config.output_dir,
            )

        logger.info("Evaluation run %s complete. Artifacts written to %s", run_id, self.config.output_dir)
        return experiment_run


def main() -> None:
    """CLI entrypoint for running evaluation experiments."""
    parser = argparse.ArgumentParser(description="PlanForge Research Evaluation & Benchmarking Runner")
    parser.add_argument("--cases", nargs="*", help="Specific benchmark case IDs to execute")
    parser.add_argument("--tags", nargs="*", help="Filter benchmark cases by category tag")
    parser.add_argument("--output-dir", default="results/runs/latest", help="Output directory for results")
    parser.add_argument("--no-baseline", action="store_true", help="Disable baseline comparison")
    parser.add_argument("--no-ablation", action="store_true", help="Disable ablation studies")
    parser.add_argument("--no-repro", action="store_true", help="Disable reproducibility audit")
    parser.add_argument("--no-plots", action="store_true", help="Disable plot generation")

    args = parser.parse_args()

    config = EvaluationConfig(
        benchmark_case_ids=args.cases,
        tags=args.tags,
        output_dir=args.output_dir,
        run_baseline=not args.no_baseline,
        run_ablation=not args.no_ablation,
        run_reproducibility=not args.no_repro,
        export_plots=not args.no_plots,
    )

    runner = BenchmarkRunner(config=config)
    run = runner.run()

    print("\n=======================================================")
    print("PLANFORGE AI — RESEARCH EVALUATION COMPLETE")
    print(f"Run ID: {run.run_id}")
    print(f"Cases Evaluated: {len(run.case_results)}")
    print(f"Ablation Studies: {len(run.ablation_results)}")
    print(f"Reproducibility Checks: {len(run.reproducibility_results)}")
    print(f"Results Directory: {config.output_dir}")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
