import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NewProjectView } from '../components/views/NewProjectView';
import { FloorPlanCanvas } from '../components/floorplan/FloorPlanCanvas';
import { RoomInspector } from '../components/floorplan/RoomInspector';
import { FloorPlanWorkspace } from '../components/chat/FloorPlanWorkspace';
import { TabNav } from '../components/layout/TabNav';
import { getValidationDisplayStatus } from '../utils/validationStatus';
import type {
  FloorPlanSet,
  GeoRoom,
  GenerationRequest,
  ProjectData,
} from '../api/types';

describe('Phase 5 User Journey & Frontend-Backend Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Test 1: New project starts with zero rooms
  it('Test 1: New project starts with zero rooms', () => {
    const onSubmit = vi.fn();
    render(<NewProjectView onSubmit={onSubmit} isLoading={false} onCancel={vi.fn()} />);

    // Step 1: Plot -> Step 2: Floors -> Step 3: Rooms
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    expect(screen.getByTestId('rooms-empty-state')).toBeDefined();
    expect(screen.getByText(/No rooms added yet/i)).toBeDefined();
    expect(screen.queryByTestId('room-table')).toBeNull();
  });

  // Test 2: Generate remains disabled until requirements are complete
  it('Test 2: Generate remains disabled or gates step progression until rooms are defined', () => {
    const onSubmit = vi.fn();
    render(<NewProjectView onSubmit={onSubmit} isLoading={false} onCancel={vi.fn()} />);

    // Attempting to jump directly to Step 5 (Review) when rooms are empty should be blocked
    fireEvent.click(screen.getByTestId('wizard-step-tab-5'));

    // Should stay or redirect to Step 3 with validation error
    expect(screen.getByText(/Please add at least one room requirement before continuing/i)).toBeDefined();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  // Test 3: Generate becomes enabled after confirmation
  it('Test 3: Generate becomes enabled after rooms are added and review is reached', () => {
    const onSubmit = vi.fn();
    render(<NewProjectView onSubmit={onSubmit} isLoading={false} onCancel={vi.fn()} />);

    // Step 1 -> Step 2 -> Step 3
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    // Add a room in Step 3
    fireEvent.click(screen.getByTestId('add-room-btn'));
    expect(screen.getByTestId('room-table')).toBeDefined();

    // Advance to Step 4 (Relationships) -> Step 5 (Review)
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    const genBtn = screen.getByTestId('generate-plan-btn');
    expect(genBtn).toBeDefined();
    fireEvent.click(genBtn);

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  // Test 4: Correct API request is sent
  it('Test 4: Correct API request is sent with plot and room configuration', () => {
    const onSubmit = vi.fn();
    render(<NewProjectView onSubmit={onSubmit} isLoading={false} onCancel={vi.fn()} />);

    // Set project name
    const nameInput = screen.getByTestId('input-project-name');
    fireEvent.change(nameInput, { target: { value: 'Phase 5 Test Villa' } });

    // Step 1: Set rectangular plot 40 x 50 ft
    fireEvent.click(screen.getByTestId('mode-rectangle'));
    fireEvent.change(screen.getByTestId('input-width'), { target: { value: '40' } });
    fireEvent.change(screen.getByTestId('input-length'), { target: { value: '50' } });

    // Advance to Floors
    fireEvent.click(screen.getByTestId('wizard-next-btn'));

    // Advance to Rooms and add a room
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('add-room-btn'));

    // Advance to Review and submit
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('wizard-next-btn'));
    fireEvent.click(screen.getByTestId('generate-plan-btn'));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const sentReq: GenerationRequest = onSubmit.mock.calls[0][0];
    expect(sentReq.project_name).toBe('Phase 5 Test Villa');
    expect(sentReq.enable_refinement).toBe(true);
    expect(sentReq.brief).toContain('40');
    expect(sentReq.brief).toContain('50');
  });

  // Test 5: Final backend floor plan renders in UI
  it('Test 5: Final backend floor plan renders in FloorPlanCanvas', () => {
    const mockFloorPlan = {
      id: 'fp_1',
      project_name: 'Test Project',
      floor_number: 1,
      geometry: {
        rooms: [
          {
            id: 'room_living',
            room_type: 'living',
            usable_polygon: [[2, 2], [8, 2], [8, 8], [2, 8]] as [number, number][],
            built_polygon: [[2, 2], [8, 2], [8, 8], [2, 8]] as [number, number][],
            area_sqm: 36.0,
            floor_number: 1,
            doors: [],
            windows: [],
            is_corridor: false,
            architectural_room_id: 'arch_r1',
            walls: ['w1', 'w2', 'w3', 'w4'],
          },
        ],
        walls: [],
        doors: [],
        windows: [],
        staircases: [],
      },
      validation: undefined,
      is_valid: true,
      metadata: {},
      notes: '',
    };

    render(
      <FloorPlanCanvas
        floorPlan={mockFloorPlan}
        plotBoundary={[[0, 0], [10, 0], [10, 10], [0, 10]]}
        buildableBoundary={[[1, 1], [9, 1], [9, 9], [1, 9]]}
        selectedRoom={null}
        onSelectRoom={vi.fn()}
        projectId="proj_test"
        theme="light"
      />
    );

    // FloorPlanCanvas SVG should be rendered with plot boundary and room
    expect(screen.getByText(/living/i)).toBeDefined();
    expect(screen.getByText(/36\.0 m²/i)).toBeDefined();
  });

  // Test 6: Multi-floor geometry remains separated
  it('Test 6: Multi-floor geometry remains separated and floor switcher works', () => {
    const onSelectFloor = vi.fn();
    const mockFloorPlanSet: FloorPlanSet = {
      id: 'fps_multi',
      project_name: 'Multi Floor Residence',
      plot_boundary: [[0, 0], [12, 0], [12, 12], [0, 12]],
      buildable_boundary: [[1, 1], [11, 1], [11, 11], [1, 11]],
      floor_plans: [
        {
          id: 'fp_1',
          project_name: 'Multi',
          floor_number: 1,
          geometry: {
            rooms: [
              {
                id: 'r_living',
                room_type: 'living',
                usable_polygon: [[2, 2], [6, 2], [6, 6], [2, 6]] as [number, number][],
                built_polygon: [[2, 2], [6, 2], [6, 6], [2, 6]] as [number, number][],
                area_sqm: 16.0,
                floor_number: 1,
                doors: [],
                windows: [],
                is_corridor: false,
                architectural_room_id: 'a1',
                walls: [],
              },
            ],
            walls: [],
            doors: [],
            windows: [],
            staircases: [],
          },
          is_valid: true,
          metadata: {},
          notes: '',
        },
        {
          id: 'fp_2',
          project_name: 'Multi',
          floor_number: 2,
          geometry: {
            rooms: [
              {
                id: 'r_bed',
                room_type: 'bedroom',
                usable_polygon: [[2, 2], [6, 2], [6, 6], [2, 6]] as [number, number][],
                built_polygon: [[2, 2], [6, 2], [6, 6], [2, 6]] as [number, number][],
                area_sqm: 16.0,
                floor_number: 2,
                doors: [],
                windows: [],
                is_corridor: false,
                architectural_room_id: 'a2',
                walls: [],
              },
            ],
            walls: [],
            doors: [],
            windows: [],
            staircases: [],
          },
          is_valid: true,
          metadata: {},
          notes: '',
        },
      ],
      generation_metadata: {},
    };

    const mockProjectData: ProjectData = {
      project_id: 'proj_multi',
      floor_plan_set: mockFloorPlanSet,
      project_metadata: {
        project_id: 'proj_multi',
        project_name: 'Multi Floor Residence',
        exported_at: '2026-10-06T12:00:00',
        schema_version: '1.0',
      },
      validation_report: {
        id: 'val_1',
        results: [],
        iteration: 0,
        overall_valid: true,
        overall_score: 100,
        total_errors: 0,
        total_warnings: 0,
      },
    };

    render(
      <FloorPlanWorkspace
        isGenerating={false}
        projectData={mockProjectData}
        generationResponse={null}
        activeFloor={1}
        onSelectFloor={onSelectFloor}
        selectedAlternativeIndex={1}
        onSelectAlternative={vi.fn()}
        selectedRoom={null}
        onSelectRoom={vi.fn()}
      />
    );

    // Floor 1 rooms visible
    expect(screen.getByText(/living/i)).toBeDefined();
    expect(screen.queryByText(/bedroom/i)).toBeNull();

    // Floor switcher button for Floor 2 is present and triggers onSelectFloor
    const floor2Btn = screen.getByRole('button', { name: /Floor 2/i });
    expect(floor2Btn).toBeDefined();
    fireEvent.click(floor2Btn);
    expect(onSelectFloor).toHaveBeenCalledWith(2);
  });

  // Test 7: Invalid backend response is shown as invalid
  it('Test 7: Invalid backend response is shown as PLAN COULD NOT BE VALIDATED', () => {
    const invalidReport = {
      overall_valid: false,
      total_errors: 2,
      results: [{ is_valid: false, issues: [{ severity: 'error' }, { severity: 'error' }] }],
    };

    const status = getValidationDisplayStatus(invalidReport, null, 'unresolved');
    expect(status.label).toBe('PLAN COULD NOT BE VALIDATED');
    expect(status.type).toBe('invalid');

    render(
      <TabNav
        projectName="Invalid Villa"
        projectId="proj_inv"
        statusLabel={status.label}
        statusBadgeClass={status.badgeClass}
        activeTab="overview"
        onTabChange={vi.fn()}
      />
    );

    expect(screen.getByText('PLAN COULD NOT BE VALIDATED')).toBeDefined();
  });

  // Test 8: Infeasible response is shown as infeasible
  it('Test 8: Infeasible response is shown as REQUIREMENTS ARE INFEASIBLE', () => {
    const infeasibleRefinement = {
      iterations: [],
      status: 'infeasible_under_constraints',
      total_iterations: 0,
    };

    const status = getValidationDisplayStatus(null, infeasibleRefinement, 'failed');
    expect(status.label).toBe('REQUIREMENTS ARE INFEASIBLE');
    expect(status.type).toBe('infeasible');

    render(
      <TabNav
        projectName="Infeasible Plot"
        projectId="proj_inf"
        statusLabel={status.label}
        statusBadgeClass={status.badgeClass}
        activeTab="overview"
        onTabChange={vi.fn()}
      />
    );

    expect(screen.getByText('REQUIREMENTS ARE INFEASIBLE')).toBeDefined();
  });

  // Test 9: API failure does not display success
  it('Test 9: getValidationDisplayStatus never reports success on error or failed status', () => {
    // Both validation errors and failure status must never result in 'valid'
    const statusWithFailure = getValidationDisplayStatus(
      { overall_valid: false, total_errors: 1 },
      null,
      'failed'
    );
    expect(statusWithFailure.type).not.toBe('valid');
    expect(statusWithFailure.type).not.toBe('refined');

    const statusUnresolved = getValidationDisplayStatus(
      { overall_valid: false, total_errors: 1 },
      { iterations: [{}], status: 'no_change', total_iterations: 1 },
      'unresolved'
    );
    expect(statusUnresolved.label).toBe('PLAN COULD NOT BE VALIDATED');
    expect(statusUnresolved.type).toBe('invalid');
  });

  // Test 10: Real LLM metadata is represented correctly
  it('Test 10: Valid refined design distinguishes VALID — REFINED from VALID FLOOR PLAN', () => {
    // Valid on initial pass
    const initialValid = getValidationDisplayStatus(
      { overall_valid: true, total_errors: 0 },
      { iterations: [{}], status: 'valid_on_initial_pass', total_iterations: 0 },
      'completed'
    );
    expect(initialValid.label).toBe('VALID FLOOR PLAN');
    expect(initialValid.type).toBe('valid');

    // Valid after 2 refinement passes
    const refinedValid = getValidationDisplayStatus(
      { overall_valid: true, total_errors: 0 },
      { iterations: [{}, {}], status: 'converged', total_iterations: 2 },
      'completed'
    );
    expect(refinedValid.label).toBe('VALID — REFINED');
    expect(refinedValid.type).toBe('refined');
  });

  // Test 11: Irregular plot geometry is displayed correctly
  it('Test 11: Irregular plot geometry is rendered with polygon in FloorPlanCanvas', () => {
    const irregularVertices: [number, number][] = [
      [0, 0],
      [20, 0],
      [20, 10],
      [10, 10],
      [10, 20],
      [0, 20],
    ];

    const mockFloorPlan = {
      id: 'fp_l',
      project_name: 'L-Shaped Villa',
      floor_number: 1,
      geometry: {
        rooms: [],
        walls: [],
        doors: [],
        windows: [],
        staircases: [],
      },
      is_valid: true,
      metadata: {},
      notes: '',
    };

    const { container } = render(
      <FloorPlanCanvas
        floorPlan={mockFloorPlan}
        plotBoundary={irregularVertices}
        buildableBoundary={irregularVertices}
        selectedRoom={null}
        onSelectRoom={vi.fn()}
        projectId="proj_l"
        theme="light"
      />
    );

    // Verify SVG contains polygon paths for irregular plot boundary
    const polygonElements = container.querySelectorAll('polygon, path');
    expect(polygonElements.length).toBeGreaterThan(0);
  });

  // Test 12: Room inspector displays backend-derived values
  it('Test 12: Room inspector displays backend-derived values without recalculation', () => {
    const mockRoom: GeoRoom = {
      id: 'room_master_bed',
      room_type: 'bedroom',
      usable_polygon: [[2, 2], [6, 2], [6, 5], [2, 5]],
      built_polygon: [[2, 2], [6, 2], [6, 5], [2, 5]],
      area_sqm: 12.0,
      floor_number: 1,
      doors: [],
      windows: [],
      is_corridor: false,
      architectural_room_id: 'arch_master_bed',
      walls: ['w_1', 'w_2'],
    };

    render(
      <RoomInspector
        room={mockRoom}
        geometry={null}
        validationResult={undefined}
        onClose={vi.fn()}
      />
    );

    // Inspect backend-derived exact values
    expect(screen.getByText(/arch_master_bed/i)).toBeDefined();
    expect(screen.getByText(/12\.00/i)).toBeDefined(); // area_sqm displayed directly
  });
});
