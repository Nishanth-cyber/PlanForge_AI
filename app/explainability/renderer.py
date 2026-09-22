"""Deterministic explanation renderer generating human-readable explanations from structured trace data.

This module renders concise, structured, factual explanations across 6 distinct levels:
1. Project Summary
2. Alternative Summary
3. Room-Level Lifecycle Narrative
4. Validation Findings
5. Refinement Trajectory Narrative
6. Pairwise Diversity Comparison

Critical Principles:
- Factual and Evidence-Based: Only facts present in the trace are reported.
- Zero Fabrication: Never invents architectural reasons (e.g. sunlight or orientation if not computed).
- Zero Chain-of-Thought: Never reveals internal LLM tokens or private deliberations.
- Objective Comparisons: Never makes subjective quality claims ("better", "more beautiful").
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.explainability.models import (
    AlternativeTrace,
    DecisionEvent,
    DecisionTrace,
    DecisionType,
    EntityTraceChain,
    StageName,
)


class ExplanationRenderer:
    """Renders deterministic human-readable explanations from a DecisionTrace."""

    @classmethod
    def render_project_summary(cls, trace: DecisionTrace) -> str:
        """Render a high-level project summary covering requirements through alternatives."""
        lines: list[str] = [f"# Project Summary: {trace.project_name}", ""]

        # 1. Requirements Overview
        req_events = trace.get_events_by_stage(StageName.REQUIREMENT)
        room_reqs = [e for e in req_events if e.entity_type == "room"]
        plot_event = next((e for e in req_events if e.entity_type == "plot"), None)

        lines.append("## 1. Requirements")
        if plot_event:
            ev = plot_event.evidence
            dims = ev.get("plot_dimensions")
            dim_str = f"{dims[0]:.2f}m × {dims[1]:.2f}m" if dims else "Specified boundary"
            lines.append(f"- Plot: {dim_str}")
            if ev.get("setbacks"):
                sb = ev["setbacks"]
                sb_str = ", ".join(f"{k}: {v}m" for k, v in sb.items())
                lines.append(f"- Setbacks: {sb_str}")
        lines.append(f"- Program: {len(room_reqs)} room requirement(s) parsed from user brief.")

        # 2. Planning Overview
        plan_events = trace.get_events_by_stage(StageName.PLANNING)
        if plan_events:
            lines.append("")
            lines.append("## 2. Planning & Spatial Organization")
            social_count = sum(1 for e in plan_events if e.evidence.get("category") == "social")
            private_count = sum(1 for e in plan_events if e.evidence.get("category") == "private")
            high_pri = [e.evidence.get("room_type") for e in plan_events if e.event_type == DecisionType.PRIORITY_ASSIGNED.value and e.evidence.get("priority") == "high"]
            lines.append(f"- Categorization: {social_count} social space(s), {private_count} private space(s).")
            if high_pri:
                lines.append(f"- High Priority Spaces: {', '.join(sorted(set(filter(None, high_pri))))}.")

        # 3. Alternatives Overview
        if trace.alternatives:
            lines.append("")
            lines.append(f"## 3. Generated Alternatives ({len(trace.alternatives)} accepted)")
            for alt in trace.alternatives:
                chars = "; ".join(alt.characteristics[:2]) if alt.characteristics else "Standard layout"
                lines.append(f"- Alternative {alt.index} ({alt.strategy}): {chars} (Status: {alt.status})")

        return "\n".join(lines)

    @classmethod
    def render_alternative_summary(cls, trace: DecisionTrace, alternative_id: str) -> str:
        """Render a concise architectural summary of an individual design alternative."""
        alt = next((a for a in trace.alternatives if a.alternative_id == alternative_id), None)
        if not alt:
            # Check if it was a rejected candidate
            rej_evts = [
                e for e in trace.get_events_by_type(DecisionType.ALTERNATIVE_REJECTED)
                if e.entity_id == alternative_id
            ]
            if rej_evts:
                rej = rej_evts[0]
                return (
                    f"Alternative {alternative_id} was REJECTED.\n"
                    f"Reason: {rej.reason}\n"
                    f"Details: {rej.evidence}"
                )
            return f"Alternative '{alternative_id}' not found in decision trace."

        lines = [
            f"# Alternative {alt.index}: Strategy '{alt.strategy}'",
            f"- Status: {alt.status}",
            f"- Strategy: {alt.strategy}",
        ]

        if alt.characteristics:
            lines.append("- Key Characteristics:")
            for c in alt.characteristics:
                lines.append(f"  • {c}")

        if alt.validation_summary:
            vs = alt.validation_summary
            valid_label = "VALID" if vs.get("is_valid") else "INVALID"
            lines.append(f"- Validation: {valid_label} (Score: {vs.get('score', 100):.1f}, Errors: {vs.get('error_count', 0)})")

        if alt.refinement_summary:
            rs = alt.refinement_summary
            lines.append(f"- Refinement Trajectory: {rs.get('refinement_status')} across {rs.get('iterations', 0)} iteration(s)")

        if alt.diversity_scores:
            lines.append("- Pairwise Diversity Distances:")
            for other_id, dist in alt.diversity_scores.items():
                lines.append(f"  • Distance to {other_id}: {dist:.3f}")

        return "\n".join(lines)

    @classmethod
    def render_room_explanation(cls, trace: DecisionTrace, room_id: str) -> str:
        """Render an evidence-based lifecycle narrative for a specific room.

        Strictly avoids fabricating uncalculated factors (e.g. sunlight or orientation if not in ASAA).
        """
        chain = trace.get_entity_chain(room_id)
        if not chain:
            # Search by room_type or partial ID
            for c in trace.entity_chains.values():
                if c.entity_id == room_id or c.room_type == room_id:
                    chain = c
                    break

        if not chain:
            return f"No decision trace found for room '{room_id}'."

        rtype = chain.room_type or "Room"
        lines = [f"### Room Lifecycle Narrative: {rtype} (ID: {chain.entity_id})", ""]

        # 1. Requirement Stage
        req_e = chain.requirement_event
        if req_e:
            ev = req_e.evidence
            t_area = ev.get("target_area_sqm", 0.0)
            lines.append(f"1. **Requirement**: User requested {rtype} with target area {t_area:.2f} m².")
            if ev.get("required_adjacency"):
                lines.append(f"   - User required adjacencies: {', '.join(ev['required_adjacency'])}.")
        else:
            lines.append("1. **Requirement**: Implicitly planned or derived program space.")

        # 2. Planning Stage
        plan_e = chain.planning_event
        if plan_e:
            cat = plan_e.evidence.get("category", "functional")
            pri = plan_e.evidence.get("priority", "normal")
            lines.append(f"2. **Planning**: Classified as '{cat}' space with '{pri}' priority.")
            if plan_e.reason:
                lines.append(f"   - Priority rationale: {plan_e.reason}")

        # 3. ASAA Allocation Stage
        asaa_e = chain.allocation_event
        if asaa_e:
            ev = asaa_e.evidence
            alloc_area = ev.get("allocated_area_sqm", 0.0)
            reg_id = ev.get("allocated_region_id", "region")
            dims = ev.get("approximate_dimensions")
            dim_str = f" ({dims[0]:.2f}m × {dims[1]:.2f}m)" if dims else ""
            lines.append(f"3. **Spatial Allocation (ASAA)**: Assigned to Region {reg_id} with {alloc_area:.2f} m²{dim_str}.")

            # Report actual evidence components without fabrication
            factors: list[str] = []
            if "priority" in ev:
                factors.append(f"priority '{ev['priority']}'")
            if "zone_type" in ev:
                factors.append(f"zone type '{ev['zone_type']}'")
            if "orientation_score" in ev:
                factors.append(f"orientation score {ev['orientation_score']}")
            if "relationship_score" in ev:
                factors.append(f"relationship score {ev['relationship_score']}")
            if factors:
                lines.append(f"   - Allocation factors: {', '.join(factors)}.")

        # 4. Architectural Design Stage
        arch_e = chain.architectural_event
        if arch_e:
            ev = arch_e.evidence
            shape = ev.get("intended_shape", "rectangular")
            dims = ev.get("intended_dimensions", [0.0, 0.0])
            rat = arch_e.reason or "Rationale not provided."
            lines.append(f"4. **Architectural Intent**: Designed as a {shape} room with dimensions {dims[0]:.2f}m × {dims[1]:.2f}m.")
            lines.append(f"   - Design rationale: {rat}")

        # 5. Geometry Engine Stage
        geom_e = chain.geometry_event
        if geom_e:
            ev = geom_e.evidence
            u_area = ev.get("usable_area_sqm", 0.0)
            walls = ev.get("walls_count", 0)
            lines.append(f"5. **Physical Geometry**: Constructed {walls}-wall boundary polygon with {u_area:.2f} m² usable interior area.")

        # 6. Validation Findings
        val_events = chain.validation_events
        if val_events:
            issues = [e for e in val_events if e.status in ("error", "warning")]
            if issues:
                lines.append("6. **Validation Findings**:")
                for iss in issues:
                    lines.append(f"   - [{iss.status.upper()}] {iss.reason}")
            else:
                lines.append("6. **Validation**: Room passed all geometric, area, and boundary checks.")

        # 7. Refinement Adjustments
        ref_events = chain.refinement_events
        if ref_events:
            lines.append("7. **Refinement Adjustments**:")
            for ref in ref_events:
                ev = ref.evidence
                field = ev.get("field_changed", "parameter")
                old_val = ev.get("old_value")
                new_val = ev.get("new_value")
                lines.append(f"   - Adjusted {field} from {old_val} to {new_val}. Reason: {ref.reason}")

        return "\n".join(lines)

    @classmethod
    def render_validation_explanation(
        cls, trace: DecisionTrace, floor_number: Optional[int] = None
    ) -> str:
        """Render a structured explanation of validation checks, errors, and warnings."""
        val_events = trace.get_events_by_stage(StageName.VALIDATION)
        if floor_number is not None:
            val_events = [e for e in val_events if e.floor_number == floor_number]

        if not val_events:
            return "No validation events recorded in decision trace."

        passed_checks = [e for e in val_events if e.status == "success"]
        warnings = [e for e in val_events if e.status == "warning"]
        errors = [e for e in val_events if e.status == "error"]

        lines = [
            "# Independent Validation Report",
            f"- Status: {'FAILED' if errors else 'PASSED'}",
            f"- Errors: {len(errors)}",
            f"- Warnings: {len(warnings)}",
            f"- Passed Check Categories: {len(passed_checks)}",
            "",
        ]

        if errors:
            lines.append("## Errors (Must be resolved):")
            for err in errors:
                chk = err.constraints.get("check", "General")
                lines.append(f"- **{chk}**: {err.reason}")
                if err.evidence.get("details"):
                    det = err.evidence["details"]
                    if "expected" in det and "observed" in det:
                        lines.append(f"  • Expected: {det['expected']} | Observed: {det['observed']}")
            lines.append("")

        if warnings:
            lines.append("## Advisory Warnings:")
            for w in warnings:
                chk = w.constraints.get("check", "General")
                lines.append(f"- **{chk}**: {w.reason}")
            lines.append("")

        if passed_checks:
            lines.append("## Passed Check Categories:")
            passed_names = sorted({e.evidence.get("check", "") for e in passed_checks if e.evidence.get("check")})
            lines.append(", ".join(passed_names))

        return "\n".join(lines)

    @classmethod
    def render_refinement_explanation(
        cls, trace: DecisionTrace, alternative_id: Optional[str] = None
    ) -> str:
        """Render a closed-loop narrative explaining iterative refinement changes."""
        ref_events = trace.get_events_by_stage(StageName.REFINEMENT)
        if not ref_events:
            return "No refinement actions required or recorded (design valid on initial pass)."

        lines = [
            "# Refinement & Iterative Correction Narrative",
            f"Total Changes Applied: {len(ref_events)}",
            "",
        ]

        for i, ref in enumerate(ref_events, 1):
            ev = ref.evidence
            field = ev.get("field_changed", "parameter")
            old_v = ev.get("old_value")
            new_v = ev.get("new_value")
            issues = ev.get("validation_issue_ids", [])
            issue_str = f" (Prompted by issue(s): {', '.join(issues)})" if issues else ""

            lines.append(f"### Change {i}: Room '{ref.entity_id}' {field}{issue_str}")
            lines.append(f"- Before: {old_v}")
            lines.append(f"- After: {new_v}")
            lines.append(f"- Decision Rationale: {ref.reason}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def render_diversity_explanation(
        cls, trace: DecisionTrace, alt_id_a: str, alt_id_b: str
    ) -> str:
        """Render an objective pairwise structural comparison between two alternatives.

        Strictly compares canonical DesignSignature features and pairwise distance metrics
        without making subjective quality judgments.
        """
        alt_a = next((a for a in trace.alternatives if a.alternative_id == alt_id_a), None)
        alt_b = next((a for a in trace.alternatives if a.alternative_id == alt_id_b), None)

        if not alt_a or not alt_b:
            return f"Cannot compare: one or both alternatives ('{alt_id_a}', '{alt_id_b}') not found."

        sig_a = alt_a.design_signature or {}
        sig_b = alt_b.design_signature or {}

        dist = alt_a.diversity_scores.get(alt_id_b) or alt_b.diversity_scores.get(alt_id_a, 0.0)

        lines = [
            f"# Structural Diversity Comparison: Alternative {alt_a.index} vs Alternative {alt_b.index}",
            f"- Alternative {alt_a.index}: Strategy '{alt_a.strategy}'",
            f"- Alternative {alt_b.index}: Strategy '{alt_b.strategy}'",
            f"- Pairwise Diversity Distance: {dist:.3f}",
            "",
            "## Structural Feature Comparison:",
        ]

        # 1. Circulation Topology
        circ_a = sig_a.get("circulation_type", "unknown")
        circ_b = sig_b.get("circulation_type", "unknown")
        circ_diff = "DIFFERENT" if circ_a != circ_b else "IDENTICAL"
        lines.append(f"- **Circulation Topology** [{circ_diff}]:")
        lines.append(f"  • Alt {alt_a.index}: {circ_a}")
        lines.append(f"  • Alt {alt_b.index}: {circ_b}")

        # 2. Entrance Room Type
        ent_a = sig_a.get("entrance_room_type", "unknown")
        ent_b = sig_b.get("entrance_room_type", "unknown")
        ent_diff = "DIFFERENT" if ent_a != ent_b else "IDENTICAL"
        lines.append(f"- **Entrance Room** [{ent_diff}]:")
        lines.append(f"  • Alt {alt_a.index}: {ent_a}")
        lines.append(f"  • Alt {alt_b.index}: {ent_b}")

        # 3. Social Sequence
        seq_a = " -> ".join(sig_a.get("social_sequence", [])) or "None"
        seq_b = " -> ".join(sig_b.get("social_sequence", [])) or "None"
        seq_diff = "DIFFERENT" if seq_a != seq_b else "IDENTICAL"
        lines.append(f"- **Social Flow Sequence** [{seq_diff}]:")
        lines.append(f"  • Alt {alt_a.index}: {seq_a}")
        lines.append(f"  • Alt {alt_b.index}: {seq_b}")

        # 4. Private Clustering
        priv_a = sig_a.get("private_clustering", "unknown")
        priv_b = sig_b.get("private_clustering", "unknown")
        priv_diff = "DIFFERENT" if priv_a != priv_b else "IDENTICAL"
        lines.append(f"- **Private Zone Clustering** [{priv_diff}]:")
        lines.append(f"  • Alt {alt_a.index}: {priv_a}")
        lines.append(f"  • Alt {alt_b.index}: {priv_b}")

        # 5. Staircase Relationship
        stair_a = sig_a.get("staircase_relationship", "unknown")
        stair_b = sig_b.get("staircase_relationship", "unknown")
        stair_diff = "DIFFERENT" if stair_a != stair_b else "IDENTICAL"
        lines.append(f"- **Vertical Core Relationship** [{stair_diff}]:")
        lines.append(f"  • Alt {alt_a.index}: {stair_a}")
        lines.append(f"  • Alt {alt_b.index}: {stair_b}")

        return "\n".join(lines)
