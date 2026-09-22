import React, { useMemo, useState } from 'react';
import type { ProjectData, Point2D } from '../../api/types';
import { calculatePolygonArea, getPolygonBoundingBox } from '../../utils/geometry';

interface PlotViewProps {
  projectData: ProjectData;
  onAdjustPlot?: () => void;
}

export const PlotView: React.FC<PlotViewProps> = ({ projectData, onAdjustPlot }) => {
  const [showDimensions, setShowDimensions] = useState<boolean>(true);
  const [showBuildable, setShowBuildable] = useState<boolean>(true);

  // Extract plot boundary vertices (prioritizing floor_plan_set, then requirements)
  const plotBoundary: Point2D[] = useMemo(() => {
    if (projectData.floor_plan_set?.plot_boundary && projectData.floor_plan_set.plot_boundary.length >= 3) {
      return projectData.floor_plan_set.plot_boundary;
    }
    if (projectData.requirements?.plot_boundary && projectData.requirements.plot_boundary.length >= 3) {
      return projectData.requirements.plot_boundary;
    }
    // Fallback if rectangle width/length specified
    const w = projectData.requirements?.plot_width || 15;
    const l = projectData.requirements?.plot_length || 20;
    return [
      [0, 0],
      [w, 0],
      [w, l],
      [0, l],
    ];
  }, [projectData]);

  // Extract buildable boundary
  const buildableBoundary: Point2D[] = useMemo(() => {
    return projectData.floor_plan_set?.buildable_boundary || [];
  }, [projectData]);

  const req = projectData.requirements;
  const orientation = req?.orientation || 'north';
  const frontSetback = req?.front_setback ?? 2.0;
  const rearSetback = req?.rear_setback ?? 2.0;
  const sideSetback = req?.side_setback ?? 2.0;

  // Gross area calculation
  const grossAreaM2 = useMemo(() => calculatePolygonArea(plotBoundary), [plotBoundary]);
  const grossAreaSqFt = useMemo(() => grossAreaM2 * 10.7639, [grossAreaM2]);

  const buildableAreaM2 = useMemo(
    () => (buildableBoundary.length >= 3 ? calculatePolygonArea(buildableBoundary) : 0),
    [buildableBoundary]
  );

  const boundingBox = useMemo(() => getPolygonBoundingBox(plotBoundary), [plotBoundary]);

  // ViewBox calculation for SVG
  const pad = 4;
  const viewBoxMinX = boundingBox.minX - pad;
  const viewBoxMinY = boundingBox.minY - pad;
  const viewBoxWidth = boundingBox.width + pad * 2;
  const viewBoxHeight = boundingBox.height + pad * 2;

  return (
    <div className="plot-view-container" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Metrics Row */}
      <div className="grid grid-cols-4 gap-3">
        <div className="card" style={{ padding: '1rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Plot Geometry
          </span>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, marginTop: '0.25rem' }}>
            {plotBoundary.length === 4 ? '4-Sided Polygon' : `${plotBoundary.length}-Sided Polygon`}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Orientation: {orientation.toUpperCase()}
          </span>
        </div>

        <div className="card" style={{ padding: '1rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Gross Parcel Area
          </span>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, marginTop: '0.25rem' }}>
            {grossAreaM2.toFixed(1)} m²
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {grossAreaSqFt.toFixed(0)} sq ft
          </span>
        </div>

        <div className="card" style={{ padding: '1rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Buildable Footprint
          </span>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, marginTop: '0.25rem' }}>
            {buildableAreaM2 > 0 ? `${buildableAreaM2.toFixed(1)} m²` : '—'}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {buildableAreaM2 > 0 ? `${((buildableAreaM2 / grossAreaM2) * 100).toFixed(0)}% coverage` : 'Offset applied'}
          </span>
        </div>

        <div className="card" style={{ padding: '1rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Municipal Setbacks
          </span>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, marginTop: '0.25rem' }}>
            F: {frontSetback}m • R: {rearSetback}m
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Side: {sideSetback}m
          </span>
        </div>
      </div>

      {/* Main Plot Layout & Coordinate Inspection */}
      <div className="grid grid-cols-3 gap-4" style={{ alignItems: 'start' }}>
        {/* SVG Plot Visualizer */}
        <div
          className="card"
          style={{
            gridColumn: 'span 2',
            padding: '1.25rem',
            position: 'relative',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1rem',
            }}
          >
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Authoritative Plot Boundary</h3>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              {onAdjustPlot && (
                <button
                  type="button"
                  data-testid="adjust-plot-btn"
                  className="btn btn-secondary btn-sm"
                  onClick={onAdjustPlot}
                  style={{ fontSize: '0.75rem' }}
                >
                  ✎ Adjust in Wizard & Regenerate
                </button>
              )}
              <label style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showDimensions}
                  onChange={(e) => setShowDimensions(e.target.checked)}
                />
                Dimensions
              </label>
              <label style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showBuildable}
                  onChange={(e) => setShowBuildable(e.target.checked)}
                />
                Buildable Boundary
              </label>
            </div>
          </div>

          <div
            style={{
              width: '100%',
              height: '420px',
              background: 'var(--bg-canvas)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            <svg
              style={{ width: '100%', height: '100%' }}
              viewBox={`${viewBoxMinX} ${viewBoxMinY} ${viewBoxWidth} ${viewBoxHeight}`}
              preserveAspectRatio="xMidYMid meet"
            >
              {/* Cartesian Coordinate Flip Transform (Y up) */}
              <g transform={`scale(1, -1) translate(0, ${-(viewBoxMinY * 2 + viewBoxHeight)})`}>
                {/* Plot Boundary Polygon */}
                <polygon
                  points={plotBoundary.map(([x, y]) => `${x},${y}`).join(' ')}
                  fill="rgba(255, 255, 255, 0.04)"
                  stroke="var(--text-primary)"
                  strokeWidth={0.2}
                />

                {/* Buildable Boundary (Inset) */}
                {showBuildable && buildableBoundary.length >= 3 && (
                  <polygon
                    points={buildableBoundary.map(([x, y]) => `${x},${y}`).join(' ')}
                    fill="none"
                    stroke="var(--accent-sky)"
                    strokeWidth={0.15}
                    strokeDasharray="0.4 0.3"
                  />
                )}

                {/* Vertices */}
                {plotBoundary.map(([x, y], i) => (
                  <circle
                    key={i}
                    cx={x}
                    cy={y}
                    r={0.4}
                    fill="#000000"
                    stroke="#ffffff"
                    strokeWidth={0.15}
                  />
                ))}
              </g>

              {/* Dimension Labels (Rendered without Y-flip to prevent inverted text) */}
              {showDimensions &&
                plotBoundary.map((v, i) => {
                  const next = plotBoundary[(i + 1) % plotBoundary.length];
                  const midX = (v[0] + next[0]) / 2;
                  const midY = (v[1] + next[1]) / 2;
                  // Map midY to viewBox Y (due to Y flip)
                  const svgY = viewBoxMinY * 2 + viewBoxHeight - midY;
                  const dx = next[0] - v[0];
                  const dy = next[1] - v[1];
                  const len = Math.sqrt(dx * dx + dy * dy);

                  return (
                    <text
                      key={`dim-${i}`}
                      x={midX}
                      y={svgY}
                      textAnchor="middle"
                      fill="var(--text-secondary)"
                      fontSize={viewBoxWidth / 35}
                      fontFamily="monospace"
                      dominantBaseline="middle"
                    >
                      {len.toFixed(1)}m
                    </text>
                  );
                })}
            </svg>

            {/* Orientation Compass */}
            <div
              style={{
                position: 'absolute',
                top: '12px',
                right: '12px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-default)',
                padding: '0.4rem 0.6rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.75rem',
                color: 'var(--text-primary)',
              }}
            >
              <span style={{ fontWeight: 700, color: 'var(--accent-sky)' }}>↑ N</span> ({orientation})
            </div>
          </div>
        </div>

        {/* Real-World Coordinates Table */}
        <div className="card" style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Boundary Coordinates (m)
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
            Real-world coordinates relative to (0,0) origin used by ASAA and Geometry Engine.
          </p>

          <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-default)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.4rem', textAlign: 'left' }}>Vertex</th>
                <th style={{ padding: '0.4rem', textAlign: 'right' }}>X (meters)</th>
                <th style={{ padding: '0.4rem', textAlign: 'right' }}>Y (meters)</th>
              </tr>
            </thead>
            <tbody>
              {plotBoundary.map(([x, y], i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border-default)' }}>
                  <td style={{ padding: '0.45rem', fontWeight: 600 }}>P{i}</td>
                  <td style={{ padding: '0.45rem', textAlign: 'right', fontFamily: 'monospace' }}>
                    {x.toFixed(2)}m
                  </td>
                  <td style={{ padding: '0.45rem', textAlign: 'right', fontFamily: 'monospace' }}>
                    {y.toFixed(2)}m
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
