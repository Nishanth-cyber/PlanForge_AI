import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NewProjectView } from '../components/views/NewProjectView';

describe('NewProjectView 5-Step Wizard Workflow', () => {
  it('initializes with zero rooms and displays the empty rooms state in Step 3', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Step 1: Plot - verify plot editor is present
    expect(screen.getByText(/Plot Boundary/i)).toBeDefined();

    // Advance to Step 2: Floors
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByText(/Floor Configuration/i)).toBeDefined();

    // Advance to Step 3: Rooms
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByText(/Define the functional room schedule/i)).toBeDefined();

    // Must show empty state
    expect(screen.getByTestId('rooms-empty-state')).toBeDefined();
    expect(screen.getByText(/No rooms added yet/i)).toBeDefined();
    expect(screen.getByTestId('add-first-room-btn')).toBeDefined();
    expect(screen.getByTestId('add-room-btn')).toBeDefined();

    // Room table must NOT be present
    expect(screen.queryByTestId('room-table')).toBeNull();
  });

  it('does NOT create or infer rooms when editing plot dimensions, shape, or floor count', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Step 1: Switch to Rectangle Mode and change dimensions
    fireEvent.click(screen.getByTestId('mode-rectangle'));
    const widthInput = screen.getByTestId('input-width');
    fireEvent.change(widthInput, { target: { value: '60' } });
    const lengthInput = screen.getByTestId('input-length');
    fireEvent.change(lengthInput, { target: { value: '80' } });

    // Step 2: Change floor count to 2 floors
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByTestId('target-floors-2')).toBeDefined();
    fireEvent.click(screen.getByTestId('target-floors-2'));

    // Step 3: Rooms
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    // Rooms must still be completely empty
    expect(screen.getByTestId('rooms-empty-state')).toBeDefined();
    expect(screen.getByText(/No rooms added yet/i)).toBeDefined();
    expect(screen.queryByTestId('room-table')).toBeNull();
  });

  it('gates the Next button and step tabs when rooms list is empty', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Navigate to Step 3: Rooms
    fireEvent.click(screen.getByTestId('wizard-next-btn')); // to step 2
    fireEvent.click(screen.getByTestId('wizard-next-btn')); // to step 3

    // Click Next button while rooms are empty
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    // Should remain on Step 3 and show validation error message
    expect(screen.getByText(/Please add at least one room requirement before continuing/i)).toBeDefined();
    expect(screen.queryByRole('heading', { name: /Spatial Relationships/i })).toBeNull();

    // Trying to click Step 5 tab directly must also be blocked
    fireEvent.click(screen.getByTestId('wizard-step-tab-5'));
    expect(screen.getByText(/Please add at least one room requirement before continuing/i)).toBeDefined();
    expect(screen.queryByText(/Review Project/i)).toBeNull();
  });

  it('allows adding rooms manually, editing parameters, deleting rooms, and progressing', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Navigate to Step 3
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    // Add first room manually via empty-state button
    fireEvent.click(screen.getByTestId('add-first-room-btn'));

    // Empty state should now be gone, and room table should be present
    expect(screen.queryByTestId('rooms-empty-state')).toBeNull();
    const table = screen.getByTestId('room-table');
    expect(table).toBeDefined();

    let rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBe(1);

    // Add second room via header button
    fireEvent.click(screen.getByTestId('add-room-btn'));
    rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBe(2);

    // Change second room to Kitchen
    const secondRowSelect = rows[1].querySelector('select') as HTMLSelectElement;
    fireEvent.change(secondRowSelect, { target: { value: 'Kitchen' } });
    expect(secondRowSelect.value).toBe('Kitchen');

    // Delete first room
    const deleteBtns = screen.getAllByTestId('delete-room-btn');
    fireEvent.click(deleteBtns[0]);
    rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBe(1);

    // Advance to Step 4: Relationships
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByRole('heading', { name: /Spatial Relationships/i })).toBeDefined();

    // Advance to Step 5: Review
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByText(/Review Project/i)).toBeDefined();
    expect(screen.getByTestId('generate-plan-btn')).toBeDefined();

    // Submit generation
    fireEvent.click(screen.getByTestId('generate-plan-btn'));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        project_name: expect.any(String),
        brief: expect.stringContaining('kitchen'),
        num_alternatives: 3,
        enable_refinement: true,
      })
    );
  });

  it('supports explicit preset selection and clearing all rooms', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Navigate to Step 3: Rooms
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    // Select 2BHK preset explicitly
    const presetSelect = screen.getByTestId('room-preset-select');
    fireEvent.change(presetSelect, { target: { value: '2bhk' } });

    // Rooms list should now contain 2BHK rooms (6 rooms)
    expect(screen.queryByTestId('rooms-empty-state')).toBeNull();
    const table = screen.getByTestId('room-table');
    expect(table).toBeDefined();
    const rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBe(6);

    // Clear all rooms
    const clearBtn = screen.getByTestId('clear-rooms-btn');
    fireEvent.click(clearBtn);

    // Returns to empty state
    expect(screen.getByTestId('rooms-empty-state')).toBeDefined();
    expect(screen.getByText(/No rooms added yet/i)).toBeDefined();

    // Attempting to advance is gated again
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    expect(screen.getByText(/Please add at least one room requirement before continuing/i)).toBeDefined();
  });

  it('submits plot_shape array and user-defined rooms for irregular polygon plots', async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <NewProjectView
        onSubmit={onSubmit}
        isLoading={false}
        onCancel={onCancel}
      />
    );

    // Step 3: Add explicit room
    fireEvent.click(screen.getByTestId('wizard-next-btn')); // Step 2
    fireEvent.click(screen.getByTestId('wizard-next-btn')); // Step 3
    fireEvent.click(screen.getByTestId('add-first-room-btn')); // Add Living Room

    // Now go to Step 5 tab
    fireEvent.click(screen.getByTestId('wizard-step-tab-5'));

    // Trigger generate
    const generateBtn = screen.getByTestId('generate-plan-btn');
    fireEvent.click(generateBtn);

    expect(onSubmit).toHaveBeenCalled();
    const submittedPayload = onSubmit.mock.calls[0][0];

    // Plot shape preserved
    expect(submittedPayload.plot_shape).toBeDefined();
    expect(Array.isArray(submittedPayload.plot_shape)).toBe(true);
    expect(submittedPayload.plot_shape.length).toBe(6);
    expect(submittedPayload.plot_shape[0]).toEqual([0, 0]);
    // Brief contains user-defined room
    expect(submittedPayload.brief).toContain('living room');
  });
});
