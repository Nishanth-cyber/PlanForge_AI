# PlanForge AI — Research Evaluation Artifacts

## Run Information
- **Run ID:** `eval_run_66ba99354301`
- **Timestamp:** `2026-09-20T14:36:06.793290+00:00`
- **Benchmark Version:** `1.0.0`
- **Total Cases:** `16`

## File Inventory
- `metadata.json`: Machine, Python, seed, and execution environment metadata.
- `benchmark_cases.json`: Canonical specifications for all 16 residential benchmark cases.
- `asaa_results.json`: Full ASAA pipeline execution results across benchmark cases.
- `baseline_results.json`: Deterministic priority-blind proportional slice baseline results.
- `ablation_results.json`: Controlled ablations for ASAA, Refinement loop, and Diversity.
- `reproducibility_results.json`: Multi-run deterministic canonical fingerprint audit results.
- `metrics.json`: Granular dictionary of all 20 evaluated research metrics.
- `failure_analysis.json`: Detailed classification of failure modes, infeasible briefs, and warnings.
- `summary.json`: Statistical aggregations (count, mean, median, min, max, std dev).
- `benchmark_metrics.csv`: Tabular metric export across all cases.
- `ablation_metrics.csv`: Tabular metric export across ablation studies.
- `performance_metrics.csv`: Stage-by-stage runtime latency breakdown.
- `RESEARCH_EVALUATION_REPORT.md`: Exhaustive publication-ready research evaluation report.

## Reproduction
To reproduce this evaluation run:
```bash
python scripts/run_evaluation.py --output-dir results/evaluation_run
```
