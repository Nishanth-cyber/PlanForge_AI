import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClarificationPanel } from '../components/chat/ClarificationPanel';
import type { ClarificationRequest } from '../api/types';

describe('ClarificationPanel Component', () => {
  const mockClarification: ClarificationRequest = {
    request_id: 'req_clarify_12345',
    project_id: 'proj_test_01',
    state_version: 3,
    category: 'REQUEST_CONSTRAINT_REVISION',
    question: 'The requested room program exceeds available buildable area by 12.5 m². How would you like to resolve this?',
    evidence: 'Measured required: 72.5 m², buildable: 60.0 m²',
    measured_deficit_sqm: 12.5,
    available_sqm: 60.0,
    required_sqm: 72.5,
    options: [
      {
        option_id: 'opt_expand_plot',
        title: 'Expand Plot Depth',
        description: 'Increase plot length to provide sufficient buildable footprint.',
        feasibility_type: 'verified_feasible',
        affected_rooms: [],
        numeric_changes: { plot_length: 15.0 },
        requires_confirmation: true,
      },
      {
        option_id: 'opt_add_floor',
        title: 'Add Second Floor',
        description: 'Distribute bedrooms across 2 floors.',
        feasibility_type: 'suggested_alternative',
        affected_rooms: [],
        numeric_changes: { target_floors: 2 },
        requires_confirmation: true,
      },
      {
        option_id: 'opt_remove_optional',
        title: 'Remove Optional Study',
        description: 'Remove study to fit within boundary.',
        feasibility_type: 'unverified_hypothetical',
        affected_rooms: ['study'],
        numeric_changes: {},
        requires_confirmation: true,
      },
    ],
    allow_free_text: true,
    allow_numeric_input: true,
    affected_constraints: ['plot_boundary'],
    is_mandatory: true,
    created_at: new Date().toISOString(),
    status: 'pending',
  };

  it('renders question, measured deficits, and options with clear feasibility distinction', () => {
    render(
      <ClarificationPanel
        projectId="proj_test_01"
        clarification={mockClarification}
        onSubmitResponse={vi.fn()}
      />
    );

    expect(screen.getByText(/Agentic Clarification Required/i)).toBeDefined();
    expect(screen.getByText(/The requested room program exceeds available buildable area/i)).toBeDefined();
    expect(screen.getByText('-12.5 m²')).toBeDefined();

    // Verify badges
    expect(screen.getByText(/✓ Verified Feasible/i)).toBeDefined();
    expect(screen.getByText(/💡 Suggested Alternative/i)).toBeDefined();
    expect(screen.getByText(/⚡ Unverified Hypothetical/i)).toBeDefined();
  });

  it('allows selecting an alternative and submitting user choice', async () => {
    const handleSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ClarificationPanel
        projectId="proj_test_01"
        clarification={mockClarification}
        onSubmitResponse={handleSubmit}
      />
    );

    const secondOption = screen.getByTestId('clarification-option-opt_add_floor');
    fireEvent.click(secondOption);

    const submitBtn = screen.getByTestId('clarification-submit-btn');
    fireEvent.click(submitBtn);

    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith(
      'opt_add_floor',
      undefined,
      expect.objectContaining({ target_floors: 2 })
    );
  });

  it('allows free-text submission and cancel action', async () => {
    const handleSubmit = vi.fn().mockResolvedValue(undefined);
    const handleCancel = vi.fn().mockResolvedValue(undefined);

    render(
      <ClarificationPanel
        projectId="proj_test_01"
        clarification={mockClarification}
        onSubmitResponse={handleSubmit}
        onCancel={handleCancel}
      />
    );

    const freeTextInput = screen.getByTestId('clarification-free-text');
    fireEvent.change(freeTextInput, { target: { value: 'Make bedrooms 12 sqm each.' } });

    const cancelBtn = screen.getByTestId('clarification-cancel-btn');
    fireEvent.click(cancelBtn);
    expect(handleCancel).toHaveBeenCalledTimes(1);

    const submitBtn = screen.getByTestId('clarification-submit-btn');
    fireEvent.click(submitBtn);
    expect(handleSubmit).toHaveBeenCalledWith(
      'opt_expand_plot',
      'Make bedrooms 12 sqm each.',
      undefined
    );
  });
});
