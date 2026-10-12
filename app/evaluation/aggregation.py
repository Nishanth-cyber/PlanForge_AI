"""Statistical aggregation across benchmark cases and evaluation runs."""

from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List
from app.evaluation.models import CaseEvaluationResult


class MetricAggregator:
    """Computes descriptive statistics across benchmark evaluation runs."""

    @classmethod
    def aggregate_cases(cls, results: List[CaseEvaluationResult]) -> Dict[str, Any]:
        """Compute statistical summaries across a list of case evaluation results."""
        if not results:
            return {}

        summary: Dict[str, Any] = {
            "total_cases": len(results),
            "successful_executions": sum(1 for r in results if r.is_success),
            "valid_plans_count": sum(1 for r in results if r.overall_valid is True),
        }

        # Group numeric values by metric name
        metric_values: Dict[str, List[float]] = {}
        for r in results:
            for m_name, m_val in r.metrics.items():
                if m_val.is_available and isinstance(m_val.value, (int, float)) and not isinstance(m_val.value, bool):
                    if m_name not in metric_values:
                        metric_values[m_name] = []
                    metric_values[m_name].append(float(m_val.value))

        stats_by_metric: Dict[str, Dict[str, Any]] = {}
        for m_name, vals in metric_values.items():
            if not vals:
                continue
            n = len(vals)
            mean_val = sum(vals) / n
            sorted_vals = sorted(vals)
            median_val = statistics.median(vals)
            std_dev = statistics.stdev(vals) if n >= 2 else 0.0
            min_val = min(vals)
            max_val = max(vals)
            ci_95 = round(1.96 * (std_dev / math.sqrt(n)), 2) if n >= 2 else 0.0

            stats_by_metric[m_name] = {
                "n": n,
                "mean": round(mean_val, 2),
                "median": round(median_val, 2),
                "std_dev": round(std_dev, 2),
                "ci_95": ci_95,
                "ci_lower": round(mean_val - ci_95, 2),
                "ci_upper": round(mean_val + ci_95, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
            }

        summary["metrics"] = stats_by_metric

        # Separate feasibility detection from generation success
        infeasible_cases = [r for r in results if any(t in ("INFEASIBLE", "CONTRADICTORY") for t in r.tags)]
        feasible_cases = [r for r in results if not any(t in ("INFEASIBLE", "CONTRADICTORY") for t in r.tags)]

        summary["feasible_cases_count"] = len(feasible_cases)
        summary["infeasible_cases_count"] = len(infeasible_cases)

        if feasible_cases:
            valid_feasible = sum(1 for r in feasible_cases if r.overall_valid is True)
            summary["feasible_valid_design_rate"] = round(valid_feasible / len(feasible_cases), 4)
            summary["feasible_completion_rate"] = round(sum(1 for r in feasible_cases if r.is_success) / len(feasible_cases), 4)

        if infeasible_cases:
            # TP = Infeasible case correctly identified as infeasible, failed, or waiting_for_clarification
            tp = sum(1 for r in infeasible_cases if r.status in ("infeasible", "failed", "waiting_for_clarification", "incomplete_requirements"))
            fn = len(infeasible_cases) - tp
            # FP = Feasible case falsely flagged as infeasible/failed
            fp = sum(1 for r in feasible_cases if r.status in ("infeasible", "failed", "incomplete_requirements"))
            tn = len(feasible_cases) - fp

            precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

            summary["infeasibility_detection"] = {
                "true_positives": tp,
                "false_negatives": fn,
                "false_positives": fp,
                "true_negatives": tn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
            }

        # High-level research summary indicators
        if "req_room_coverage" in stats_by_metric:
            summary["mean_room_coverage_pct"] = stats_by_metric["req_room_coverage"]["mean"]
        if "area_min_compliance" in stats_by_metric:
            summary["mean_area_min_compliance_pct"] = stats_by_metric["area_min_compliance"]["mean"]
        if "area_preferred_mae" in stats_by_metric:
            summary["mean_area_preferred_mae_sqm"] = stats_by_metric["area_preferred_mae"]["mean"]
        if "allocation_adjacency_compliance" in stats_by_metric:
            summary["mean_adjacency_compliance_pct"] = stats_by_metric["allocation_adjacency_compliance"]["mean"]
        if "boundary_compliance" in stats_by_metric:
            summary["mean_boundary_compliance_pct"] = stats_by_metric["boundary_compliance"]["mean"]
        if "connectivity_rate" in stats_by_metric:
            summary["mean_connectivity_pct"] = stats_by_metric["connectivity_rate"]["mean"]
        if "timing_total_ms" in stats_by_metric:
            summary["mean_total_pipeline_ms"] = stats_by_metric["timing_total_ms"]["mean"]

        return summary

    @classmethod
    def compute_paired_differences(
        cls,
        results_a: List[CaseEvaluationResult],
        results_b: List[CaseEvaluationResult],
    ) -> Dict[str, Any]:
        """Compute paired case-by-case deltas between two experimental variants."""
        map_b = {r.case_id: r for r in results_b}
        paired_deltas: Dict[str, List[float]] = {}
        common_cases: List[str] = []

        for r_a in results_a:
            cid = r_a.case_id
            if cid in map_b:
                common_cases.append(cid)
                r_b = map_b[cid]
                for m_name in r_a.metrics:
                    m_a = r_a.metrics[m_name]
                    m_b = r_b.metrics.get(m_name)
                    if (
                        m_a.is_available
                        and m_b
                        and m_b.is_available
                        and isinstance(m_a.value, (int, float))
                        and isinstance(m_b.value, (int, float))
                    ):
                        if m_name not in paired_deltas:
                            paired_deltas[m_name] = []
                        paired_deltas[m_name].append(float(m_a.value) - float(m_b.value))

        summary_diffs: Dict[str, Any] = {
            "paired_cases_count": len(common_cases),
            "common_cases": common_cases,
            "metrics": {},
        }

        for m_name, deltas in paired_deltas.items():
            if deltas:
                n = len(deltas)
                mean_d = sum(deltas) / n
                std_d = statistics.stdev(deltas) if n >= 2 else 0.0
                summary_diffs["metrics"][m_name] = {
                    "mean_difference": round(mean_d, 3),
                    "median_difference": round(statistics.median(deltas), 3),
                    "std_difference": round(std_d, 3),
                    "min_difference": round(min(deltas), 3),
                    "max_difference": round(max(deltas), 3),
                }

        return summary_diffs
