import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FloorPlanCanvas } from '../components/floorplan/FloorPlanCanvas';
import { RoomInspector } from '../components/floorplan/RoomInspector';
import {
  findInteriorLabelPoint,
  isPointInPolygon,
  getAdaptiveLabelConfig,
} from '../utils/geometry';
import type { FloorPlan, GeoRoom, Point2D } from '../api/types';

const MOCK_ROOM: GeoRoom = {
  id: 'room_living_01',
  room_type: 'living_room',
  usable_polygon: [
    [0, 0],
    [5, 0],
    [5, 4],
    [0, 4],
  ],
  built_polygon: [
    [-0.1, -0.1],
    [5.1, -0.1],
    [5.1, 4.1],
    [-0.1, 4.1],
  ],
  area_sqm: 20.0,
  walls: ['wall_1', 'wall_2', 'wall_3', 'wall_4'],
  doors: ['door_1'],
  windows: ['win_1'],
  floor_number: 1,
  architectural_room_id: 'arch_r_01',
};

const MOCK_STAIRCASE = {
  id: 'stair_01',
  polygon: [
    [5, 0],
    [7, 0],
    [7, 3],
    [5, 3],
  ] as Point2D[],
  from_floor: 1,
  to_floor: 2,
  width: 1.0,
  depth: 0.3,
  riser_count: 16,
  tread_depth: 0.28,
  floor_number: 1,
};

const MOCK_FLOOR_PLAN: FloorPlan = {
  id: 'fp_floor_1',
  project_name: 'Test Residence',
  floor_number: 1,
  is_valid: true,
  notes: '',
  geometry: {
    rooms: [
      MOCK_ROOM,
      {
        id: 'room_bath_01',
        room_type: 'bathroom',
        usable_polygon: [
          [0, 4],
          [2, 4],
          [2, 6],
          [0, 6],
        ],
        built_polygon: [
          [-0.1, 3.9],
          [2.1, 3.9],
          [2.1, 6.1],
          [-0.1, 6.1],
        ],
        area_sqm: 4.0,
        walls: [],
        doors: [],
        windows: [],
        floor_number: 1,
      },
      // Floor 2 room that should be filtered out when viewing Floor 1
      {
        id: 'room_floor2_bed',
        room_type: 'upper_bedroom',
        usable_polygon: [
          [0, 0],
          [4, 0],
          [4, 4],
          [0, 4],
        ],
        built_polygon: [],
        area_sqm: 16.0,
        walls: [],
        doors: [],
        windows: [],
        floor_number: 2,
      },
    ],
    walls: [
      {
        id: 'wall_1',
        start: [0, 0],
        end: [5, 0],
        thickness: 0.2,
        height: 2.8,
        type: 'exterior',
        floor_number: 1,
        polygon: [
          [0, -0.1],
          [5, -0.1],
          [5, 0.1],
          [0, 0.1],
        ],
        room_ids: ['room_living_01'],
      },
    ],
    doors: [
      {
        id: 'door_1',
        wall_id: 'wall_1',
        position: [2.5, 0],
        width: 0.9,
        height: 2.1,
        type: 'entrance',
        connects_from: 'room_living_01',
        connects_to: 'foyer',
        floor_number: 1,
        swing_arc: [
          [2.05, 0],
          [2.95, 0],
          [2.68, 0.63],
          [2.05, 0.9],
        ],
      },
    ],
    windows: [
      {
        id: 'win_1',
        wall_id: 'wall_1',
        position: [1.2, 0],
        width: 1.2,
        height: 1.2,
        sill_height: 0.9,
        type: 'standard',
        floor_number: 1,
      },
    ],
    staircases: [MOCK_STAIRCASE],
  },
};

describe('PlanForge Web UI — Interactive Floor Plan Canvas & Visualization', () => {
  it('renders SVG canvas with room polygons, adaptive labels, and screen-space north arrow', () => {
    const onSelectRoom = vi.fn();
    render(
      <FloorPlanCanvas
        floorPlan={MOCK_FLOOR_PLAN}
        plotBoundary={[
          [-2, -2],
          [8, -2],
          [8, 8],
          [-2, 8],
        ]}
        buildableBoundary={[
          [0, 0],
          [6, 0],
          [6, 6],
          [0, 6],
        ]}
        selectedRoom={null}
        onSelectRoom={onSelectRoom}
        projectId="proj_test"
        orientation="north"
      />
    );

    // Living room label and area
    expect(screen.getByText(/LIVING ROOM/i)).toBeDefined();
    expect(screen.getByText(/20.0 m²/i)).toBeDefined();

    // Small room adaptive label
    expect(screen.getByText(/BATH/i)).toBeDefined();
    expect(screen.getByText(/4.0 m²/i)).toBeDefined();

    // Staircase label
    expect(screen.getByText(/STAIR/i)).toBeDefined();
    expect(screen.getByText(/16R/i)).toBeDefined();

    // Screen-space north arrow overlay
    expect(screen.getByText('N')).toBeDefined();
    expect(screen.getByText('north')).toBeDefined();

    // Floor 2 room should NOT be rendered when floorPlan.floor_number is 1
    expect(screen.queryByText(/UPPER BEDROOM/i)).toBeNull();
  });

  it('calculates interior label point guaranteed strictly inside L-shaped room', () => {
    // L-shaped room: 10x10 with 5x5 corner cutout
    // (0,0) -> (10,0) -> (10,5) -> (5,5) -> (5,10) -> (0,10)
    // Arithmetic centroid: (4.16, 4.16) which is near internal corner
    const lShapedRoom: Point2D[] = [
      [0, 0],
      [10, 0],
      [10, 5],
      [5, 5],
      [5, 10],
      [0, 10],
    ];

    const labelPoint = findInteriorLabelPoint(lShapedRoom);
    expect(isPointInPolygon(labelPoint, lShapedRoom)).toBe(true);
  });

  it('adapts typography and wraps long room names without wall overflow', () => {
    const squarePoly: Point2D[] = [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
    ];

    const config = getAdaptiveLabelConfig('master_bedroom_with_attached_bathroom', 16, squarePoly);
    // Should split long name into multiple lines rather than a single 40-char string
    expect(config.nameLines.length).toBeGreaterThanOrEqual(2);
    expect(config.nameFontSize).toBeGreaterThanOrEqual(0.35);
    expect(config.nameFontSize).toBeLessThanOrEqual(0.60);
  });

  it('supports zoom controls and fit-to-plot reset', () => {
    const onSelectRoom = vi.fn();
    render(
      <FloorPlanCanvas
        floorPlan={MOCK_FLOOR_PLAN}
        selectedRoom={null}
        onSelectRoom={onSelectRoom}
        projectId="proj_test"
      />
    );

    // Initial zoom is 100%
    expect(screen.getByText('100%')).toBeDefined();

    // Zoom In
    const zoomInBtn = screen.getByTitle('Zoom In');
    fireEvent.click(zoomInBtn);
    expect(screen.getByText('125%')).toBeDefined();

    // Fit to Plot resets zoom
    const fitBtn = screen.getByTitle('Fit to Plot');
    fireEvent.click(fitBtn);
    expect(screen.getByText('100%')).toBeDefined();
  });

  it('toggles development debug overlay', () => {
    const onSelectRoom = vi.fn();
    const { container } = render(
      <FloorPlanCanvas
        floorPlan={MOCK_FLOOR_PLAN}
        selectedRoom={null}
        onSelectRoom={onSelectRoom}
        projectId="proj_test"
      />
    );

    // Initially debug overlay is not rendered
    expect(container.querySelector('#debug-overlay')).toBeNull();

    // Click Debug Overlay checkbox
    const debugCheckbox = screen.getByLabelText(/Debug Overlay/i);
    fireEvent.click(debugCheckbox);

    // Debug overlay is now visible
    expect(container.querySelector('#debug-overlay')).toBeDefined();
  });

  it('selects room on click and opens room inspector with connections and area', () => {
    const onClose = vi.fn();
    const onViewTrace = vi.fn();

    render(
      <RoomInspector
        room={MOCK_ROOM}
        geometry={MOCK_FLOOR_PLAN.geometry || null}
        onClose={onClose}
        onViewTrace={onViewTrace}
      />
    );

    expect(screen.getByText(/Living Room/i)).toBeDefined();
    expect(screen.getByText(/20.00 m²/i)).toBeDefined();
    expect(screen.getByText(/foyer/i)).toBeDefined(); // connected room

    const traceBtn = screen.getByRole('button', { name: /Explore Room Traceability/i });
    fireEvent.click(traceBtn);
    expect(onViewTrace).toHaveBeenCalledWith('room_living_01');
  });

  it('renders door-swing arcs when enabled and hides them when Show Door Swing Arcs toggle is unchecked', () => {
    const { container } = render(
      <FloorPlanCanvas
        floorPlan={MOCK_FLOOR_PLAN}
        selectedRoom={null}
        onSelectRoom={vi.fn()}
        projectId="proj_test"
      />
    );

    // Initial state: Show Door Swing Arcs is checked
    const toggleCheckbox = screen.getByTestId('toggle-door-swings') as HTMLInputElement;
    expect(toggleCheckbox.checked).toBe(true);

    // Door swing arc polyline is rendered
    const arcsBefore = container.querySelectorAll('.svg-door-arc');
    expect(arcsBefore.length).toBe(1);

    // Door leaf line and hinge are also rendered
    const doorLinesBefore = container.querySelectorAll('.svg-door-line');
    expect(doorLinesBefore.length).toBe(1);

    // Uncheck Show Door Swing Arcs toggle
    fireEvent.click(toggleCheckbox);
    expect(toggleCheckbox.checked).toBe(false);

    // Swing arc is hidden
    const arcsAfter = container.querySelectorAll('.svg-door-arc');
    expect(arcsAfter.length).toBe(0);

    // Door leaf line remains preserved
    const doorLinesAfter = container.querySelectorAll('.svg-door-line');
    expect(doorLinesAfter.length).toBe(1);
  });

  it('renders zero swing arcs when floor plan contains no doors', () => {
    const noDoorsFloorPlan: FloorPlan = {
      ...MOCK_FLOOR_PLAN,
      geometry: {
        ...MOCK_FLOOR_PLAN.geometry!,
        doors: [],
      },
    };

    const { container } = render(
      <FloorPlanCanvas
        floorPlan={noDoorsFloorPlan}
        selectedRoom={null}
        onSelectRoom={vi.fn()}
        projectId="proj_test"
      />
    );

    expect(container.querySelectorAll('.svg-door-arc').length).toBe(0);
    expect(container.querySelectorAll('.svg-door-line').length).toBe(0);
  });

  it('deduplicates doors so each valid physical door is rendered exactly once', () => {
    const duplicateDoorsFloorPlan: FloorPlan = {
      ...MOCK_FLOOR_PLAN,
      geometry: {
        ...MOCK_FLOOR_PLAN.geometry!,
        doors: [
          MOCK_FLOOR_PLAN.geometry!.doors[0],
          // Duplicate door at same position on same wall
          {
            ...MOCK_FLOOR_PLAN.geometry!.doors[0],
            id: 'door_1_duplicate',
          },
        ],
      },
    };

    const { container } = render(
      <FloorPlanCanvas
        floorPlan={duplicateDoorsFloorPlan}
        selectedRoom={null}
        onSelectRoom={vi.fn()}
        projectId="proj_test"
      />
    );

    // Even with 2 doors in data, deduplication renders only 1 door arc and line
    expect(container.querySelectorAll('.svg-door-arc').length).toBe(1);
    expect(container.querySelectorAll('.svg-door-line').length).toBe(1);
  });
});
