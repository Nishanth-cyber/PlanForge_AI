import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NewProjectView } from '../components/views/NewProjectView';

describe('NewProjectView 5-Step Wizard Workflow', () => {
  it('navigates through the 5 steps and triggers generation', async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Step 1: Plot
    expect(screen.getByText(/Plot Boundary/i)).toBeDefined();
    expect(screen.getByTestId('input-project-name')).toBeDefined();
    expect(screen.getByTestId('plot-editor')).toBeDefined();

    // Advance to Step 2: Floors
    const nextBtn = screen.getByTestId('wizard-next-btn');
    fireEvent.click(nextBtn);

    expect(screen.getByText(/Floor Configuration/i)).toBeDefined();
    expect(screen.getByTestId('target-floors-2')).toBeDefined();

    // Select 2 floors
    fireEvent.click(screen.getByTestId('target-floors-2'));

    // Advance to Step 3: Rooms
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByText(/Define the functional room schedule/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /\+ Add Room/i })).toBeDefined();

    // Advance to Step 4: Relationships
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByRole('heading', { name: /Spatial Relationships/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /\+ Required/i })).toBeDefined();

    // Advance to Step 5: Review
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByText(/Review Project/i)).toBeDefined();
    expect(screen.getByTestId('generate-plan-btn')).toBeDefined();

    // Click Generate Button
    fireEvent.click(screen.getByTestId('generate-plan-btn'));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        project_name: expect.any(String),
        brief: expect.stringContaining('residence'),
        num_alternatives: 3,
        enable_refinement: true,
      })
    );
  });

  it('submits plot_shape array of meter coordinates for irregular polygon plots', async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Click directly on Step 5 tab (Review)
    const step5Tab = screen.getByTestId('wizard-step-tab-5');
    fireEvent.click(step5Tab);

    // Trigger generate
    const generateBtn = screen.getByTestId('generate-plan-btn');
    fireEvent.click(generateBtn);

    expect(onSubmit).toHaveBeenCalled();
    const submittedPayload = onSubmit.mock.calls[0][0];

    // Default plot is irregular with 6 vertices
    expect(submittedPayload.plot_shape).toBeDefined();
    expect(Array.isArray(submittedPayload.plot_shape)).toBe(true);
    expect(submittedPayload.plot_shape.length).toBe(6);
    expect(submittedPayload.plot_shape[0]).toEqual([0, 0]);
  });

  it('updates compiled brief and submitted payload when plot dimensions are edited in Step 1', async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Step 1: Switch to Rectangle Mode
    fireEvent.click(screen.getByTestId('mode-rectangle'));

    // Edit Width to 45 and Length to 55
    const widthInput = screen.getByTestId('input-width');
    fireEvent.change(widthInput, { target: { value: '45' } });

    const lengthInput = screen.getByTestId('input-length');
    fireEvent.change(lengthInput, { target: { value: '55' } });

    // Navigate to Step 5: Review
    fireEvent.click(screen.getByTestId('wizard-step-tab-5'));

    // Expand compiled brief
    const toggleBrief = screen.getByRole('button', { name: /View \/ Edit Compiled Brief/i });
    fireEvent.click(toggleBrief);

    const briefTextarea = screen.getByTestId('brief-textarea') as HTMLTextAreaElement;
    expect(briefTextarea.value).toContain('45');
    expect(briefTextarea.value).toContain('55');

    // Trigger generate
    fireEvent.click(screen.getByTestId('generate-plan-btn'));

    expect(onSubmit).toHaveBeenCalled();
    const submitted = onSubmit.mock.calls[0][0];
    expect(submitted.brief).toContain('45');
    expect(submitted.brief).toContain('55');
  });
});
