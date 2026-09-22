import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlotView } from '../components/views/PlotView';
import type { ProjectData } from '../api/types';

describe('PlotView Component', () => {
  it('renders plot geometry metrics, coordinates table, and SVG canvas', () => {
    const mockProjectData: ProjectData = {
      project_id: 'test_plot_proj',
      requirements: {
        plot_width: 20,
        plot_length: 20,
        plot_unit: 'm',
        orientation: 'south',
        front_setback: 3,
        rear_setback: 2,
        side_setback: 1.5,
        target_floors: 1,
        plot_boundary: [
          [0, 0],
          [20, 0],
          [20, 10],
          [10, 10],
          [10, 20],
          [0, 20],
        ],
      },
      floor_plan_set: {
        id: 'fps_1',
        project_name: 'Irregular Plot Test',
        plot_boundary: [
          [0, 0],
          [20, 0],
          [20, 10],
          [10, 10],
          [10, 20],
          [0, 20],
        ],
        buildable_boundary: [
          [1.5, 3],
          [18.5, 3],
          [18.5, 10],
          [10, 10],
          [10, 18],
          [1.5, 18],
        ],
        floor_plans: [],
      },
    };

    render(<PlotView projectData={mockProjectData} />);

    expect(screen.getByText(/Authoritative Plot Boundary/i)).toBeDefined();
    expect(screen.getByText(/6-Sided Polygon/i)).toBeDefined();
    expect(screen.getByText(/300.0 m²/i)).toBeDefined();
    expect(screen.getByText(/F: 3m • R: 2m/i)).toBeDefined();
    expect(screen.getByText(/Boundary Coordinates \(m\)/i)).toBeDefined();
  });
});
