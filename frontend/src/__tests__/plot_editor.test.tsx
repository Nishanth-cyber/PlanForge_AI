import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlotEditor, type PlotData } from '../components/plot-editor/PlotEditor';
import {
  calculatePolygonArea,
  checkPolygonSelfIntersection,
  snapToGrid,
} from '../utils/geometry';
import type { Point2D } from '../api/types';

describe('Geometry Utilities', () => {
  it('calculates polygon area correctly using Shoelace formula', () => {
    // 10m x 10m square = 100 m²
    const square: Point2D[] = [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
    ];
    expect(calculatePolygonArea(square)).toBeCloseTo(100, 2);

    // L-shaped polygon
    const lShape: Point2D[] = [
      [0, 0],
      [20, 0],
      [20, 10],
      [10, 10],
      [10, 20],
      [0, 20],
    ];
    // Total 20x20=400 minus 10x10 cutout = 300 m²
    expect(calculatePolygonArea(lShape)).toBeCloseTo(300, 2);

    // Triangle
    const triangle: Point2D[] = [
      [0, 0],
      [10, 0],
      [0, 10],
    ];
    expect(calculatePolygonArea(triangle)).toBeCloseTo(50, 2);

    // Less than 3 points
    expect(calculatePolygonArea([[0, 0], [10, 0]])).toBe(0);
  });

  it('detects polygon self-intersections reliably', () => {
    // Simple convex square - no intersection
    const simpleSquare: Point2D[] = [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
    ];
    expect(checkPolygonSelfIntersection(simpleSquare).hasIntersection).toBe(false);

    // Hourglass / Bowtie polygon (self-intersecting)
    // (0,0) -> (10,10) -> (10,0) -> (0,10)
    const hourglass: Point2D[] = [
      [0, 0],
      [10, 10],
      [10, 0],
      [0, 10],
    ];
    expect(checkPolygonSelfIntersection(hourglass).hasIntersection).toBe(true);

    // L-shaped polygon - no intersection
    const lShape: Point2D[] = [
      [0, 0],
      [20, 0],
      [20, 10],
      [10, 10],
      [10, 20],
      [0, 20],
    ];
    expect(checkPolygonSelfIntersection(lShape).hasIntersection).toBe(false);
  });

  it('snaps coordinates to grid intervals correctly', () => {
    expect(snapToGrid(4.23, 0.5)).toBe(4.0);
    expect(snapToGrid(4.35, 0.5)).toBe(4.5);
    expect(snapToGrid(4.88, 0.5)).toBe(5.0);
    expect(snapToGrid(4.88, 1.0)).toBe(5.0);
  });
});

describe('PlotEditor Component', () => {
  const initialData: PlotData = {
    mode: 'rectangle',
    vertices: [
      [0, 0],
      [15, 0],
      [15, 25],
      [0, 25],
    ],
    width: 15,
    length: 25,
    unit: 'm',
    frontSetback: 2.0,
    rearSetback: 2.0,
    sideSetback: 2.0,
    orientation: 'north',
    isClosed: true,
  };

  it('renders in rectangle mode with dimension inputs and area calculation', () => {
    const onChange = vi.fn();
    render(<PlotEditor plotData={initialData} onChange={onChange} />);

    expect(screen.getByTestId('plot-editor')).toBeDefined();
    expect(screen.getByTestId('input-width')).toBeDefined();
    expect(screen.getByTestId('input-length')).toBeDefined();
    expect(screen.getByTestId('gross-area-badge')).toBeDefined();
    expect(screen.getByText(/Gross Area: 375.0 m²/i)).toBeDefined();
  });

  it('switches to irregular polygon mode and renders presets & vertex table', () => {
    const onChange = vi.fn();
    const { rerender } = render(<PlotEditor plotData={initialData} onChange={onChange} />);

    // Click irregular mode button
    const irregularBtn = screen.getByTestId('mode-irregular');
    fireEvent.click(irregularBtn);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'irregular',
      })
    );

    // Rerender with irregular mode
    const irregularData: PlotData = {
      ...initialData,
      mode: 'irregular',
      vertices: [
        [0, 0],
        [20, 0],
        [20, 10],
        [10, 10],
        [10, 20],
        [0, 20],
      ],
    };
    rerender(<PlotEditor plotData={irregularData} onChange={onChange} />);

    expect(screen.getByTestId('preset-select')).toBeDefined();
    expect(screen.getByTestId('vertex-table')).toBeDefined();
    expect(screen.getByTestId('vertex-count-badge')).toBeDefined();
    expect(screen.getByText(/6 Vertices/i)).toBeDefined();
  });

  it('displays self-intersection warning when irregular polygon edges cross', () => {
    const onChange = vi.fn();
    const onValidationChange = vi.fn();

    // Hourglass self-intersecting polygon
    const selfIntersectingData: PlotData = {
      mode: 'irregular',
      vertices: [
        [0, 0],
        [10, 10],
        [10, 0],
        [0, 10],
      ],
      width: 10,
      length: 10,
      unit: 'm',
      frontSetback: 2.0,
      rearSetback: 2.0,
      sideSetback: 2.0,
      orientation: 'north',
      isClosed: true,
    };

    render(
      <PlotEditor
        plotData={selfIntersectingData}
        onChange={onChange}
        onValidationChange={onValidationChange}
      />
    );

    expect(screen.getByTestId('self-intersection-warning')).toBeDefined();
    expect(
      screen.getByText(/Self-Intersecting Boundary Detected/i)
    ).toBeDefined();

    expect(onValidationChange).toHaveBeenCalledWith(
      false,
      expect.stringContaining('self-intersecting')
    );
  });

  it('allows adding and deleting vertices in irregular mode', () => {
    const onChange = vi.fn();
    const irregularData: PlotData = {
      mode: 'irregular',
      vertices: [
        [0, 0],
        [15, 0],
        [15, 15],
        [0, 15],
      ],
      width: 15,
      length: 15,
      unit: 'm',
      frontSetback: 2.0,
      rearSetback: 2.0,
      sideSetback: 2.0,
      orientation: 'north',
      isClosed: true,
    };

    render(<PlotEditor plotData={irregularData} onChange={onChange} />);

    // Click Add Vertex button
    const addBtn = screen.getByTestId('add-vertex-btn');
    fireEvent.click(addBtn);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        vertices: expect.arrayContaining([[0, 0], [15, 0], [15, 15], [0, 15]]),
      })
    );

    // Delete vertex
    const deleteBtns = screen.getAllByTestId('delete-vertex-btn');
    expect(deleteBtns.length).toBe(4);
    fireEvent.click(deleteBtns[2]);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        vertices: [
          [0, 0],
          [15, 0],
          [0, 15],
        ],
      })
    );
  });

  it('updates width and length dimensions in rectangle mode and triggers onChange with scaled vertices', () => {
    const onChange = vi.fn();
    render(<PlotEditor plotData={initialData} onChange={onChange} />);

    const widthInput = screen.getByTestId('input-width');
    fireEvent.change(widthInput, { target: { value: '30' } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        width: 30,
        vertices: [
          [0, 0],
          [30, 0],
          [30, 25],
          [0, 25],
        ],
      })
    );

    const lengthInput = screen.getByTestId('input-length');
    fireEvent.change(lengthInput, { target: { value: '40' } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        length: 40,
        vertices: [
          [0, 0],
          [15, 0],
          [15, 40],
          [0, 40],
        ],
      })
    );
  });

  it('accurately calculates and formats area in feet when unit is ft', () => {
    const onChange = vi.fn();
    const feetData: PlotData = {
      mode: 'rectangle',
      width: 40,
      length: 50,
      unit: 'ft',
      frontSetback: 2,
      rearSetback: 2,
      sideSetback: 2,
      orientation: 'north',
      vertices: [
        [0, 0],
        [40 * 0.3048, 0],
        [40 * 0.3048, 50 * 0.3048],
        [0, 50 * 0.3048],
      ],
      isClosed: true,
    };

    render(<PlotEditor plotData={feetData} onChange={onChange} />);

    // 40 ft * 50 ft = 2000 sq ft = 185.8 m²
    const areaBadge = screen.getByTestId('gross-area-badge');
    expect(areaBadge.textContent).toContain('2000 sq ft');
    expect(areaBadge.textContent).toContain('185.8 m²');
  });

  it('provides draggable coordinate scrub buttons, sliders mode, and interactive controls in vertex table', () => {
    const onChange = vi.fn();
    const irregularData: PlotData = {
      mode: 'irregular',
      vertices: [
        [0, 0],
        [20, 0],
        [20, 10],
        [0, 10],
      ],
      width: 20,
      length: 10,
      unit: 'm',
      frontSetback: 2.0,
      rearSetback: 2.0,
      sideSetback: 2.0,
      orientation: 'north',
      isClosed: true,
    };

    render(<PlotEditor plotData={irregularData} onChange={onChange} />);

    // Check scrub handles exist for vertices
    expect(screen.getByTestId('scrub-x-0')).toBeDefined();
    expect(screen.getByTestId('scrub-y-0')).toBeDefined();
    expect(screen.getByTestId('toggle-drag-mode')).toBeDefined();

    // Toggle drag sliders mode
    const toggleBtn = screen.getByTestId('toggle-drag-mode');
    fireEvent.click(toggleBtn);

    // Range sliders should now be present for coordinates
    const sliderX0 = screen.getByTestId('slider-x-0') as HTMLInputElement;
    expect(sliderX0).toBeDefined();

    // Fire slider change to drag X coordinate
    fireEvent.change(sliderX0, { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        vertices: [
          [5, 0],
          [20, 0],
          [20, 10],
          [0, 10],
        ],
      })
    );
  });
});

