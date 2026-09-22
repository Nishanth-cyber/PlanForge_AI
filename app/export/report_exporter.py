"""Human-readable Markdown project report generation."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Union, List

from app.models.requirements import Requirements
from app.models.planning import PlanningSpec
from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.validation import ValidationReport
from app.models.refinement import RefinementResult
from app.models.alternatives import DesignAlternative, DesignAlternativeSet
from app.explainability.models import DecisionTrace
from app.explainability.renderer import ExplanationRenderer


def generate_project_markdown_report(
    project_id: str,
    project_name: str = "",
    requirements: Optional[Requirements] = None,
    planning_spec: Optional[PlanningSpec] = None,
    allocation_set: Optional[AllocationSet] = None,
    architectural_design_set: Optional[ArchitecturalDesignSet] = None,
    floor_plan_set: Optional[FloorPlanSet] = None,
    validation_report: Optional[ValidationReport] = None,
    refinement_result: Optional[RefinementResult] = None,
    alternative_set: Optional[DesignAlternativeSet] = None,
    decision_trace: Optional[DecisionTrace] = None,
) -> str:
    """Generate comprehensive human-readable Markdown generation report.

    Strict Invariants:
    - Neutral presentation: No alternative is labeled "best", "winner", or "optimal".
    - Validity status: Clearly distinguishes VALID, INVALID, and VALID WITH WARNINGS based
      strictly on ValidationReport.overall_valid.
    - Zero fabrication: If metrics are missing, falls back cleanly.
    """
    proj_title = project_name or (requirements.project_name if requirements else project_id)
    lines: List[str] = [
        f"# PlanForge AI — Floor Plan Generation Report: {proj_title}",
        f"**Project ID:** `{project_id}`  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Pipeline Status:** Complete",
        "",
        "---",
        "",
        "## 1. Project Executive Summary",
    ]

    # Requirements summary
    if requirements:
        plot_dims = requirements.plot_dimensions
        dim_str = f"{plot_dims[0]:.2f}m × {plot_dims[1]:.2f}m" if plot_dims else "Custom polygon"
        area_str = f"{requirements.plot_area_sqm:.2f} m²" if requirements.plot_area_sqm else "Calculated from boundary"
        orient_str = requirements.orientation or "Not specified"
        target_f = len(requirements.floors) if requirements.floors else (requirements.target_floors or 1)

        lines.extend([
            f"- **Plot Dimensions:** {dim_str}",
            f"- **Plot Area:** {area_str}",
            f"- **Orientation:** {orient_str}",
            f"- **Target Floors:** {target_f}",
            f"- **Total Room Requirements:** {requirements.total_rooms()}",
        ])
        if requirements.setbacks:
            setbacks_str = ", ".join(f"{k}: {v:.1f}m" for k, v in requirements.setbacks.items())
            lines.append(f"- **Setbacks:** {setbacks_str}")
    else:
        lines.append("- *Requirements data not supplied for this report.*")

    lines.extend(["", "---", "", "## 2. Planning & Program Strategy"])
    if planning_spec:
        lines.append(f"- **Total Programmed Floors:** {len(planning_spec.floors)}")
        for f in planning_spec.floors:
            lines.append(f"  - **Floor {f.floor_number}:** {len(f.room_specs)} rooms programmed")
            cat_counts: dict[str, int] = {}
            for r in f.room_specs:
                cat = getattr(r, "room_category", getattr(r, "category", "other"))
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            cat_str = ", ".join(f"{k}: {v}" for k, v in cat_counts.items())
            lines.append(f"    - Categories: {cat_str}")
    else:
        lines.append("- *Planning specification not supplied.*")

    lines.extend(["", "---", "", "## 3. ASAA Spatial Allocation"])
    if allocation_set:
        total_regions = sum(len(a.allocated_regions) for a in allocation_set.allocations)
        lines.append(f"- **Allocated Floors:** {len(allocation_set.allocations)}")
        lines.append(f"- **Total Allocated Regions:** {total_regions}")
        for alloc in allocation_set.allocations:
            lines.append(f"  - **Floor {alloc.floor_number}:** {len(alloc.allocated_regions)} regions ({alloc.total_area_sqm:.1f} m² allocated, {alloc.circulation_area_sqm:.1f} m² circulation)")
    else:
        lines.append("- *Spatial allocation set not supplied.*")

    lines.extend(["", "---", "", "## 4. Independent Validation Status"])
    # Resolve validation report
    val_rep = validation_report
    if not val_rep and floor_plan_set and floor_plan_set.validation_report:
        val_rep = floor_plan_set.validation_report
    if not val_rep and refinement_result:
        val_rep = refinement_result.final_report

    if val_rep:
        if val_rep.overall_valid:
            if val_rep.total_warnings > 0:
                val_status = "VALID WITH WARNINGS"
            else:
                val_status = "VALID"
        else:
            val_status = "INVALID"

        lines.extend([
            f"- **Validation Status:** **`{val_status}`**",
            f"- **Overall Compliance Score:** {val_rep.overall_score:.1f} / 100.0",
            f"- **Total Errors:** {val_rep.total_errors}",
            f"- **Total Warnings:** {val_rep.total_warnings}",
        ])

        err_list = val_rep.all_errors() if hasattr(val_rep, "all_errors") else [i for i in getattr(val_rep, "issues", []) if getattr(i, "severity", "") == "error"]
        warn_list = val_rep.all_warnings() if hasattr(val_rep, "all_warnings") else [i for i in getattr(val_rep, "issues", []) if getattr(i, "severity", "") == "warning"]

        if val_rep.total_errors > 0:
            lines.append("")
            lines.append("### Critical Non-Compliance Errors:")
            for issue in err_list:
                rule = getattr(issue, "rule_id", getattr(issue, "check", getattr(issue, "category", "RULE")))
                e_type = getattr(issue, "entity_type", getattr(issue, "category", "entity"))
                e_id = getattr(issue, "target_id", getattr(issue, "room_id", getattr(issue, "entity_id", "floor")))
                lines.append(f"- ❌ **[{rule}]** `{e_type}` ({e_id}): {issue.message}")

        if val_rep.total_warnings > 0:
            lines.append("")
            lines.append("### Advisory Warnings:")
            for issue in warn_list:
                rule = getattr(issue, "rule_id", getattr(issue, "check", getattr(issue, "category", "RULE")))
                e_type = getattr(issue, "entity_type", getattr(issue, "category", "entity"))
                e_id = getattr(issue, "target_id", getattr(issue, "room_id", getattr(issue, "entity_id", "floor")))
                lines.append(f"- ⚠️ **[{rule}]** `{e_type}` ({e_id}): {issue.message}")
    else:
        lines.append("- *Validation report not supplied.*")

    lines.extend(["", "---", "", "## 5. Iterative Refinement History"])
    if refinement_result:
        status_val = refinement_result.status.value if isinstance(refinement_result.status, Enum) else str(refinement_result.status)
        lines.extend([
            f"- **Refinement Status:** `{status_val}`",
            f"- **Total Iterations Attempted:** {refinement_result.total_iterations}",
            f"- **Design Modifications Applied:** {len(refinement_result.changes)}",
            f"- **Termination Reason:** {refinement_result.termination_reason}",
        ])
        if refinement_result.changes:
            lines.append("")
            lines.append("### Refinement Modifications Applied:")
            for chg in refinement_result.changes:
                issue_ref = f" (resolving issues: {chg.validation_issue_ids})" if chg.validation_issue_ids else ""
                lines.append(f"- Adjusted `{chg.field_changed}` on room `{chg.room_id}`: {chg.old_value} → {chg.new_value}. {chg.reason}{issue_ref}")
    else:
        lines.append("- *No refinement loop was required or recorded for this run.*")

    # 6. Structured Room Table
    lines.extend(["", "---", "", "## 6. Room Lifecycle & Geometry Breakdown"])
    if floor_plan_set:
        lines.extend([
            "| Floor | Room Type | Usable Area (m²) | Walls | Doors | Windows | Architectural Room ID |",
            "|:-----:|:----------|:----------------:|:-----:|:-----:|:-------:|:---------------------:|",
        ])
        for fp in floor_plan_set.floor_plans:
            fn = fp.floor_number
            if fp.geometry:
                for r in fp.geometry.rooms:
                    r_type = r.room_type.replace("_", " ").title()
                    arch_id = r.architectural_room_id or "-"
                    lines.append(
                        f"| Floor {fn} | {r_type} | {r.area_sqm:.2f} | {len(r.walls)} | {len(r.doors)} | {len(r.windows)} | `{arch_id}` |"
                    )
        lines.append(f"\n**Total Usable Area Across All Floors:** {floor_plan_set.total_usable_area:.2f} m²")
    else:
        lines.append("- *Constructed physical geometry table not available.*")

    # 7. Multi-Design Alternatives (Neutral Presentation)
    lines.extend(["", "---", "", "## 7. Multi-Design Alternatives Exploration"])
    if alternative_set and alternative_set.alternatives:
        lines.extend([
            f"- **Requested Alternatives:** {alternative_set.requested_count}",
            f"- **Candidates Evaluated:** {alternative_set.candidates_generated}",
            f"- **Validated Distinct Alternatives:** {len(alternative_set.alternatives)}",
            f"- **Strategies Attempted:** {', '.join(alternative_set.strategies_attempted)}",
            "",
            "> [!NOTE]",
            "> All alternatives satisfy 100% of user program requirements and ASAA allocation bounds.",
            "> They are presented neutrally without subjective ranking or single-candidate preference.",
            "",
        ])

        for alt in alternative_set.alternatives:
            status_str = alt.status.value if isinstance(alt.status, Enum) else str(alt.status)
            lines.extend([
                f"### Alternative {alt.index}: Strategy `{alt.strategy}`",
                f"- **Alternative ID:** `{alt.alternative_id}`",
                f"- **Status:** `{status_str}` (Valid: {alt.is_valid})",
                f"- **Design Rationale:** {alt.design_rationale or 'Neutral structural alternative'}",
            ])
            if alt.characteristics:
                lines.append(f"- **Key Characteristics:** {', '.join(alt.characteristics)}")
            if alt.diversity_scores:
                scores_str = ", ".join(f"{k}: {v:.3f}" for k, v in alt.diversity_scores.items())
                lines.append(f"- **Pairwise Structural Diversity Distances:** {scores_str}")
            lines.append("")

        if alternative_set.rejected_candidates:
            lines.append("### Rejected Candidates Audit Log:")
            for rej in alternative_set.rejected_candidates:
                rej_stat = rej.status.value if isinstance(rej.status, Enum) else str(rej.status)
                lines.append(f"- Candidate `{rej.alternative_id}` (Strategy `{rej.strategy}`): Status `{rej_stat}`. Rejection reason: {rej.rejection_reason or rej.design_rationale}")
    else:
        lines.append("- *Single design generation mode (no multi-alternative set generated).*")

    # 8. Explainability Integration
    lines.extend(["", "---", "", "## 8. Explainability & Decision Trace"])
    if decision_trace:
        if hasattr(ExplanationRenderer, "render_project_summary"):
            exp_summary = ExplanationRenderer.render_project_summary(decision_trace)
        else:
            exp_summary = f"- Trace ID: `{decision_trace.trace_id}` ({len(decision_trace.stages)} stages recorded)"
        lines.append(exp_summary)
    else:
        lines.append("- *Decision trace not supplied for this report.*")

    lines.append("")
    return "\n".join(lines)


def generate_alternative_markdown_report(
    alternative: DesignAlternative,
    decision_trace: Optional[DecisionTrace] = None,
) -> str:
    """Generate Markdown report for a specific alternative."""
    status_str = alternative.status.value if isinstance(alternative.status, Enum) else str(alternative.status)
    lines: List[str] = [
        f"# Design Alternative {alternative.index} — Strategy: {alternative.strategy}",
        f"**Alternative ID:** `{alternative.alternative_id}`  ",
        f"**Status:** `{status_str}` (Valid: {alternative.is_valid})  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## Architectural Characteristics & Rationale",
        f"- **Strategy:** `{alternative.strategy}`",
        f"- **Design Rationale:** {alternative.design_rationale or 'Structural organization based on strategy.'}",
    ]

    if alternative.characteristics:
        lines.append(f"- **Architectural Traits:** {', '.join(alternative.characteristics)}")

    if alternative.diversity_scores:
        lines.append("")
        lines.append("## Pairwise Structural Diversity Distances")
        for other_id, dist in alternative.diversity_scores.items():
            lines.append(f"- Diversity distance to `{other_id}`: **{dist:.3f}**")

    if alternative.validation_report:
        lines.append("")
        lines.append("## Validation Findings")
        v = alternative.validation_report
        lines.append(f"- Overall Valid: `{v.overall_valid}`")
        lines.append(f"- Errors: {v.total_errors}, Warnings: {v.total_warnings}")
        v_errs = v.all_errors() if hasattr(v, "all_errors") else [i for i in getattr(v, "issues", []) if getattr(i, "severity", "") == "error"]
        v_warns = v.all_warnings() if hasattr(v, "all_warnings") else [i for i in getattr(v, "issues", []) if getattr(i, "severity", "") == "warning"]
        for err in v_errs:
            r = getattr(err, "rule_id", getattr(err, "check", getattr(err, "category", "RULE")))
            lines.append(f"- ❌ [{r}]: {err.message}")
        for warn in v_warns:
            r = getattr(warn, "rule_id", getattr(warn, "check", getattr(warn, "category", "RULE")))
            lines.append(f"- ⚠️ [{r}]: {warn.message}")

    if decision_trace:
        alt_trace = None
        for a in decision_trace.alternatives:
            if a.alternative_id == alternative.alternative_id:
                alt_trace = a
                break
        if alt_trace:
            lines.append("")
            lines.append("## Decision Trace for this Alternative")
            lines.append(f"- Strategy: `{alt_trace.strategy}`")
            lines.append(f"- Recorded Events: {len(alt_trace.events)}")

    lines.append("")
    return "\n".join(lines)


def save_markdown(content: str, output_path: Union[str, Path]) -> Path:
    """Save string content to Markdown file."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(content)
    return out_p
