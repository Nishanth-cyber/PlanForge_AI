import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import type { Point2D } from '../../api/types';
import {
  calculatePolygonArea,
  checkPolygonSelfIntersection,
  getPolygonBoundingBox,
  snapToGrid,
  PLOT_PRESETS,
} from '../../utils/geometry';

export interface PlotData {
  mode: 'rectangle' | 'irregular';
  vertices: Point2D[];
  width: number;
  length: number;
  unit: 'm' | 'ft';
  frontSetback: number;
  rearSetback: number;
  sideSetback: number;
  orientation: string;
  isClosed: boolean;
}

interface PlotEditorProps {
  plotData: PlotData;
  onChange: (data: PlotData) => void;
  onValidationChange?: (isValid: boolean, errorMessage?: string) => void;
}

export const PlotEditor: React.FC<PlotEditorProps> = ({
  plotData,
  onChange,
  onValidationChange,
}) => {
  const {
    mode,
    vertices,
    width,
    length,
    unit,
    frontSetback,
    rearSetback,
    sideSetback,
    orientation,
    isClosed,
  } = plotData;

  // Selected vertex index
  const [selectedVertexIndex, setSelectedVertexIndex] = useState<number | null>(null);
  // Dragging state
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  // Grid snapping state
  const [snapEnabled, setSnapEnabled] = useState<boolean>(true);
  const snapStep = 0.5; // meters

  // History stack for undo / redo
  const [history, setHistory] = useState<Point2D[][]>([]);
  const [historyPointer, setHistoryPointer] = useState<number>(-1);

  // SVG Canvas pan and zoom
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 60, y: 60 });
  const [zoom, setZoom] = useState<number>(12); // pixels per meter
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const svgRef = useRef<SVGSVGElement | null>(null);

  // Push state to undo history
  const pushHistory = useCallback((newVertices: Point2D[]) => {
    setHistory((prev) => {
      const upToCurrent = prev.slice(0, historyPointer + 1);
      return [...upToCurrent, newVertices];
    });
    setHistoryPointer((prev) => prev + 1);
  }, [historyPointer]);

  // Initial history push if empty
  useEffect(() => {
    if (history.length === 0 && vertices.length > 0) {
      setHistory([vertices]);
      setHistoryPointer(0);
    }
  }, [vertices, history.length]);

  const handleUndo = () => {
    if (historyPointer > 0) {
      const newPointer = historyPointer - 1;
      const prevVertices = history[newPointer];
      setHistoryPointer(newPointer);
      onChange({
        ...plotData,
        vertices: prevVertices,
        isClosed: prevVertices.length >= 3,
      });
      setSelectedVertexIndex(null);
    }
  };

  const handleRedo = () => {
    if (historyPointer < history.length - 1) {
      const newPointer = historyPointer + 1;
      const nextVertices = history[newPointer];
      setHistoryPointer(newPointer);
      onChange({
        ...plotData,
        vertices: nextVertices,
        isClosed: nextVertices.length >= 3,
      });
      setSelectedVertexIndex(null);
    }
  };

  // Local input string states so users can freely clear, backspace, and type decimals
  const [widthInput, setWidthInput] = useState<string>(String(width));
  const [lengthInput, setLengthInput] = useState<string>(String(length));

  useEffect(() => {
    setWidthInput(String(width));
  }, [width]);

  useEffect(() => {
    setLengthInput(String(length));
  }, [length]);

  // Compute bounding box and center zoom automatically
  const boundingBox = useMemo(() => {
    if (mode === 'rectangle') {
      const wM = unit === 'ft' ? width * 0.3048 : width;
      const lM = unit === 'ft' ? length * 0.3048 : length;
      return {
        minX: 0,
        minY: 0,
        maxX: Math.max(wM, 0.1),
        maxY: Math.max(lM, 0.1),
        width: Math.max(wM, 0.1),
        height: Math.max(lM, 0.1),
      };
    }
    return getPolygonBoundingBox(vertices);
  }, [mode, unit, width, length, vertices]);

  // Area calculation
  const grossAreaM2 = useMemo(() => {
    if (mode === 'rectangle') {
      const wM = unit === 'ft' ? width * 0.3048 : width;
      const lM = unit === 'ft' ? length * 0.3048 : length;
      return wM * lM;
    }
    return calculatePolygonArea(vertices);
  }, [mode, unit, width, length, vertices]);

  const grossAreaSqFt = useMemo(() => {
    if (mode === 'rectangle' && unit === 'ft') {
      return width * length;
    }
    return grossAreaM2 * 10.7639;
  }, [mode, unit, width, length, grossAreaM2]);

  // Self-intersection test
  const intersectionResult = useMemo(
    () => checkPolygonSelfIntersection(vertices, isClosed),
    [vertices, isClosed]
  );

  // Validation status
  const validation = useMemo(() => {
    if (mode === 'rectangle') {
      if (width <= 0 || length <= 0) {
        return { isValid: false, message: 'Plot dimensions must be greater than zero.' };
      }
      return { isValid: true };
    }

    if (vertices.length < 3) {
      return { isValid: false, message: 'An irregular plot requires at least 3 vertices.' };
    }
    if (!isClosed) {
      return { isValid: false, message: 'Polygon boundary must be closed.' };
    }
    if (intersectionResult.hasIntersection) {
      return {
        isValid: false,
        message: 'Plot boundary has self-intersecting edges. Please adjust vertices.',
      };
    }
    if (grossAreaM2 < 10) {
      return { isValid: false, message: 'Plot area is too small (< 10 m²).' };
    }
    return { isValid: true };
  }, [mode, width, length, vertices, isClosed, intersectionResult, grossAreaM2]);

  useEffect(() => {
    onValidationChange?.(validation.isValid, validation.message);
  }, [validation, onValidationChange]);

  // Conversion: Screen SVG coordinates to real-world meters
  const screenToMeters = useCallback(
    (screenX: number, screenY: number): Point2D => {
      if (!svgRef.current) return [0, 0];
      const rect = svgRef.current.getBoundingClientRect();
      const localX = screenX - rect.left;
      const localY = screenY - rect.top;

      const meterX = (localX - pan.x) / zoom;
      const meterY = (rect.height - localY - pan.y) / zoom;

      const snappedX = snapEnabled ? snapToGrid(meterX, snapStep) : Math.round(meterX * 10) / 10;
      const snappedY = snapEnabled ? snapToGrid(meterY, snapStep) : Math.round(meterY * 10) / 10;

      return [Math.max(0, snappedX), Math.max(0, snappedY)];
    },
    [pan, zoom, snapEnabled, snapStep]
  );

  // Conversion: Real-world meters to Screen SVG coordinates
  const metersToScreen = useCallback(
    (mx: number, my: number): { x: number; y: number } => {
      if (!svgRef.current) return { x: 0, y: 0 };
      const svgHeight = svgRef.current.clientHeight || 450;
      return {
        x: pan.x + mx * zoom,
        y: svgHeight - pan.y - my * zoom,
      };
    },
    [pan, zoom]
  );

  // Fit view to plot and center in canvas
  const handleFitView = useCallback(() => {
    if (!svgRef.current) return;
    const svgWidth = svgRef.current.clientWidth || 700;
    const svgHeight = svgRef.current.clientHeight || 450;

    const pad = 50;
    const bb = boundingBox;
    const scaleX = (svgWidth - pad * 2) / Math.max(bb.width, 2);
    const scaleY = (svgHeight - pad * 2) / Math.max(bb.height, 2);
    const newZoom = Math.min(Math.max(Math.min(scaleX, scaleY), 2), 40);

    setZoom(newZoom);
    const contentW = bb.width * newZoom;
    const contentH = bb.height * newZoom;
    const panX = Math.max(20, (svgWidth - contentW) / 2) - bb.minX * newZoom;
    const panY = Math.max(20, (svgHeight - contentH) / 2) - bb.minY * newZoom;

    setPan({
      x: panX,
      y: panY,
    });
  }, [boundingBox]);

  // Auto-fit view whenever bounding box changes or mode changes
  const prevBbRef = useRef<string>('');
  useEffect(() => {
    const bbKey = `${mode}-${boundingBox.width.toFixed(1)}-${boundingBox.height.toFixed(1)}`;
    if (prevBbRef.current !== bbKey) {
      prevBbRef.current = bbKey;
      handleFitView();
    }
  }, [mode, boundingBox, handleFitView]);

  // Handle Switch to Rectangle Mode
  const handleSwitchToRectangle = () => {
    const w = width > 0 ? width : 15;
    const l = length > 0 ? length : 25;
    const wM = unit === 'ft' ? w * 0.3048 : w;
    const lM = unit === 'ft' ? l * 0.3048 : l;
    const rectVerts: Point2D[] = [
      [0, 0],
      [wM, 0],
      [wM, lM],
      [0, lM],
    ];
    onChange({
      ...plotData,
      mode: 'rectangle',
      width: w,
      length: l,
      vertices: rectVerts,
      isClosed: true,
    });
    pushHistory(rectVerts);
  };

  // Handle Switch to Irregular Polygon Mode
  const handleSwitchToIrregular = () => {
    onChange({
      ...plotData,
      mode: 'irregular',
    });
  };

  // Load Preset
  const handleSelectPreset = (presetKey: string) => {
    const preset = PLOT_PRESETS[presetKey];
    if (!preset) return;
    const newVerts = [...preset.points];
    const bb = getPolygonBoundingBox(newVerts);
    onChange({
      ...plotData,
      mode: 'irregular',
      vertices: newVerts,
      width: bb.width,
      length: bb.height,
      isClosed: true,
    });
    pushHistory(newVerts);
    setSelectedVertexIndex(null);
  };

  // Rectangle dimension changes
  const handleWidthChange = (val: number) => {
    const newW = Math.max(0.1, val);
    const wM = unit === 'ft' ? newW * 0.3048 : newW;
    const lM = unit === 'ft' ? length * 0.3048 : length;
    const rectVerts: Point2D[] = [
      [0, 0],
      [wM, 0],
      [wM, lM],
      [0, lM],
    ];
    onChange({
      ...plotData,
      width: newW,
      vertices: rectVerts,
    });
  };

  const handleLengthChange = (val: number) => {
    const newL = Math.max(0.1, val);
    const wM = unit === 'ft' ? width * 0.3048 : width;
    const lM = unit === 'ft' ? newL * 0.3048 : newL;
    const rectVerts: Point2D[] = [
      [0, 0],
      [wM, 0],
      [wM, lM],
      [0, lM],
    ];
    onChange({
      ...plotData,
      length: newL,
      vertices: rectVerts,
    });
  };

  const handleUnitChange = (newUnit: 'm' | 'ft') => {
    if (newUnit === unit) return;
    const newW = newUnit === 'ft' ? Math.round((width / 0.3048) * 10) / 10 : Math.round(width * 0.3048 * 10) / 10;
    const newL = newUnit === 'ft' ? Math.round((length / 0.3048) * 10) / 10 : Math.round(length * 0.3048 * 10) / 10;
    const wM = newUnit === 'ft' ? newW * 0.3048 : newW;
    const lM = newUnit === 'ft' ? newL * 0.3048 : newL;
    const rectVerts: Point2D[] = [
      [0, 0],
      [wM, 0],
      [wM, lM],
      [0, lM],
    ];
    onChange({
      ...plotData,
      unit: newUnit,
      width: newW,
      length: newL,
      vertices: rectVerts,
    });
  };

  const handleWidthInputChange = (valStr: string) => {
    setWidthInput(valStr);
    const val = parseFloat(valStr);
    if (!isNaN(val) && val > 0) {
      handleWidthChange(val);
    }
  };

  const handleWidthInputBlur = () => {
    const val = parseFloat(widthInput);
    if (isNaN(val) || val <= 0) {
      setWidthInput(String(width));
    } else {
      handleWidthChange(val);
    }
  };

  const handleLengthInputChange = (valStr: string) => {
    setLengthInput(valStr);
    const val = parseFloat(valStr);
    if (!isNaN(val) && val > 0) {
      handleLengthChange(val);
    }
  };

  const handleLengthInputBlur = () => {
    const val = parseFloat(lengthInput);
    if (isNaN(val) || val <= 0) {
      setLengthInput(String(length));
    } else {
      handleLengthChange(val);
    }
  };

  // Vertex Manipulation in Irregular Mode
  const handleAddVertexAtPoint = (pt: Point2D) => {
    const updated = [...vertices, pt];
    onChange({
      ...plotData,
      vertices: updated,
      isClosed: updated.length >= 3,
    });
    pushHistory(updated);
    setSelectedVertexIndex(updated.length - 1);
  };

  const handleUpdateVertexCoord = (index: number, x: number, y: number) => {
    const updated = vertices.map((v, i) => (i === index ? [x, y] as Point2D : v));
    onChange({
      ...plotData,
      vertices: updated,
    });
    pushHistory(updated);
  };

  const handleDeleteVertex = (index: number) => {
    if (vertices.length <= 3) {
      alert('A polygon must have at least 3 vertices.');
      return;
    }
    const updated = vertices.filter((_, i) => i !== index);
    onChange({
      ...plotData,
      vertices: updated,
      isClosed: updated.length >= 3,
    });
    pushHistory(updated);
    setSelectedVertexIndex(null);
  };

  const handleClear = () => {
    onChange({
      ...plotData,
      vertices: [],
      isClosed: false,
    });
    pushHistory([]);
    setSelectedVertexIndex(null);
  };

  const handleClosePolygon = () => {
    if (vertices.length >= 3) {
      onChange({
        ...plotData,
        isClosed: true,
      });
    }
  };

  // SVG Mouse Handlers for Canvas Interaction
  const handleCanvasMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button === 1 || e.altKey) {
      // Middle click or Alt+click pans
      setIsPanning(true);
      panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
      return;
    }

    if (e.button === 0 && draggingIndex === null) {
      // Left click on empty canvas
      const target = e.target as SVGElement;
      if (target.dataset.type === 'canvas-bg' || target.dataset.type === 'grid') {
        if (mode === 'irregular' && (!isClosed || vertices.length < 3)) {
          const pt = screenToMeters(e.clientX, e.clientY);
          handleAddVertexAtPoint(pt);
        } else {
          setSelectedVertexIndex(null);
        }
      }
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (isPanning) {
      setPan({
        x: e.clientX - panStartRef.current.x,
        y: e.clientY - panStartRef.current.y,
      });
      return;
    }

    if (draggingIndex !== null && mode === 'irregular') {
      const pt = screenToMeters(e.clientX, e.clientY);
      const updated = vertices.map((v, i) => (i === draggingIndex ? pt : v));
      onChange({
        ...plotData,
        vertices: updated,
      });
    }
  };

  const handleCanvasMouseUp = () => {
    if (isPanning) {
      setIsPanning(false);
    }
    if (draggingIndex !== null) {
      pushHistory(vertices);
      setDraggingIndex(null);
    }
  };

  const handleCanvasWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    const newZoom = Math.min(Math.max(zoom * zoomFactor, 4), 50);
    setZoom(newZoom);
  };

  // Generate SVG Points string
  const svgPolygonPoints = useMemo(() => {
    return vertices
      .map((v) => {
        const s = metersToScreen(v[0], v[1]);
        return `${s.x},${s.y}`;
      })
      .join(' ');
  }, [vertices, metersToScreen]);

  // Compute Buildable Inset Boundary (for preview)
  const buildablePoints = useMemo(() => {
    if (vertices.length < 3) return null;
    // Inset boundary for rectangular mode
    if (mode === 'rectangle') {
      const wM = unit === 'ft' ? width * 0.3048 : width;
      const lM = unit === 'ft' ? length * 0.3048 : length;
      const minX = sideSetback;
      const maxX = Math.max(minX, wM - sideSetback);
      const minY = frontSetback;
      const maxY = Math.max(minY, lM - rearSetback);
      return [
        metersToScreen(minX, minY),
        metersToScreen(maxX, minY),
        metersToScreen(maxX, maxY),
        metersToScreen(minX, maxY),
      ];
    }
    return null;
  }, [vertices, mode, width, length, unit, frontSetback, rearSetback, sideSetback, metersToScreen]);

  return (
    <div className="plot-editor-container" data-testid="plot-editor">
      {/* Mode Switcher and Presets Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--border-default)',
          marginBottom: '1rem',
        }}
      >
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            type="button"
            data-testid="mode-rectangle"
            className={`btn btn-sm ${mode === 'rectangle' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={handleSwitchToRectangle}
          >
            Rectangle Mode
          </button>
          <button
            type="button"
            data-testid="mode-irregular"
            className={`btn btn-sm ${mode === 'irregular' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={handleSwitchToIrregular}
          >
            Irregular Polygon Mode
          </button>
        </div>

        {mode === 'irregular' && (
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.775rem', color: 'var(--text-secondary)' }}>Presets:</span>
            <select
              data-testid="preset-select"
              className="form-select form-select-sm"
              style={{ width: 'auto', fontSize: '0.775rem', padding: '0.25rem 0.5rem' }}
              onChange={(e) => {
                if (e.target.value) handleSelectPreset(e.target.value);
              }}
              defaultValue=""
            >
              <option value="" disabled>
                Select Irregular Preset...
              </option>
              <option value="l_shaped">L-Shaped Corner (300 m²)</option>
              <option value="trapezoid">Trapezoid Cul-de-sac (320 m²)</option>
              <option value="infill_5sided">5-Sided Urban Infill (235.5 m²)</option>
              <option value="rectangle_standard">Standard Suburban (375 m²)</option>
            </select>
          </div>
        )}
      </div>

      {/* Mode-Specific Parameters Bar */}
      {mode === 'rectangle' ? (
        <div
          className="grid grid-cols-5 gap-3"
          style={{
            background: 'var(--bg-secondary)',
            padding: '0.85rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1rem',
            alignItems: 'end',
          }}
        >
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>
              Width ({unit})
            </label>
            <input
              type="number"
              data-testid="input-width"
              step={0.5}
              min={1}
              max={500}
              className="form-input form-input-sm"
              value={widthInput}
              onChange={(e) => handleWidthInputChange(e.target.value)}
              onBlur={handleWidthInputBlur}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>
              Length ({unit})
            </label>
            <input
              type="number"
              data-testid="input-length"
              step={0.5}
              min={1}
              max={500}
              className="form-input form-input-sm"
              value={lengthInput}
              onChange={(e) => handleLengthInputChange(e.target.value)}
              onBlur={handleLengthInputBlur}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>
              Orientation
            </label>
            <select
              data-testid="select-orientation"
              className="form-select form-select-sm"
              value={orientation}
              onChange={(e) => onChange({ ...plotData, orientation: e.target.value })}
            >
              <option value="north">North-Facing</option>
              <option value="south">South-Facing</option>
              <option value="east">East-Facing</option>
              <option value="west">West-Facing</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>
              Unit
            </label>
            <select
              className="form-select form-select-sm"
              value={unit}
              onChange={(e) => handleUnitChange(e.target.value as 'm' | 'ft')}
            >
              <option value="m">Meters (m)</option>
              <option value="ft">Feet (ft)</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end', paddingBottom: '2px' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setZoom((z) => Math.min(z * 1.25, 45))}
              title="Zoom In"
            >
              +
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setZoom((z) => Math.max(z * 0.8, 2))}
              title="Zoom Out"
            >
              -
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleFitView}
              title="Fit View"
            >
              Fit
            </button>
          </div>
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.5rem',
            background: 'var(--bg-secondary)',
            padding: '0.65rem 0.85rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              data-testid="undo-btn"
              className="btn btn-secondary btn-sm"
              onClick={handleUndo}
              disabled={historyPointer <= 0}
              title="Undo (Ctrl+Z)"
            >
              ↶ Undo
            </button>
            <button
              type="button"
              data-testid="redo-btn"
              className="btn btn-secondary btn-sm"
              onClick={handleRedo}
              disabled={historyPointer >= history.length - 1}
              title="Redo (Ctrl+Y)"
            >
              ↷ Redo
            </button>
            <button
              type="button"
              data-testid="clear-btn"
              className="btn btn-secondary btn-sm"
              onClick={handleClear}
            >
              Clear
            </button>
            {!isClosed && vertices.length >= 3 && (
              <button
                type="button"
                data-testid="close-polygon-btn"
                className="btn btn-primary btn-sm"
                onClick={handleClosePolygon}
              >
                ✓ Close Polygon
              </button>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginLeft: '0.5rem' }}>
              <input
                type="checkbox"
                id="snap-grid-check"
                checked={snapEnabled}
                onChange={(e) => setSnapEnabled(e.target.checked)}
              />
              <label htmlFor="snap-grid-check" style={{ fontSize: '0.75rem', cursor: 'pointer' }}>
                Snap Grid (0.5m)
              </label>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setZoom((z) => Math.min(z * 1.25, 45))}
              title="Zoom In"
            >
              +
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setZoom((z) => Math.max(z * 0.8, 4))}
              title="Zoom Out"
            >
              -
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleFitView}
              title="Fit View"
            >
              Fit
            </button>
          </div>
        </div>
      )}

      {/* Validation / Self-Intersection Warning Banner */}
      {intersectionResult.hasIntersection && (
        <div
          data-testid="self-intersection-warning"
          style={{
            padding: '0.65rem 1rem',
            background: 'var(--status-danger-bg)',
            border: '1px solid var(--status-danger-border)',
            color: '#f87171',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.825rem',
            marginBottom: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>⚠</span>
          <span>
            <strong>Self-Intersecting Boundary Detected:</strong> Polygon edges cross over each other.
            Adjust vertices to form a simple closed perimeter before generating.
          </span>
        </div>
      )}

      {/* Main Canvas & Coordinate Inspector Layout */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: mode === 'irregular' ? '1fr 280px' : '1fr',
          gap: '1rem',
          alignItems: 'start',
        }}
      >
        {/* SVG Interactive Canvas */}
        <div
          style={{
            position: 'relative',
            background: 'var(--bg-canvas)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
            height: '460px',
          }}
        >
          <svg
            ref={svgRef}
            data-testid="plot-canvas"
            style={{
              width: '100%',
              height: '100%',
              cursor: isPanning ? 'grabbing' : mode === 'irregular' ? 'crosshair' : 'default',
              userSelect: 'none',
            }}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            onWheel={handleCanvasWheel}
          >
            {/* Background click target */}
            <rect
              data-type="canvas-bg"
              width="100%"
              height="100%"
              fill="transparent"
            />

            {/* Coordinate Grid (1m minor, 5m major) */}
            <g data-type="grid" opacity={0.35}>
              {Array.from({ length: 60 }).map((_, i) => {
                const meterCoord = (i - 10) * 1;
                const isMajor = meterCoord % 5 === 0;
                const s = metersToScreen(meterCoord, 0);
                return (
                  <line
                    key={`grid-x-${i}`}
                    x1={s.x}
                    y1={0}
                    x2={s.x}
                    y2="100%"
                    stroke={isMajor ? 'var(--border-strong)' : 'var(--border-default)'}
                    strokeWidth={isMajor ? 1 : 0.5}
                  />
                );
              })}
              {Array.from({ length: 45 }).map((_, i) => {
                const meterCoord = (i - 5) * 1;
                const isMajor = meterCoord % 5 === 0;
                const s = metersToScreen(0, meterCoord);
                return (
                  <line
                    key={`grid-y-${i}`}
                    x1={0}
                    y1={s.y}
                    x2="100%"
                    y2={s.y}
                    stroke={isMajor ? 'var(--border-strong)' : 'var(--border-default)'}
                    strokeWidth={isMajor ? 1 : 0.5}
                  />
                );
              })}
            </g>

            {/* Origin Marker (0,0) */}
            {(() => {
              const origin = metersToScreen(0, 0);
              return (
                <g>
                  <circle cx={origin.x} cy={origin.y} r={4} fill="#ffffff" stroke="#000000" strokeWidth={1.5} />
                  <text
                    x={origin.x + 8}
                    y={origin.y - 8}
                    fill="var(--text-muted)"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    (0,0)
                  </text>
                </g>
              );
            })()}

            {/* Plot Polygon Boundary Fill & Stroke */}
            {vertices.length >= 2 && (
              <polygon
                points={svgPolygonPoints}
                fill={
                  intersectionResult.hasIntersection
                    ? 'rgba(239, 68, 68, 0.12)'
                    : 'rgba(255, 255, 255, 0.04)'
                }
                stroke={
                  intersectionResult.hasIntersection
                    ? '#ef4444'
                    : 'var(--text-primary)'
                }
                strokeWidth={2}
                strokeDasharray={isClosed ? 'none' : '4 4'}
              />
            )}

            {/* Buildable Area Inset Preview (Rectangle mode) */}
            {buildablePoints && (
              <polygon
                points={buildablePoints.map((p) => `${p.x},${p.y}`).join(' ')}
                fill="none"
                stroke="var(--accent-sky)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
            )}

            {/* Edge Dimension Labels */}
            {vertices.length >= 2 &&
              vertices.map((v, i) => {
                const next = isClosed
                  ? vertices[(i + 1) % vertices.length]
                  : i < vertices.length - 1
                  ? vertices[i + 1]
                  : null;
                if (!next) return null;

                const p1 = metersToScreen(v[0], v[1]);
                const p2 = metersToScreen(next[0], next[1]);
                const midX = (p1.x + p2.x) / 2;
                const midY = (p1.y + p2.y) / 2;
                const dx = next[0] - v[0];
                const dy = next[1] - v[1];
                const lenM = Math.sqrt(dx * dx + dy * dy);
                const displayLen = unit === 'ft' ? `${(lenM / 0.3048).toFixed(1)}ft` : `${lenM.toFixed(1)}m`;

                return (
                  <g key={`edge-len-${i}`}>
                    <rect
                      x={midX - 22}
                      y={midY - 9}
                      width={44}
                      height={18}
                      fill="var(--bg-surface)"
                      rx={3}
                      opacity={0.9}
                      stroke="var(--border-default)"
                      strokeWidth={0.5}
                    />
                    <text
                      x={midX}
                      y={midY + 4}
                      textAnchor="middle"
                      fill="var(--text-secondary)"
                      fontSize="9.5"
                      fontFamily="monospace"
                      fontWeight="500"
                    >
                      {displayLen}
                    </text>
                  </g>
                );
              })}

            {/* Vertices & Handles (Draggable in Irregular Mode) */}
            {vertices.map((v, i) => {
              const s = metersToScreen(v[0], v[1]);
              const isSelected = selectedVertexIndex === i;
              const isFirst = i === 0;

              return (
                <g
                  key={`vert-${i}`}
                  style={{ cursor: mode === 'irregular' ? 'grab' : 'default' }}
                  onMouseDown={(e) => {
                    if (mode === 'irregular') {
                      e.stopPropagation();
                      if (e.button === 0) {
                        setSelectedVertexIndex(i);
                        setDraggingIndex(i);
                      }
                    }
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (mode === 'irregular') {
                      if (!isClosed && isFirst && vertices.length >= 3) {
                        handleClosePolygon();
                      } else {
                        setSelectedVertexIndex(i);
                      }
                    }
                  }}
                >
                  {/* Selection Ring */}
                  {isSelected && (
                    <circle
                      cx={s.x}
                      cy={s.y}
                      r={10}
                      fill="none"
                      stroke="var(--accent-sky)"
                      strokeWidth={1.5}
                      strokeDasharray="2 2"
                    />
                  )}

                  {/* Vertex Center Handle */}
                  <circle
                    cx={s.x}
                    cy={s.y}
                    r={isSelected ? 6 : 5}
                    fill={isFirst ? '#ffffff' : '#000000'}
                    stroke={isSelected ? 'var(--accent-sky)' : '#ffffff'}
                    strokeWidth={1.75}
                  />

                  {/* Index / Label */}
                  <text
                    x={s.x + 8}
                    y={s.y - 6}
                    fill="var(--text-primary)"
                    fontSize="10"
                    fontWeight="600"
                    fontFamily="monospace"
                  >
                    P{i} ({v[0].toFixed(1)}, {v[1].toFixed(1)})
                  </text>
                </g>
              );
            })}
          </svg>

          {/* North Orientation Indicator */}
          <div
            style={{
              position: 'absolute',
              top: '12px',
              right: '12px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-default)',
              padding: '0.4rem 0.6rem',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              fontSize: '0.75rem',
              color: 'var(--text-primary)',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            <span style={{ fontWeight: 700, color: 'var(--accent-sky)' }}>↑ N</span>
            <span style={{ textTransform: 'capitalize', color: 'var(--text-secondary)' }}>
              {orientation}
            </span>
          </div>

          {/* Canvas Help Hint */}
          <div
            style={{
              position: 'absolute',
              bottom: '10px',
              left: '12px',
              fontSize: '0.7rem',
              color: 'var(--text-muted)',
              background: 'rgba(0,0,0,0.5)',
              padding: '0.2rem 0.5rem',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {mode === 'irregular'
              ? !isClosed
                ? 'Click on canvas to add vertex • Click P0 or "Close" when done'
                : 'Drag vertices to reshape • Click vertex to inspect / delete'
              : 'Interactive rectangular boundary live preview'}
          </div>
        </div>

        {/* Irregular Mode: Synchronized Vertex Coordinates Table */}
        {mode === 'irregular' && (
          <div
            data-testid="vertex-table"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              padding: '0.85rem',
              maxHeight: '460px',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Vertex Table (m)</span>
              <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
                {vertices.length} Points
              </span>
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
              <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-default)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '0.35rem 0.2rem', textAlign: 'left' }}>#</th>
                    <th style={{ padding: '0.35rem 0.2rem', textAlign: 'left' }}>X (m)</th>
                    <th style={{ padding: '0.35rem 0.2rem', textAlign: 'left' }}>Y (m)</th>
                    <th style={{ padding: '0.35rem 0.2rem', textAlign: 'right' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {vertices.map((v, i) => (
                    <tr
                      key={i}
                      style={{
                        background: selectedVertexIndex === i ? 'var(--bg-surface)' : 'transparent',
                        borderBottom: '1px solid var(--border-default)',
                      }}
                      onClick={() => setSelectedVertexIndex(i)}
                    >
                      <td style={{ padding: '0.35rem 0.2rem', fontWeight: 600 }}>P{i}</td>
                      <td style={{ padding: '0.35rem 0.2rem' }}>
                        <input
                          type="number"
                          step={0.5}
                          style={{
                            width: '55px',
                            padding: '0.15rem 0.3rem',
                            fontSize: '0.75rem',
                            background: 'var(--bg-canvas)',
                            border: '1px solid var(--border-default)',
                            color: 'var(--text-primary)',
                            borderRadius: '3px',
                          }}
                          value={v[0]}
                          onChange={(e) =>
                            handleUpdateVertexCoord(i, parseFloat(e.target.value) || 0, v[1])
                          }
                        />
                      </td>
                      <td style={{ padding: '0.35rem 0.2rem' }}>
                        <input
                          type="number"
                          step={0.5}
                          style={{
                            width: '55px',
                            padding: '0.15rem 0.3rem',
                            fontSize: '0.75rem',
                            background: 'var(--bg-canvas)',
                            border: '1px solid var(--border-default)',
                            color: 'var(--text-primary)',
                            borderRadius: '3px',
                          }}
                          value={v[1]}
                          onChange={(e) =>
                            handleUpdateVertexCoord(i, v[0], parseFloat(e.target.value) || 0)
                          }
                        />
                      </td>
                      <td style={{ padding: '0.35rem 0.2rem', textAlign: 'right' }}>
                        <button
                          type="button"
                          data-testid="delete-vertex-btn"
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: '#f87171',
                            cursor: 'pointer',
                            fontSize: '0.85rem',
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteVertex(i);
                          }}
                          title="Delete Vertex"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button
              type="button"
              data-testid="add-vertex-btn"
              className="btn btn-secondary btn-sm"
              style={{ width: '100%', fontSize: '0.75rem' }}
              onClick={() => {
                const last = vertices[vertices.length - 1] || [0, 0];
                handleAddVertexAtPoint([last[0] + 5, last[1]]);
              }}
            >
              + Add Vertex
            </button>
          </div>
        )}
      </div>

      {/* Setback and Orientation Controls (Both Modes) */}
      <div
        className="grid grid-cols-4 gap-3"
        style={{
          marginTop: '1rem',
          padding: '0.85rem',
          background: 'var(--bg-secondary)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" style={{ fontSize: '0.75rem' }}>
            Front Setback (m)
          </label>
          <input
            type="number"
            data-testid="input-front-setback"
            step={0.5}
            min={0}
            max={20}
            className="form-input form-input-sm"
            value={frontSetback}
            onChange={(e) =>
              onChange({ ...plotData, frontSetback: Math.max(0, parseFloat(e.target.value) || 0) })
            }
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" style={{ fontSize: '0.75rem' }}>
            Rear Setback (m)
          </label>
          <input
            type="number"
            data-testid="input-rear-setback"
            step={0.5}
            min={0}
            max={20}
            className="form-input form-input-sm"
            value={rearSetback}
            onChange={(e) =>
              onChange({ ...plotData, rearSetback: Math.max(0, parseFloat(e.target.value) || 0) })
            }
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" style={{ fontSize: '0.75rem' }}>
            Side Setback (m)
          </label>
          <input
            type="number"
            data-testid="input-side-setback"
            step={0.5}
            min={0}
            max={20}
            className="form-input form-input-sm"
            value={sideSetback}
            onChange={(e) =>
              onChange({ ...plotData, sideSetback: Math.max(0, parseFloat(e.target.value) || 0) })
            }
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" style={{ fontSize: '0.75rem' }}>
            Orientation
          </label>
          <select
            data-testid="select-orientation"
            className="form-select form-select-sm"
            value={orientation}
            onChange={(e) => onChange({ ...plotData, orientation: e.target.value })}
          >
            <option value="north">North</option>
            <option value="south">South</option>
            <option value="east">East</option>
            <option value="west">West</option>
          </select>
        </div>
      </div>

      {/* Real-Time Metrics & Validation Badges Footer */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingTop: '0.85rem',
          marginTop: '0.85rem',
          borderTop: '1px solid var(--border-default)',
          fontSize: '0.8rem',
        }}
      >
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <span
            data-testid="vertex-count-badge"
            className="badge"
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-default)',
              color: 'var(--text-primary)',
            }}
          >
            {vertices.length} Vertices
          </span>
          <span
            className="badge"
            style={{
              background: isClosed ? 'rgba(34, 197, 94, 0.1)' : 'rgba(245, 158, 11, 0.1)',
              border: `1px solid ${isClosed ? 'rgba(34, 197, 94, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
              color: isClosed ? '#22c55e' : '#f59e0b',
            }}
          >
            {isClosed ? 'Closed Perimeter' : 'Open Boundary'}
          </span>
          <span
            data-testid="gross-area-badge"
            style={{ fontWeight: 600, color: 'var(--text-primary)' }}
          >
            Gross Area: {grossAreaM2.toFixed(1)} m² ({grossAreaSqFt.toFixed(0)} sq ft)
          </span>
        </div>

        <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
          Coordinates exported to backend in real-world meters (x, y) relative to (0,0)
        </div>
      </div>
    </div>
  );
};
