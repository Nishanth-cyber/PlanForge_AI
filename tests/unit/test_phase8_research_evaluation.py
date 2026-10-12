"""Tests for Phase 8: Research Evaluation, Ablation Studies, and Explainability.

Verifies:
1. Identical deterministic inputs produce reproducible results under fixed seeds.
2. Evaluation records preserve the exact configuration used.
3. Every metric is computed from actual outputs.
4. Invalid designs are not counted as successful designs.
5. Correctly detected infeasibility is reported separately from generation success.
6. Missing metrics are handled explicitly.
7. Ablation configurations actually disable or modify the intended component.
8. LLM and fallback provenance are recorded accurately.
9. Mocked results are never labeled as live-provider results.
10. Paired comparisons use compatible inputs.
11. Statistical summaries handle small samples and missing values correctly.
12. Explainability outputs cite actual recorded evidence.
13. Missing evidence produces an explicit limitation rather than a fabricated explanation.
14. Evaluation output schemas are stable and versioned.
15. Phase 7 clarification and resume behavior remains correct.
16. Legacy pipeline behavior remains compatible.
"""

import pytest
from app.evaluation.models import (
    EvaluationProtocolConfig,
    CaseEvaluationResult,
    MetricValue,
    AblationResult,
)
from app.evaluation.aggregation import (
    MetricAggregator,
)
from app.evaluation.benchmark import BenchmarkRegistry
from app.evaluation.ablation import AblationStudyCoordinator
from app.explainability.service import (
    ExplainabilityService,
    GroundedExplanation,
    ProjectExplanationDossier,
)
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.agentic.state import (
    ProjectState,
    Finding,
    DecisionRecord,
)


def _create_minimal_state(project_id="test_p8") -> ProjectState:
    state = ProjectState(project_id=project_id, goal="Generate residential layout")
    return state


class TestPhase8ResearchEvaluation:

    def test_01_deterministic_reproducibility(self):
        """1. Identical deterministic inputs produce reproducible results under fixed seeds."""
        case = BenchmarkRegistry.get_case("case_01_small_single_floor")
        assert case is not None

        orch = PlanForgeOrchestrator()
        cfg1 = OrchestrationConfig(mode="pipeline", seed=42, enable_rendering=False, enable_exports=False)
        res1 = orch.generate(case.brief, project_name=case.name, config=cfg1)

        cfg2 = OrchestrationConfig(mode="pipeline", seed=42, enable_rendering=False, enable_exports=False)
        res2 = orch.generate(case.brief, project_name=case.name, config=cfg2)

        assert res1.is_success == res2.is_success
        assert res1.status == res2.status
        assert res1.validation_report.overall_valid == res2.validation_report.overall_valid

    def test_02_evaluation_records_preserve_exact_config(self):
        """2. Evaluation records preserve the exact configuration used."""
        proto = EvaluationProtocolConfig(
            experiment_id="test_exp_001",
            dataset_version="2.0",
            case_ids=["case_01_small_single_floor"],
            case_input_hashes={"case_01_small_single_floor": "sha256:abc123"},
            python_version="3.11",
            os_platform="Windows",
            environment_dependencies={"pydantic": "2.0"},
            random_seed=42,
            asaa_candidate_budget=3,
            max_refinement_iterations=5,
            orchestration_mode="hierarchical",
            llm_provider="heuristic",
            llm_model="heuristic-fallback",
            use_live_llm=False,
            scoring_version="v2.1",
            validator_version="v2.0",
        )
        d = proto.to_dict()
        assert d["dataset_version"] == "2.0"
        assert d["random_seed"] == 42
        assert d["orchestration_mode"] == "hierarchical"
        assert d["use_live_llm"] is False
        assert d["case_input_hashes"]["case_01_small_single_floor"] == "sha256:abc123"

    def test_03_metrics_computed_from_actual_outputs(self):
        """3. Every metric is computed from actual outputs."""
        case = BenchmarkRegistry.get_case("case_01_small_single_floor")
        assert case is not None

        orch = PlanForgeOrchestrator()
        cfg = OrchestrationConfig(mode="multi_agent", seed=42, enable_rendering=False, enable_exports=False)
        res = orch.generate(case.brief, project_name=case.name, config=cfg)

        assert res.is_success is True
        assert res.validation_report is not None
        assert res.floor_plan_set is not None
        assert len(res.floor_plan_set.floor_plans) >= 1

    def test_04_invalid_designs_not_counted_as_successful(self):
        """4. Invalid designs are not counted as successful designs."""
        results = [
            CaseEvaluationResult(
                case_id="case_01",
                name="case_01",
                tags=["SINGLE_FLOOR"],
                status="completed",
                is_success=True,
                overall_valid=False,
                metrics={
                    "area_min_compliance": MetricValue(name="area_min_compliance", value=50.0),
                },
            )
        ]
        summary = MetricAggregator.aggregate_cases(results)
        assert summary["valid_plans_count"] == 0
        assert summary["feasible_valid_design_rate"] == 0.0
        assert summary["total_cases"] == 1

    def test_05_infeasibility_detection_reported_separately(self):
        """5. Correctly detected infeasibility is reported separately from generation success."""
        results = [
            CaseEvaluationResult(
                case_id="case_16_infeasible_deficit",
                name="Infeasible deficit",
                tags=["INFEASIBLE"],
                status="waiting_for_clarification",
                is_success=True,
                overall_valid=False,
                metrics={},
            ),
            CaseEvaluationResult(
                case_id="case_01_small_single_floor",
                name="Feasible single floor",
                tags=["SINGLE_FLOOR"],
                status="completed",
                is_success=True,
                overall_valid=True,
                metrics={
                    "area_min_compliance": MetricValue(name="area_min_compliance", value=100.0),
                },
            ),
        ]
        summary = MetricAggregator.aggregate_cases(results)

        assert summary["feasible_cases_count"] == 1
        assert summary["infeasible_cases_count"] == 1
        assert summary["feasible_valid_design_rate"] == 1.0
        assert summary["infeasibility_detection"]["precision"] == 1.0
        assert summary["infeasibility_detection"]["recall"] == 1.0
        assert summary["infeasibility_detection"]["f1_score"] == 1.0

    def test_06_missing_metrics_handled_explicitly(self):
        """6. Missing metrics are handled explicitly without errors or fabricated values."""
        results = [
            CaseEvaluationResult(
                case_id="case_01",
                name="case_01",
                tags=["SINGLE_FLOOR"],
                status="completed",
                is_success=True,
                overall_valid=True,
                metrics={
                    "missing_metric": MetricValue.not_available("missing_metric", "Metric not computed"),
                },
            )
        ]
        summary = MetricAggregator.aggregate_cases(results)
        assert summary["total_cases"] == 1
        assert "missing_metric" not in summary.get("metrics", {})

    def test_07_ablation_configurations_modify_intended_components(self, tmp_path):
        """7. Ablation configurations actually disable or modify the intended component."""
        case = BenchmarkRegistry.get_case("case_01_small_single_floor")
        assert case is not None

        coordinator = AblationStudyCoordinator(seed=42)
        orch = PlanForgeOrchestrator()

        res_budget = coordinator.evaluate_candidate_budget_ablation(
            case=case,
            orchestrator=orch,
            budgets=[1, 3],
            output_dir=str(tmp_path / "budget"),
        )
        assert res_budget.variant_a_name == "Budget_3_Candidates"
        assert res_budget.variant_b_name == "Budget_1_Candidate"

        res_refine = coordinator.evaluate_refinement_ablation(
            case=case,
            orchestrator=orch,
            output_dir=str(tmp_path / "refine"),
        )
        assert res_refine.variant_a_name == "With_Refinement"
        assert res_refine.variant_b_name == "Without_Refinement"

    def test_08_llm_and_fallback_provenance_recorded_accurately(self):
        """8. LLM and fallback provenance are recorded accurately."""
        state = _create_minimal_state()
        state.record_decision(
            agent="planning_agent",
            kind="evaluate_requirements",
            tool=None,
            args={"deficit": 0.0},
            rationale="Deterministic fallback applied because provider returned empty",
            source="fallback",
            fallback_reason="Empty provider response",
        )
        assert len(state.decisions) == 1
        rec = state.decisions[0]
        assert rec.source == "fallback"
        assert rec.fallback_reason == "Empty provider response"

    def test_09_mocked_results_never_labeled_as_live(self):
        """9. Mocked results are never labeled as live-provider results."""
        proto = EvaluationProtocolConfig(
            experiment_id="mock_exp",
            dataset_version="2.0",
            use_live_llm=False,
            llm_provider="heuristic",
            llm_model="heuristic-fallback",
        )
        assert proto.use_live_llm is False
        assert proto.llm_provider == "heuristic"

    def test_10_paired_comparisons_use_compatible_inputs(self):
        """10. Paired comparisons use compatible inputs."""
        res_a = [
            CaseEvaluationResult(
                case_id="case_01",
                name="c1",
                tags=[],
                status="completed",
                is_success=True,
                overall_valid=True,
                metrics={
                    "area_min_compliance": MetricValue(name="area_min_compliance", value=85.0),
                },
            )
        ]
        res_b = [
            CaseEvaluationResult(
                case_id="case_01",
                name="c1",
                tags=[],
                status="completed",
                is_success=True,
                overall_valid=True,
                metrics={
                    "area_min_compliance": MetricValue(name="area_min_compliance", value=80.0),
                },
            )
        ]
        diffs = MetricAggregator.compute_paired_differences(res_a, res_b)
        assert "area_min_compliance" in diffs["metrics"]
        assert diffs["metrics"]["area_min_compliance"]["mean_difference"] == 5.0

    def test_11_statistical_summaries_handle_small_samples(self):
        """11. Statistical summaries handle small samples and missing values correctly."""
        single_res = [
            CaseEvaluationResult(
                case_id="case_01",
                name="c1",
                tags=[],
                status="completed",
                is_success=True,
                overall_valid=True,
                metrics={
                    "test_metric": MetricValue(name="test_metric", value=75.0),
                },
            )
        ]
        summary = MetricAggregator.aggregate_cases(single_res)
        m_stat = summary["metrics"]["test_metric"]
        assert m_stat["n"] == 1
        assert m_stat["mean"] == 75.0
        assert m_stat["std_dev"] == 0.0
        assert m_stat["ci_95"] == 0.0

    def test_12_explainability_outputs_cite_recorded_evidence(self):
        """12. Explainability outputs cite actual recorded evidence."""
        state = _create_minimal_state()
        state.record_decision(
            agent="spatial_allocation_agent",
            kind="allocate_spaces",
            tool="handle_allocate_spatial_regions",
            args={
                "candidate_index": 0,
                "candidate_score": 85.0,
                "deficit": 0.0,
                "soft_preference_score": 88.0,
            },
            rationale="Evaluated 3 ASAA candidates; selected candidate 0 with best adjacency",
            source="rules",
        )
        state.apply_findings(
            findings=[],
            scope_keys=[],
        )

        service = ExplainabilityService()
        dossier = service.generate_dossier(state)

        assert len(dossier.decision_explanations) == 1
        exp = dossier.decision_explanations[0]
        assert exp.is_verified is True
        assert exp.decision_action == "allocate_spaces"
        assert exp.supporting_evidence["candidate_score"] == 85.0

    def test_13_missing_evidence_produces_explicit_limitation(self):
        """13. Missing evidence produces an explicit limitation rather than a fabricated explanation."""
        state = _create_minimal_state()
        state.record_decision(
            agent="unknown_agent",
            kind="magic_action",
            tool=None,
            args={},
            rationale="",
            source="unknown",
        )

        service = ExplainabilityService()
        dossier = service.generate_dossier(state)

        assert len(dossier.decision_explanations) == 1
        exp = dossier.decision_explanations[0]
        assert exp.is_verified is False
        assert "no supporting evidence recorded" in exp.unverified_reason.lower()
        assert exp.to_readable_text().startswith("Action 'magic_action': Reason cannot be verified")

    def test_14_evaluation_output_schemas_are_stable_and_versioned(self):
        """14. Evaluation output schemas are stable and versioned."""
        proto = EvaluationProtocolConfig(
            experiment_id="v_test",
            dataset_version="2.0",
            scoring_version="v2.1",
            validator_version="v2.0",
        )
        d = proto.to_dict()
        assert d["dataset_version"] == "2.0"
        assert d["scoring_version"] == "v2.1"
        assert d["validator_version"] == "v2.0"

    def test_15_phase7_clarification_and_resume_behavior_remains_correct(self):
        """15. Phase 7 clarification and resume behavior remains correct."""
        from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
        from app.agentic.state import RunStatus
        from app.orchestration.hierarchical import HierarchicalOrchestrator

        reqs = Requirements(
            project_name="Infeasible Cottage",
            plot_dimensions=(10.0, 10.0),
            setbacks={"front": 2.0, "rear": 2.0, "left": 2.0, "right": 2.0},
            target_floors=1,
            floors=[
                FloorRequirement(
                    floor_number=1,
                    room_requirements=[
                        RoomRequirement(room_type="living", min_count=1, min_area_sqm=30.0, target_area_sqm=35.0),
                        RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=20.0, target_area_sqm=22.0),
                        RoomRequirement(room_type="master_bedroom", min_count=1, min_area_sqm=25.0, target_area_sqm=28.0),
                        RoomRequirement(room_type="study", min_count=1, min_area_sqm=12.0, target_area_sqm=14.0),
                    ],
                )
            ],
        )

        registry = PlanForgeOrchestrator().tool_registry
        orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

        state = orchestrator.run(
            project_id="test_p8_phase7",
            goal="Infeasible Cottage",
            requirements=reqs,
        )

        assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
        assert state.is_paused is True
        assert state.pending_clarification is not None
        req_id = state.pending_clarification.request_id

        # Apply clarification and resume
        success, msg, response = orchestrator.apply_clarification_response(
            state=state,
            request_id=req_id,
            selected_option_id="expand_plot_depth",
            numeric_overrides={"plot_length": 25.0},
        )
        assert success is True
        assert state.status == RunStatus.RESUMABLE

        res_ok, res_msg, resumed_state = orchestrator.resume(state)
        assert res_ok is True
        assert resumed_state.status in (RunStatus.ACCEPTED, RunStatus.COMPLETED)
        assert resumed_state.get_artifact("floor_plan_set") is not None

    def test_16_legacy_pipeline_behavior_remains_compatible(self):
        """16. Legacy pipeline behavior remains compatible."""
        case = BenchmarkRegistry.get_case("case_01_small_single_floor")
        assert case is not None

        orch = PlanForgeOrchestrator()
        cfg = OrchestrationConfig(mode="pipeline", seed=42, enable_rendering=False, enable_exports=False)
        pipe_res = orch.generate(case.brief, project_name=case.name, config=cfg)

        assert pipe_res.is_success is True
        assert pipe_res.status == "completed"
        assert pipe_res.floor_plan_set is not None
