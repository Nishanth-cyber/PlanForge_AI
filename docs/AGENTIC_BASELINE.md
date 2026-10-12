# PlanForge Agentic Transformation - Phase 2 Baseline

**Read this first:** the assistant cannot execute code on your machine. Nothing in section A was produced by a fresh run during this
transformation. It is a *recorded* baseline taken from artifacts already in the repository. Section C lists the exact commands that
produce a *fresh* baseline; paste their output into section D before any comparison is made.

## A. Recorded baseline (pre-existing artifacts, mock LLM)

Source: `results/evaluation_run/` (`metadata.json`, `summary.json`, `failure_analysis.json`).

| Property | Value |
|----------|-------|
| Run id | `eval_run_66ba99354301` |
| Recorded at | 2026-09-20T14:36:06Z |
| Python / platform | 3.14.7 / Windows-10 (as recorded in metadata) |
| LLM | **mock** (`mock_llm: true`) - no live-LLM measurement exists |
| Seed | 42 |
| Benchmark version | 1.0.0 (16 cases) |
| Code revision | not recorded in the artifact (cannot be tied to a commit) |

### A.1 Outcome counts
| Metric | Value |
|--------|-------|
| Cases | 16 |
| Successful executions | 15 |
| Valid plans | 15 |
| Unsuccessful | 1 - `case_16_infeasible_deficit`, an intentional negative control |
| Infeasible message | "Floor 1: Total minimum room area (122.6 m2) exceeds available buildable area (12.8 m2) by deficit of 109.9 m2" |
| Status given to it | `failed` (the structured infeasibility is flattened; see audit F19) |

### A.2 Selected quality metrics (mean over the 15 successful cases)
| Metric | Mean |
|--------|------|
| Room coverage | 100.0 % |
| Floor-count adherence | 100.0 % |
| Room-count accuracy | 90.37 % (min 55.6) |
| Min-area compliance | 90.0 % (min 60.0) |
| Preferred-area MAE | 6.58 m2 |
| Allocation adjacency compliance | 100.0 % |
| Boundary / connectivity / door compliance | 100.0 % each |
| Validation hard errors | 0.0 |
| Validation warnings | 5.06 (n=16, max 9) |
| Validation score | 80.62 (n=16, includes the failed case as 0) |
| Staircase compliance (3 multi-floor cases) | 100.0 % |

### A.3 Performance (mock LLM, exports and rendering disabled)
| Metric | Mean ms |
|--------|---------|
| Total pipeline | 259.41 (median 125.71, max 1483.72) |
| ASAA | 234.74 (dominant stage) |
| Geometry | 10.12 |
| Validation | 3.66 |
| Refinement | ~0.00 |

### A.4 What this baseline can NOT show
1. **Refinement is never exercised**: 15/15 plans were valid on the first pass (`timing_refinement_ms` ~ 0). Refinement success rate,
   replanning, and repeated-failure handling have no baseline value. New fault-injection benchmark cases are required.
2. **LLM behavior is not measured**: mock only. No LLM-call counts, latency, or cost exist.
3. **Feasibility detection** has exactly one data point (case 16).
4. **Alternatives**: the run used one alternative per case (the single-design wrapper), so diversity and alternative quality are unmeasured.
5. **Two metrics look inconsistent and must not be used as baseline values until explained**: `trace_entity_chain_completeness`
   mean 559.11 (not a 0-100 percentage) and `alternative_validity_rate` 0.0 while 15 plans are valid.
6. The "reproducibility" and "ablation" results exist in `results/evaluation_run/` but were not analyzed here.

## B. Recorded test inventory (not a pass/fail result)

Source: `.pytest_cache/v/cache/nodeids` (the node ids pytest collected at some earlier run; the date is not recorded in the file).

| Area | Collected test ids |
|------|--------------------|
| `tests/unit` | 520 |
| `tests/integration` | 30 |
| `tests/regression` | 3 |
| **Total** | **553 in 107 files** |

Caveats: this is a collection count, not a pass count. `.pytest_cache/v/cache/lastfailed` lists only
`tests/unit/test_refinement/test_refinement_loop.py`, a file that no longer exists (it was renamed to `test_refinement_loop_coordinator.py`),
so that entry is stale and is not evidence of a current failure. The count may be out of date relative to the current tree. Frontend
tests (`frontend/src/__tests__/*.test.tsx`, 9 files) are not included in the 553.

## C. Commands to capture the FRESH baseline (run from the project root, PowerShell, venv active)

```powershell
venv\Scripts\activate
git rev-parse HEAD
git status --short
python --version

# 1. Full Python test run (record the final summary line)
python -m pytest -q -p no:cacheprovider 2>&1 | Tee-Object -FilePath logs\baseline_pytest.txt | Select-Object -Last 25

# 2. Collection count only
python -m pytest --collect-only -q 2>&1 | Select-Object -Last 3

# 3. Evaluation baseline (writes a NEW directory so the recorded run is preserved)
python scripts\run_evaluation.py --output-dir results\baseline_fresh

# 4. Frontend tests (inspect package.json for the exact script name first)
cd frontend
npm test -- --run
cd ..
```

## D. Fresh baseline results (to be filled from your output; empty until provided)

| Item | Value |
|------|-------|
| Git revision | _pending_ |
| pytest passed / failed / skipped / errors | _pending_ |
| Collected tests | _pending_ |
| Evaluation run id and directory | _pending_ |
| Frontend tests passed / failed | _pending_ |
| Live-LLM run | _not executed; requires credentials and is a separate step_ |
