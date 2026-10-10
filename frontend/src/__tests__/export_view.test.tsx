import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExportView } from '../components/views/ExportView';
import type { FloorPlanSet } from '../api/types';

// Mock API calls
vi.mock('../api/projects', () => ({
  getExportInventory: vi.fn().mockResolvedValue({
    project_id: 'test_p1',
    bundle_path: 'outputs/test_p1',
    total_files: 2,
    files: [
      {
        filename: 'test_p1_floorplan.dxf',
        relative_path: 'test_p1_floorplan.dxf',
        size_bytes: 15420,
        media_type: 'application/dxf',
      },
    ],
  }),
}));

describe('ExportView CAD DXF Export Integration', () => {
  const mockFloorPlanSet: FloorPlanSet = {
    id: 'fps_1',
    project_name: 'Test Project',
    plot_boundary: [[0, 0], [20, 0], [20, 15], [0, 15]],
    buildable_boundary: [[2, 2], [18, 2], [18, 13], [2, 13]],
    floor_plans: [
      {
        id: 'fp_1',
        project_name: 'Test Project',
        floor_number: 1,
        is_valid: true,
        notes: '',
      },
    ],
  };

  it('renders CAD Drawing (DXF) card and download link for valid project', async () => {
    render(<ExportView projectId="test_p1" floorPlanSet={mockFloorPlanSet} />);

    // Check title
    expect(screen.getByText('CAD Drawing (DXF)')).toBeDefined();
    expect(screen.getByText('Publication-ready CAD geometry')).toBeDefined();

    // Check download button
    const downloadBtn = screen.getByRole('link', { name: /Download DXF/i }) as HTMLAnchorElement;
    expect(downloadBtn).toBeDefined();
    expect(downloadBtn.href).toContain('/projects/test_p1/export/dxf');
    expect(downloadBtn.download).toBeDefined();
  });

  it('displays warning badge when floor plan is invalid', async () => {
    const invalidFloorPlanSet: FloorPlanSet = {
      ...mockFloorPlanSet,
      floor_plans: [
        {
          ...mockFloorPlanSet.floor_plans[0],
          is_valid: false,
        },
      ],
    };

    render(<ExportView projectId="test_p2" floorPlanSet={invalidFloorPlanSet} />);

    expect(screen.getByText('CAD Drawing (DXF)')).toBeDefined();
    expect(screen.getByText('Requires Valid Plan')).toBeDefined();
    expect(screen.queryByRole('link', { name: /Download DXF/i })).toBeNull();
  });
});
