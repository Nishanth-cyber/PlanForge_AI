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

            stats_by_metric[m_name] = {
                "n": n,
                "mean": round(mean_val, 2),
                "median": round(median_val, 2),
                "std_dev": round(std_dev, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
            }

        summary["metrics"] = stats_by_metric

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
