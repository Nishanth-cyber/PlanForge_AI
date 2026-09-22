import React, { useState, useRef, useMemo, useEffect, useCallback } from 'react';
import type { FloorPlan, GeoRoom, Point2D } from '../../api/types';
import { getExportFileUrl } from '../../api/client';
import {
  getPolygonBoundingBox,
  findInteriorLabelPoint,
  getAdaptiveLabelConfig,
  polyToSvgPoints,
} from '../../utils/geometry';

interface FloorPlanCanvasProps {
  floorPlan: FloorPlan | null;
  plotBoundary?: Point2D[];
  buildableBoundary?: Point2D[];
  selectedRoom: GeoRoom | null;
  onSelectRoom: (room: GeoRoom | null) => void;
  projectId: string;
  alternativeIndex?: number;
  theme?: 'light' | 'dark';
  orientation?: string;
}

// Map room types to curated architectural theme colors (monochrome drafting)
function getRoomColor(roomType: string, isCorridor: boolean, isLight: boolean = false): { fill: string; stroke: string } {
  const t = roomType.toLowerCase();
  if (isLight) {
    if (isCorridor || t.includes('corridor') || t.includes('hallway') || t.includes('passage') || t.includes('circulation')) {
      return { fill: 'rgba(0, 0, 0, 0.015)', stroke: '#ced4da' };
    }
    if (t.includes('bed') || t.includes('bath') || t.includes('toilet') || t.includes('powder') || t.includes('ensuite')) {
      return { fill: 'rgba(0, 0, 0, 0.05)', stroke: '#495057' };
    }
    if (t.includes('kitchen') || t.includes('pantry') || t.includes('utility') || t.includes('laundry') || t.includes('store')) {
      return { fill: 'rgba(0, 0, 0, 0.03)', stroke: '#6c757d' };
    }
    if (t.includes('balcony') || t.includes('terrace') || t.includes('deck') || t.includes('patio')) {
      return { fill: 'rgba(0, 0, 0, 0.04)', stroke: '#495057' };
    }
    return { fill: 'rgba(0, 0, 0, 0.035)', stroke: '#212529' };
  }

  // Dark mode
  if (isCorridor || t.includes('corridor') || t.includes('hallway') || t.includes('passage') || t.includes('circulation')) {
    return { fill: 'rgba(255, 255, 255, 0.015)', stroke: '#555555' };
  }
  if (t.includes('bed') || t.includes('bath') || t.includes('toilet') || t.includes('powder') || t.includes('ensuite')) {
    return { fill: 'rgba(255, 255, 255, 0.07)', stroke: '#999999' };
  }
  if (t.includes('kitchen') || t.includes('pantry') || t.includes('utility') || t.includes('laundry') || t.includes('store')) {
    return { fill: 'rgba(255, 255, 255, 0.035)', stroke: '#777777' };
  }
  if (t.includes('balcony') || t.includes('terrace') || t.includes('deck') || t.includes('patio')) {
    return { fill: 'rgba(255, 255, 255, 0.05)', stroke: '#888888' };
  }
  return { fill: 'rgba(255, 255, 255, 0.05)', stroke: '#aaaaaa' };
}

export const FloorPlanCanvas: React.FC<FloorPlanCanvasProps> = ({
  floorPlan,
  plotBoundary = [],
  buildableBoundary = [],
  selectedRoom,
  onSelectRoom,
  projectId,
  alternativeIndex = 1,
  theme = 'light',
  orientation = 'north',
}) => {
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [viewMode, setViewMode] = useState<'svg' | 'png'>('svg');
  const [showPlot, setShowPlot] = useState<boolean>(true);
  const [showBuildable, setShowBuildable] = useState<boolean>(true);
  const [showDebug, setShowDebug] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const currentFloorNumber = floorPlan?.floor_number || 1;
  const geometry = floorPlan?.geometry;

  // Filter current floor geometry to prevent multi-floor overlapping
  const rooms = useMemo(() => {
    if (!geometry?.rooms) return [];
    return geometry.rooms.filter((r) => !r.floor_number || r.floor_number === currentFloorNumber);
  }, [geometry?.rooms, currentFloorNumber]);

  const walls = useMemo(() => {
    if (!geometry?.walls) return [];
    return geometry.walls.filter((w) => !w.floor_number || w.floor_number === currentFloorNumber);
  }, [geometry?.walls, currentFloorNumber]);

  const doors = useMemo(() => {
    if (!geometry?.doors) return [];
    return geometry.doors.filter((d) => !d.floor_number || d.floor_number === currentFloorNumber);
  }, [geometry?.doors, currentFloorNumber]);

  const windows = useMemo(() => {
    if (!geometry?.windows) return [];
    return geometry.windows.filter((w) => !w.floor_number || w.floor_number === currentFloorNumber);
  }, [geometry?.windows, currentFloorNumber]);

  const staircases = useMemo(() => {
    if (!geometry?.staircases) return [];
    return geometry.staircases.filter(
      (s) => !s.floor_number || s.floor_number === currentFloorNumber || s.from_floor === currentFloorNumber
    );
  }, [geometry?.staircases, currentFloorNumber]);

  // Wall map for fast lookup
  const wallMap = useMemo(() => {
    const map = new Map<string, (typeof walls)[0]>();
    walls.forEach((w) => map.set(w.id, w));
    return map;
  }, [walls]);

  // Calculate global bounding box encompassing plot and all floor elements
  const bbox = useMemo(() => {
    const allPoints: Point2D[] = [
      ...plotBoundary,
      ...buildableBoundary,
    ];

    rooms.forEach((r) => {
      allPoints.push(...(r.built_polygon || r.usable_polygon || []));
    });

    walls.forEach((w) => {
      if (w.polygon && w.polygon.length >= 2) {
        allPoints.push(...w.polygon);
      } else if (w.start && w.end) {
        allPoints.push(w.start, w.end);
      }
    });

    staircases.forEach((s) => {
      if (s.polygon && s.polygon.length >= 2) {
        allPoints.push(...s.polygon);
      }
    });

    if (allPoints.length === 0) {
      return { minX: 0, minY: 0, width: 20, height: 20, centerX: 10, centerY: 10 };
    }

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const [x, y] of allPoints) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }

    const spanX = Math.max(maxX - minX, 5);
    const spanY = Math.max(maxY - minY, 5);
    // Tight professional architectural margin: ~2.5% of span (min 0.4m, max 0.8m)
    const pad = Math.max(0.4, Math.min(0.8, Math.max(spanX, spanY) * 0.025));

    minX -= pad;
    maxX += pad;
    minY -= pad;
    maxY += pad;

    const width = maxX - minX;
    const height = maxY - minY;

    return {
      minX,
      minY,
      width,
      height,
      centerX: minX + width / 2,
      centerY: minY + height / 2,
    };
  }, [plotBoundary, buildableBoundary, rooms, walls, staircases]);

  // Reset to Fit to Plot
  const handleFitToPlot = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // When floor changes, reset view
  useEffect(() => {
    handleFitToPlot();
  }, [currentFloorNumber, handleFitToPlot]);

  // Pan & Drag Handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    setZoom((prev) => Math.max(0.4, Math.min(6, prev * factor)));
  };

  const handleZoomIn = () => setZoom((z) => Math.min(6, z * 1.25));
  const handleZoomOut = () => setZoom((z) => Math.max(0.4, z * 0.8));

  const pngUrl = getExportFileUrl(
    projectId,
    `alternatives/alternative_${alternativeIndex}/floor_${currentFloorNumber}.png`
  );

  return (
    <div className="floorplan-viewer-wrapper" ref={containerRef} data-testid="floorplan-canvas">
      {/* Top Toolbar Overlay */}
      <div className="canvas-toolbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: '0.25rem' }}>
            <button
              className={`btn btn-sm ${viewMode === 'svg' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setViewMode('svg')}
            >
              Interactive Vector
            </button>
            <button
              className={`btn btn-sm ${viewMode === 'png' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setViewMode('png')}
            >
              300 DPI Drawing
            </button>
          </div>

          {viewMode === 'svg' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', fontSize: '0.8rem', marginLeft: '0.25rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showPlot}
                  onChange={(e) => setShowPlot(e.target.checked)}
                />
                Plot Boundary
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showBuildable}
                  onChange={(e) => setShowBuildable(e.target.checked)}
                />
                Buildable Setback
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer', color: showDebug ? 'var(--accent-sky)' : 'inherit' }}>
                <input
                  type="checkbox"
                  checked={showDebug}
                  onChange={(e) => setShowDebug(e.target.checked)}
                />
                Debug Overlay
              </label>
            </div>
          )}
        </div>

        {viewMode === 'svg' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <button className="btn btn-outline btn-sm" onClick={handleZoomIn} title="Zoom In">
              +
            </button>
            <button className="btn btn-outline btn-sm" onClick={handleZoomOut} title="Zoom Out">
              −
            </button>
            <button className="btn btn-outline btn-sm" onClick={handleFitToPlot} title="Fit to Plot">
              Fit to Plot
            </button>
            <button className="btn btn-outline btn-sm" onClick={handleFitToPlot} title="Reset Center">
              Reset
            </button>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.4rem', fontFamily: 'var(--font-mono)' }}>
              {(zoom * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {/* Main Viewport */}
      {viewMode === 'png' ? (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem',
            overflow: 'auto',
            background: theme === 'light' ? '#ffffff' : '#000000',
          }}
        >
          <img
            src={pngUrl}
            alt={`Floor ${currentFloorNumber} Architectural Drawing`}
            style={{
              maxHeight: '100%',
              maxWidth: '100%',
              objectFit: 'contain',
              borderRadius: 'var(--radius-md)',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6)',
              border: '1px solid var(--border-default)',
            }}
            onError={(e) => {
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
        </div>
      ) : (
        <div
          className="canvas-viewport"
          style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
        >
          <svg
            ref={svgRef}
            className="canvas-svg"
            viewBox={`${bbox.minX} ${bbox.minY} ${bbox.width} ${bbox.height}`}
            preserveAspectRatio="xMidYMid meet"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: 'center center',
              transition: isDragging ? 'none' : 'transform 0.08s ease-out',
            }}
          >
            {/* 1. Subtle Architectural 1m Grid */}
            <defs>
              <pattern id="arch-grid" width="1" height="1" patternUnits="userSpaceOnUse">
                <path
                  d="M 1 0 L 0 0 0 1"
                  fill="none"
                  stroke={theme === 'light' ? 'rgba(0, 0, 0, 0.04)' : 'rgba(255, 255, 255, 0.025)'}
                  strokeWidth="0.03"
                />
              </pattern>
            </defs>
            <rect
              x={bbox.minX}
              y={bbox.minY}
              width={bbox.width}
              height={bbox.height}
              fill="url(#arch-grid)"
            />

            {/* 2. Plot Boundary (True irregular or rectangular polygon) */}
            {showPlot && plotBoundary.length >= 3 && (
              <polygon
                points={polyToSvgPoints(plotBoundary)}
                className="svg-plot-boundary"
              />
            )}

            {/* 3. Buildable / Setback Boundary */}
            {showBuildable && buildableBoundary.length >= 3 && (
              <polygon
                points={polyToSvgPoints(buildableBoundary)}
                className="svg-buildable-boundary"
              />
            )}

            {/* 4. Room Polygons (Fills & Boundaries) */}
            {rooms.map((room) => {
              const poly = room.usable_polygon || room.built_polygon || [];
              if (poly.length < 3) return null;
              const isSelected = selectedRoom?.id === room.id;
              const colors = getRoomColor(room.room_type, room.is_corridor || false, theme === 'light');

              return (
                <polygon
                  key={`poly-${room.id}`}
                  points={polyToSvgPoints(poly)}
                  className={`svg-room-poly ${isSelected ? 'selected' : ''}`}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectRoom(isSelected ? null : room);
                  }}
                />
              );
            })}

            {/* 5. Staircases (Geometry Treads & Direction Arrow) */}
            {staircases.map((stair) => {
              if (!stair.polygon || stair.polygon.length < 3) return null;
              const sBbox = getPolygonBoundingBox(stair.polygon);
              const rc = Math.max(6, Math.min(stair.riser_count || 16, 24));
              const isVertical = sBbox.height >= sBbox.width;

              // Generate tread lines
              const treads: React.ReactNode[] = [];
              if (isVertical) {
                const step = sBbox.height / rc;
                for (let i = 1; i < rc; i++) {
                  const yVal = sBbox.minY + i * step;
                  treads.push(
                    <line
                      key={`tread-${i}`}
                      x1={sBbox.minX}
                      y1={yVal}
                      x2={sBbox.maxX}
                      y2={yVal}
                      className="svg-staircase-tread"
                    />
                  );
                }
              } else {
                const step = sBbox.width / rc;
                for (let i = 1; i < rc; i++) {
                  const xVal = sBbox.minX + i * step;
                  treads.push(
                    <line
                      key={`tread-${i}`}
                      x1={xVal}
                      y1={sBbox.minY}
                      x2={xVal}
                      y2={sBbox.maxY}
                      className="svg-staircase-tread"
                    />
                  );
                }
              }

              // Flight arrow & label
              const [scx, scy] = [sBbox.minX + sBbox.width / 2, sBbox.minY + sBbox.height / 2];
              const isCompact = sBbox.width < 1.8 || sBbox.height < 1.8;

              return (
                <g key={`stair-${stair.id}`}>
                  <polygon points={polyToSvgPoints(stair.polygon)} className="svg-staircase" />
                  {treads}

                  {/* Direction Flight Arrow */}
                  {isVertical ? (
                    <g opacity={0.65}>
                      <line
                        x1={scx}
                        y1={sBbox.minY + 0.3}
                        x2={scx}
                        y2={sBbox.maxY - 0.5}
                        stroke={theme === 'light' ? '#000000' : '#ffffff'}
                        strokeWidth="0.05"
                      />
                      <path
                        d={`M ${scx - 0.15} ${sBbox.maxY - 0.7} L ${scx} ${sBbox.maxY - 0.4} L ${scx + 0.15} ${sBbox.maxY - 0.7}`}
                        fill="none"
                        stroke={theme === 'light' ? '#000000' : '#ffffff'}
                        strokeWidth="0.05"
                      />
                      <circle cx={scx} cy={sBbox.minY + 0.3} r={0.06} fill={theme === 'light' ? '#000000' : '#ffffff'} />
                    </g>
                  ) : (
                    <g opacity={0.65}>
                      <line
                        x1={sBbox.minX + 0.3}
                        y1={scy}
                        x2={sBbox.maxX - 0.5}
                        y2={scy}
                        stroke={theme === 'light' ? '#000000' : '#ffffff'}
                        strokeWidth="0.05"
                      />
                      <path
                        d={`M ${sBbox.maxX - 0.7} ${scy - 0.15} L ${sBbox.maxX - 0.4} ${scy} L ${sBbox.maxX - 0.7} ${scy + 0.15}`}
                        fill="none"
                        stroke={theme === 'light' ? '#000000' : '#ffffff'}
                        strokeWidth="0.05"
                      />
                      <circle cx={sBbox.minX + 0.3} cy={scy} r={0.06} fill={theme === 'light' ? '#000000' : '#ffffff'} />
                    </g>
                  )}

                  {/* Centered Staircase Annotation Chip */}
                  <g transform={`translate(${scx}, ${scy})`}>
                    <rect
                      x={-0.6}
                      y={-0.28}
                      width={1.2}
                      height={0.56}
                      rx={0.08}
                      fill={theme === 'light' ? 'rgba(255, 255, 255, 0.88)' : 'rgba(0, 0, 0, 0.75)'}
                    />
                    <text
                      x={0}
                      y={-0.06}
                      className="svg-room-label"
                      style={{ fontSize: isCompact ? '0.18px' : '0.22px' }}
                    >
                      STAIR
                    </text>
                    <text
                      x={0}
                      y={0.14}
                      className="svg-room-sublabel"
                      style={{ fontSize: isCompact ? '0.14px' : '0.16px' }}
                    >
                      {stair.riser_count}R
                    </text>
                  </g>
                </g>
              );
            })}

            {/* 6. Physical Walls (Footprint Polygons or Clean Lines) */}
            {walls.map((wall) => {
              if (wall.polygon && wall.polygon.length >= 3) {
                return (
                  <polygon
                    key={`wall-${wall.id}`}
                    points={polyToSvgPoints(wall.polygon)}
                    className={wall.type === 'exterior' ? 'svg-wall-exterior' : 'svg-wall'}
                  />
                );
              }

              if (wall.start && wall.end) {
                return (
                  <line
                    key={`wall-${wall.id}`}
                    x1={wall.start[0]}
                    y1={wall.start[1]}
                    x2={wall.end[0]}
                    y2={wall.end[1]}
                    className={wall.type === 'exterior' ? 'svg-wall-exterior' : 'svg-wall'}
                  />
                );
              }
              return null;
            })}

            {/* 7. Windows (Architectural Flush Segments on Wall) */}
            {windows.map((win) => {
              const [wx, wy] = win.position;
              const wHalf = (win.width || 1.2) / 2.0;
              const hostWall = win.wall_id ? wallMap.get(win.wall_id) : undefined;

              let dx = wHalf;
              let dy = 0;

              if (hostWall && hostWall.start && hostWall.end) {
                const len = Math.hypot(hostWall.end[0] - hostWall.start[0], hostWall.end[1] - hostWall.start[1]);
                if (len > 0.01) {
                  dx = ((hostWall.end[0] - hostWall.start[0]) / len) * wHalf;
                  dy = ((hostWall.end[1] - hostWall.start[1]) / len) * wHalf;
                }
              }

              const p1: Point2D = [wx - dx, wy - dy];
              const p2: Point2D = [wx + dx, wy + dy];

              return (
                <g key={`win-${win.id}`}>
                  {/* Visual Architectural Window Frame */}
                  <line
                    x1={p1[0]}
                    y1={p1[1]}
                    x2={p2[0]}
                    y2={p2[1]}
                    className="svg-window"
                  />
                  {/* Invisible Hit Area for Click/Inspect */}
                  <line
                    x1={p1[0]}
                    y1={p1[1]}
                    x2={p2[0]}
                    y2={p2[1]}
                    stroke="transparent"
                    strokeWidth="0.4"
                    style={{ cursor: 'pointer' }}
                  />
                </g>
              );
            })}

            {/* 8. Doors (Leaf Line + Clean 90-Degree Swing Arc) */}
            {doors.map((door) => {
              const hasArc = door.swing_arc && door.swing_arc.length >= 2;
              const hinge = hasArc ? door.swing_arc![0] : door.position;
              const leafTip = hasArc ? door.swing_arc![door.swing_arc!.length - 1] : door.position;

              return (
                <g key={`door-${door.id}`}>
                  {/* Swing Arc Path */}
                  {hasArc && (
                    <polyline
                      points={polyToSvgPoints(door.swing_arc!)}
                      className="svg-door-arc"
                    />
                  )}

                  {/* Door Leaf (from hinge to open edge) */}
                  {hasArc && (
                    <line
                      x1={hinge[0]}
                      y1={hinge[1]}
                      x2={leafTip[0]}
                      y2={leafTip[1]}
                      className="svg-door-line"
                    />
                  )}

                  {/* Delicate Hinge Pivot Marker (40mm radius) */}
                  <circle
                    cx={hinge[0]}
                    cy={hinge[1]}
                    r={0.04}
                    fill={theme === 'light' ? '#000000' : '#ffffff'}
                  />
                </g>
              );
            })}

            {/* 9. Room Labels (Interior Representative Point & Adaptive Grouping) */}
            {rooms.map((room) => {
              const poly = room.usable_polygon || room.built_polygon || [];
              if (poly.length < 3) return null;

              // Guaranteed interior label anchor
              const [lx, ly] = findInteriorLabelPoint(poly);
              const config = getAdaptiveLabelConfig(room.room_type, room.area_sqm, poly);

              const isSelected = selectedRoom?.id === room.id;

              // Vertical alignment offset so the text group is centered at (lx, ly)
              const totalLines = config.nameLines.length + (config.areaText ? 1 : 0);
              const startY = -(totalLines - 1) * (config.lineSpacing / 2);

              return (
                <g
                  key={`label-${room.id}`}
                  transform={`translate(${lx}, ${ly})`}
                  style={{ pointerEvents: 'none' }}
                >
                  {/* Subtle Contrast Chip Backdrop */}
                  <rect
                    x={-config.boxWidth / 2}
                    y={-config.boxHeight / 2}
                    width={config.boxWidth}
                    height={config.boxHeight}
                    rx={0.15}
                    ry={0.15}
                    fill={
                      isSelected
                        ? theme === 'light'
                          ? 'rgba(0, 0, 0, 0.90)'
                          : 'rgba(255, 255, 255, 0.95)'
                        : theme === 'light'
                        ? 'rgba(255, 255, 255, 0.90)'
                        : 'rgba(18, 18, 18, 0.88)'
                    }
                    stroke={
                      isSelected
                        ? 'var(--accent-sky)'
                        : theme === 'light'
                        ? 'rgba(0, 0, 0, 0.15)'
                        : 'rgba(255, 255, 255, 0.18)'
                    }
                    strokeWidth={0.03}
                  />

                  {/* Room Name Line(s) */}
                  {config.nameLines.map((line, idx) => (
                    <text
                      key={`name-${idx}`}
                      x={0}
                      y={startY + idx * config.lineSpacing}
                      className="svg-room-label"
                      fontSize={config.nameFontSize}
                      style={{
                        fontSize: `${config.nameFontSize}px`,
                        fill: isSelected
                          ? theme === 'light'
                            ? '#ffffff'
                            : '#000000'
                          : undefined,
                      }}
                    >
                      {line}
                    </text>
                  ))}

                  {/* Room Area Line */}
                  {config.areaText && (
                    <text
                      key="area"
                      x={0}
                      y={startY + config.nameLines.length * config.lineSpacing}
                      className="svg-room-sublabel"
                      fontSize={config.areaFontSize}
                      style={{
                        fontSize: `${config.areaFontSize}px`,
                        fill: isSelected
                          ? theme === 'light'
                            ? '#cccccc'
                            : '#333333'
                          : undefined,
                      }}
                    >
                      {config.areaText}
                    </text>
                  )}
                </g>
              );
            })}

            {/* 10. Development Debug Overlay */}
            {showDebug && (
              <g id="debug-overlay" opacity={0.75}>
                {rooms.map((room) => {
                  const poly = room.usable_polygon || room.built_polygon || [];
                  if (poly.length < 3) return null;
                  const [lx, ly] = findInteriorLabelPoint(poly);
                  const rBbox = getPolygonBoundingBox(poly);

                  return (
                    <g key={`debug-${room.id}`}>
                      {/* Bounding Box Outline */}
                      <rect
                        x={rBbox.minX}
                        y={rBbox.minY}
                        width={rBbox.width}
                        height={rBbox.height}
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="0.04"
                        strokeDasharray="0.2 0.2"
                      />
                      {/* Anchor crosshair */}
                      <line x1={lx - 0.2} y1={ly} x2={lx + 0.2} y2={ly} stroke="#ef4444" strokeWidth="0.04" />
                      <line x1={lx} y1={ly - 0.2} x2={lx} y2={ly + 0.2} stroke="#ef4444" strokeWidth="0.04" />
                      <circle cx={lx} cy={ly} r={0.06} fill="#ef4444" />
                      <text
                        x={rBbox.minX + 0.15}
                        y={rBbox.minY + 0.3}
                        fill="#f59e0b"
                        fontSize="0.16px"
                        fontFamily="monospace"
                      >
                        {room.id.slice(0, 8)}
                      </text>
                    </g>
                  );
                })}
              </g>
            )}
          </svg>

          {/* Screen-Space North Arrow Overlay (Fixed in Corner Outside Plot) */}
          <div
            className="north-arrow-overlay"
            style={{
              position: 'absolute',
              top: '14px',
              right: '16px',
              background: theme === 'light' ? 'rgba(255, 255, 255, 0.92)' : 'rgba(20, 20, 20, 0.88)',
              backdropFilter: 'blur(6px)',
              border: '1px solid var(--border-default)',
              padding: '0.45rem 0.65rem',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '0 2px 6px rgba(0, 0, 0, 0.25)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.45rem',
              pointerEvents: 'none',
              zIndex: 15,
            }}
          >
            <div
              style={{
                width: '18px',
                height: '18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="11" fill="none" stroke={theme === 'light' ? '#ced4da' : '#555555'} strokeWidth="1" />
                <path d="M 12 3 L 16 19 L 12 15 L 8 19 Z" fill={theme === 'light' ? '#000000' : '#ffffff'} />
              </svg>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
              <span style={{ fontSize: '0.725rem', fontWeight: 700, color: 'var(--text-primary)' }}>N</span>
              <span style={{ fontSize: '0.625rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                {orientation || 'North'}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
