import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ValidationView } from '../components/views/ValidationView';
import { AlternativesView } from '../components/views/AlternativesView';
import { ExplainabilityView } from '../components/views/ExplainabilityView';
import { RefinementView } from '../components/views/RefinementView';
import { ExportView } from '../components/views/ExportView';
import type { ValidationReport, DesignAlternative, DecisionTrace, RefinementResult } from '../api/types';

describe('PlanForge Web UI — Research Views', () => {
  it('renders ValidationView with hard error / warning counts and check groups', () => {
    const mockReport: ValidationReport = {
      id: 'val_01',
      overall_valid: true,
      overall_score: 96.5,
      total_errors: 0,
      total_warnings: 1,
      iteration: 1,
      results: [
        {
          id: 'res_01',
          floor_number: 1,
          is_valid: true,
          score: 96.5,
          checks_passed: ['boundary', 'overlap', 'dimension'],
          checks_failed: [],
          checks_warned: ['window'],
          issues: [
            {
              id: 'iss_01',
              floor_number: 1,
              severity: 'warning',
              category: 'window',
              rule_name: 'WINDOW_DAYLIGHT',
              description: 'Powder room lacks direct exterior daylight opening.',
            },
          ],
        },
      ],
    };

    render(<ValidationView validationReport={mockReport} />);

    expect(screen.getByText(/Hard Errors/i)).toBeDefined();
    expect(screen.getAllByText(/Warnings/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Boundary Containment/i)).toBeDefined();
    expect(screen.getByText(/Powder room lacks direct exterior daylight opening/i)).toBeDefined();
  });

  it('renders AlternativesView neutrally without best or winner claims', () => {
    const mockAlts: DesignAlternative[] = [
      {
        alternative_id: 'alt_01',
        index: 1,
        strategy: 'social_centric',
        status: 'validated',
        is_valid: true,
        characteristics: ['Open social living', 'Direct garden access'],
        diversity_scores: { alt_02: 0.35 },
      },
      {
        alternative_id: 'alt_02',
        index: 2,
        strategy: 'privacy_centric',
        status: 'validated',
        is_valid: true,
        characteristics: ['Buffer vestibule', 'Acoustic zoning'],
        diversity_scores: { alt_01: 0.35 },
      },
    ];

    render(
      <AlternativesView
        alternatives={mockAlts}
        projectId="proj_test"
        selectedAlternativeIndex={1}
        onSelectAlternative={vi.fn()}
        onViewFloorPlan={vi.fn()}
      />
    );

    expect(screen.getAllByText(/Alternative 1/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Alternative 2/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Social Centric Strategy/i)).toBeDefined();
    expect(screen.getByText(/Privacy Centric Strategy/i)).toBeDefined();
    expect(screen.getByText(/Structural Diversity Comparison Matrix/i)).toBeDefined();

    // Verify absence of biased ranking badges or winner designations
    expect(screen.queryByText(/^Winner$/i)).toBeNull();
    expect(screen.queryByText(/^Best Alternative$/i)).toBeNull();
    expect(screen.queryByText(/^Recommended$/i)).toBeNull();
  });

  it('renders RefinementView showing error reduction and iterations', () => {
    const mockRefine: RefinementResult = {
      id: 'ref_01',
      status: 'valid_after_refinement',
      is_valid: true,
      total_iterations: 2,
      termination_reason: 'converged',
      iterations: [
        {
          iteration: 0,
          design_version: 0,
          error_count: 1,
          warning_count: 2,
          score: 85.0,
          overall_valid: false,
          validation_status: 'failed',
          changes: [],
        },
        {
          iteration: 1,
          design_version: 1,
          error_count: 0,
          warning_count: 1,
          score: 98.0,
          overall_valid: true,
          validation_status: 'valid',
          changes: [
            {
              id: 'ch_01',
              room_id: 'room_bed_01',
              field_changed: 'dimensions',
              old_value: [3, 2],
              new_value: [4, 3],
              reason: 'Resolved room aspect ratio violation',
              floor_number: 1,
            },
          ],
        },
      ],
      changes: [],
    };

    render(<RefinementView refinementResult={mockRefine} />);

    expect(screen.getByText(/Closed-Loop Validation-Driven Refinement/i)).toBeDefined();
    expect(screen.getByText(/Hard Errors Resolved/i)).toBeDefined();
    expect(screen.getByText(/Initial Architectural Proposal/i)).toBeDefined();
    expect(screen.getByText(/Resolved room aspect ratio violation/i)).toBeDefined();
  });

  it('renders ExplainabilityView showing provenance and stages', () => {
    const mockTrace: DecisionTrace = {
      trace_id: 'tr_01',
      project_id: 'proj_test',
      stages: [
        {
          stage_name: 'planning',
          summary: 'Derived 4 functional room specifications from user brief.',
          events: [
            {
              event_id: 'ev_01',
              timestamp: '2026-09-19T10:00:00',
              stage: 'planning',
              event_type: 'priority_assigned',
              source: 'planning_agent',
              reason: 'Living room categorized as primary social core with high priority.',
              evidence: { priority: 'high' },
              constraints: {},
              status: 'success',
            },
          ],
        },
      ],
      entity_chains: {},
    };

    render(<ExplainabilityView decisionTrace={mockTrace} />);

    expect(screen.getByText(/Explainability & Decision Trace System/i)).toBeDefined();
    expect(screen.getByText(/Planning Stage/i)).toBeDefined();
    expect(screen.getByText(/Living room categorized as primary social core/i)).toBeDefined();
  });

  it('renders ExplainabilityView with human-readable stage names, empty room trace message, and handles zero events', () => {
    const mockTrace: DecisionTrace = {
      trace_id: 'tr_02',
      project_id: 'proj_test',
      stages: [
        {
          stage_name: 'ASAA_ALLOCATION',
          summary: 'Space allocated via spatial partitioner.',
          events: [],
        },
        {
          stage_name: 'ARCHITECTURAL_DESIGN',
          summary: 'Architectural layout generated.',
          events: [],
        },
      ],
      entity_chains: {},
    };

    render(<ExplainabilityView decisionTrace={mockTrace} />);

    // Issue 4 & 5: Human-readable stage titles and subtitles
    expect(screen.getByText(/ASAA Allocation Stage/i)).toBeDefined();
    expect(screen.getByText(/Architectural Design Stage/i)).toBeDefined();
    expect(screen.getAllByText(/No events recorded/i).length).toBeGreaterThanOrEqual(1);

    // Issue 6: Empty state for room trace
    expect(screen.getByText(/Select a room to view its lifecycle trace/i)).toBeDefined();
  });

  it('renders ExportView with download buttons and bundle inventory', () => {
    render(<ExportView projectId="proj_test" />);

    expect(screen.getByText(/Publication Exports & Project Artifacts/i)).toBeDefined();
    expect(screen.getByText(/Download Floor 1 PNG/i)).toBeDefined();
    expect(screen.getByText(/Download project.json/i)).toBeDefined();
    expect(screen.getByText(/Download summary.md/i)).toBeDefined();
  });
});
