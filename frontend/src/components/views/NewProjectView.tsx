import React, { useState, useMemo, useEffect } from 'react';
import type { GenerationRequest, Point2D } from '../../api/types';
import { PlotEditor, type PlotData } from '../plot-editor/PlotEditor';
import { calculatePolygonArea } from '../../utils/geometry';

interface NewProjectViewProps {
  initialBrief?: string;
  initialName?: string;
  onSubmit: (request: GenerationRequest) => void;
  isLoading: boolean;
  onCancel: () => void;
}

export interface RoomItem {
  id: string;
  type: string;
  targetArea: number; // in area unit (m² or sq ft)
  count: number;
  floor: number;
  attachedTo?: string;
}

export interface RelationshipItem {
  id: string;
  type: 'required' | 'preferred' | 'separation' | 'attached';
  room1: string;
  room2: string;
}

export function updateBriefWithPlotData(
  brief: string,
  plot: PlotData,
  floors: number
): string {
  const storyPrefix = floors === 1 ? 'Single floor residence on' : `${floors} floor residence on`;

  let newPlotDesc = '';
  if (plot.mode === 'irregular' && plot.vertices.length >= 3) {
    const coordsStr = plot.vertices.map(([x, y]) => `(${x.toFixed(1)}, ${y.toFixed(1)})`).join(', ');
    newPlotDesc = `${storyPrefix} an irregular plot polygon: ${coordsStr} with front setback: ${plot.frontSetback}m, rear setback: ${plot.rearSetback}m, side setback: ${plot.sideSetback}m.`;
  } else {
    newPlotDesc = `${storyPrefix} a ${plot.width} ${plot.unit === 'm' ? 'meters' : 'feet'} by ${plot.length} ${
      plot.unit === 'm' ? 'meters' : 'feet'
    } plot facing ${plot.orientation} with front setback: ${plot.frontSetback}m, rear setback: ${plot.rearSetback}m, side setback: ${plot.sideSetback}m.`;
  }

  const lines = brief.split('\n');
  let replacedPlot = false;

  const updatedLines = lines.map((line) => {
    const l = line.trim().toLowerCase();
    if (
      !replacedPlot &&
      (l.includes('plot') || l.includes('residence on') || l.includes('polygon:')) &&
      !l.startsWith('-') &&
      !l.startsWith('floor')
    ) {
      replacedPlot = true;
      return newPlotDesc;
    }
    if (l.startsWith('front setback:') || l.startsWith('setback:')) {
      return `Front setback: ${plot.frontSetback}m, rear setback: ${plot.rearSetback}m, side setback: ${plot.sideSetback}m.`;
    }
    return line;
  });

  if (!replacedPlot) {
    return `${newPlotDesc}\n${brief}`;
  }

  return updatedLines.join('\n');
}

const WIZARD_STEPS = [
  { id: 1, title: 'Plot', label: '1. Plot' },
  { id: 2, title: 'Floors', label: '2. Floors' },
  { id: 3, title: 'Rooms', label: '3. Rooms' },
  { id: 4, title: 'Relationships', label: '4. Relationships' },
  { id: 5, title: 'Review', label: '5. Review' },
];

const ROOM_TYPES = [
  'Living Room',
  'Dining Room',
  'Kitchen',
  'Master Bedroom',
  'Bedroom',
  'Bathroom',
  'Powder Room',
  'Balcony',
  'Study Room',
];

export const NewProjectView: React.FC<NewProjectViewProps> = ({
  initialBrief,
  initialName,
  onSubmit,
  isLoading,
  onCancel,
}) => {
  // Current Wizard Step: 1 (Plot), 2 (Floors), 3 (Rooms), 4 (Relationships), 5 (Review)
  const [currentStep, setCurrentStep] = useState<number>(1);

  // Project Info
  const [projectName, setProjectName] = useState<string>(initialName || 'My House');
  const [numAlternatives, setNumAlternatives] = useState<number>(3);
  const [enableRefinement, setEnableRefinement] = useState<boolean>(true);

  // Step 1: Plot Data
  const [plotData, setPlotData] = useState<PlotData>({
    mode: 'irregular',
    vertices: [
      [0, 0],
      [20, 0],
      [20, 10],
      [10, 10],
      [10, 20],
      [0, 20],
    ],
    width: 20,
    length: 20,
    unit: 'm',
    frontSetback: 2,
    rearSetback: 2,
    sideSetback: 2,
    orientation: 'north',
    isClosed: true,
  });
  const [isPlotValid, setIsPlotValid] = useState<boolean>(true);

  // Step 2: Floors
  const [targetFloors, setTargetFloors] = useState<number>(1);

  // Step 3: Rooms Schedule
  const [rooms, setRooms] = useState<RoomItem[]>([
    { id: 'r1', type: 'Living Room', targetArea: 24, count: 1, floor: 1 },
    { id: 'r2', type: 'Dining Room', targetArea: 14, count: 1, floor: 1 },
    { id: 'r3', type: 'Kitchen', targetArea: 12, count: 1, floor: 1 },
    { id: 'r4', type: 'Master Bedroom', targetArea: 18, count: 1, floor: 1 },
    { id: 'r5', type: 'Bedroom', targetArea: 14, count: 1, floor: 1 },
    { id: 'r6', type: 'Bathroom', targetArea: 6, count: 1, floor: 1 },
  ]);

  // Step 4: Relationships
  const [relationships, setRelationships] = useState<RelationshipItem[]>([
    { id: 'rel1', type: 'required', room1: 'Living Room', room2: 'Dining Room' },
    { id: 'rel2', type: 'required', room1: 'Living Room', room2: 'Main Entrance' },
    { id: 'rel3', type: 'preferred', room1: 'Bedroom', room2: 'Bathroom' },
    { id: 'rel4', type: 'separation', room1: 'Kitchen', room2: 'Bedroom' },
    { id: 'rel5', type: 'attached', room1: 'Master Bedroom', room2: 'Bathroom' },
  ]);

  // Step 5: Brief (Auto-compiled)
  const [briefText, setBriefText] = useState<string>(initialBrief || '');
  const [showAdvancedBrief, setShowAdvancedBrief] = useState<boolean>(false);

  // Computed Plot Metrics
  const calculatedPlotArea = useMemo(() => {
    if (plotData.mode === 'rectangle') {
      return plotData.width * plotData.length;
    }
    if (plotData.vertices.length >= 3) {
      return calculatePolygonArea(plotData.vertices);
    }
    return 0;
  }, [plotData]);

  // Total room count
  const totalRoomCount = useMemo(() => {
    return rooms.reduce((acc, r) => acc + (r.count || 1), 0);
  }, [rooms]);

  // Auto-compile brief whenever inputs change
  useEffect(() => {
    if (initialBrief && !briefText) {
      setBriefText(initialBrief);
      return;
    }

    const storyPrefix = targetFloors === 1 ? 'Single floor residence on' : `${targetFloors} floor residence on`;
    let plotDesc = '';
    if (plotData.mode === 'irregular' && plotData.vertices.length >= 3) {
      const coordsStr = plotData.vertices.map(([x, y]) => `(${x.toFixed(1)}, ${y.toFixed(1)})`).join(', ');
      plotDesc = `${storyPrefix} an irregular plot polygon: ${coordsStr} with front setback: ${plotData.frontSetback}m, rear setback: ${plotData.rearSetback}m, side setback: ${plotData.sideSetback}m.`;
    } else {
      plotDesc = `${storyPrefix} a ${plotData.width} ${plotData.unit === 'm' ? 'meters' : 'feet'} by ${plotData.length} ${
        plotData.unit === 'm' ? 'meters' : 'feet'
      } plot facing ${plotData.orientation} with front setback: ${plotData.frontSetback}m, rear setback: ${plotData.rearSetback}m, side setback: ${plotData.sideSetback}m.`;
    }

    const lines: string[] = [plotDesc];
    if (targetFloors > 1) {
      lines.push(`Target floors: ${targetFloors}`);
    }

    // Group rooms by floor
    for (let f = 1; f <= targetFloors; f++) {
      const floorRooms = rooms.filter((r) => r.floor === f);
      if (floorRooms.length > 0) {
        lines.push(`Floor ${f}:`);
        floorRooms.forEach((r) => {
          const areaSuffix = r.targetArea > 0 ? ` of ${r.targetArea} ${plotData.unit === 'm' ? 'sqm' : 'sq ft'}` : '';
          lines.push(`- ${r.count} ${r.type.toLowerCase()}${areaSuffix}`);
        });
      }
    }

    // Relationships
    const requiredRels = relationships.filter((r) => r.type === 'required');
    const attachedRels = relationships.filter((r) => r.type === 'attached');
    const preferredRels = relationships.filter((r) => r.type === 'preferred');
    const sepRels = relationships.filter((r) => r.type === 'separation');

    if (requiredRels.length > 0) {
      lines.push('Required relationships:');
      requiredRels.forEach((r) => lines.push(`- ${r.room1.toLowerCase()} adjacent to ${r.room2.toLowerCase()}`));
    }
    if (attachedRels.length > 0) {
      lines.push('Attached relationships:');
      attachedRels.forEach((r) => lines.push(`- ${r.room1.toLowerCase()} attached to ${r.room2.toLowerCase()}`));
    }
    if (preferredRels.length > 0) {
      lines.push('Preferred relationships:');
      preferredRels.forEach((r) => lines.push(`- ${r.room1.toLowerCase()} near ${r.room2.toLowerCase()}`));
    }
    if (sepRels.length > 0) {
      lines.push('Separation relationships:');
      sepRels.forEach((r) => lines.push(`- ${r.room1.toLowerCase()} separate from ${r.room2.toLowerCase()}`));
    }

    setBriefText(lines.join('\n'));
  }, [plotData, targetFloors, rooms, relationships]);

  // Handler for adding a room
  const handleAddRoom = () => {
    const newRoom: RoomItem = {
      id: `r_${Date.now()}`,
      type: 'Bedroom',
      targetArea: plotData.unit === 'm' ? 14 : 150,
      count: 1,
      floor: 1,
    };
    setRooms([...rooms, newRoom]);
  };

  const handleUpdateRoom = (id: string, field: keyof RoomItem, val: any) => {
    setRooms(rooms.map((r) => (r.id === id ? { ...r, [field]: val } : r)));
  };

  const handleDeleteRoom = (id: string) => {
    setRooms(rooms.filter((r) => r.id !== id));
  };

  // Handler for relationships
  const handleAddRelationship = (type: RelationshipItem['type']) => {
    const newRel: RelationshipItem = {
      id: `rel_${Date.now()}`,
      type,
      room1: rooms[0]?.type || 'Living Room',
      room2: rooms[1]?.type || 'Kitchen',
    };
    setRelationships([...relationships, newRel]);
  };

  const handleDeleteRelationship = (id: string) => {
    setRelationships(relationships.filter((r) => r.id !== id));
  };

  const handleUpdateRelationship = (id: string, field: 'room1' | 'room2' | 'type', val: string) => {
    setRelationships(relationships.map((r) => (r.id === id ? { ...r, [field]: val } : r)));
  };

  // Generate Submission
  const handleGenerate = () => {
    let finalShape: Point2D[] | undefined = undefined;
    if (plotData.mode === 'irregular' && plotData.vertices.length >= 3) {
      finalShape = plotData.vertices;
    }

    const payload: GenerationRequest = {
      project_name: projectName || 'Residential Project',
      brief: briefText,
      num_alternatives: numAlternatives,
      enable_refinement: enableRefinement,
      max_refinement_iterations: 3,
      enable_rendering: true,
      enable_exports: true,
      create_zip: false,
      plot_shape: finalShape,
    };

    onSubmit(payload);
  };

  // Generation Stages Checklist (Section 9)
  const [activeStageIndex, setActiveStageIndex] = useState<number>(0);
  const GENERATION_STAGES = [
    'Requirements',
    'Planning',
    'ASAA Allocation',
    'Architectural Design',
    'Geometry',
    'Validation',
    'Refinement',
    'Alternatives',
  ];

  useEffect(() => {
    if (!isLoading) {
      setActiveStageIndex(0);
      return;
    }
    const interval = setInterval(() => {
      setActiveStageIndex((prev) => (prev < GENERATION_STAGES.length - 1 ? prev + 1 : prev));
    }, 1400);
    return () => clearInterval(interval);
  }, [isLoading]);

  if (isLoading) {
    return (
      <div style={{ maxWidth: '640px', margin: '3rem auto', textAlign: 'left' }}>
        <div className="card" style={{ padding: '2rem 2.5rem' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1.5rem', color: 'var(--text-primary)' }}>
            Generating your floor plans...
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            {GENERATION_STAGES.map((stage, idx) => {
              const isDone = idx < activeStageIndex;
              const isCurrent = idx === activeStageIndex;
              return (
                <div
                  key={stage}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.5rem 0',
                    borderBottom: '1px solid var(--border-subtle)',
                    fontSize: '0.9rem',
                    color: isCurrent ? 'var(--text-primary)' : isDone ? 'var(--text-secondary)' : 'var(--text-muted)',
                    fontWeight: isCurrent ? 600 : 400,
                  }}
                >
                  <span>{stage}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem' }}>
                    {isDone ? (
                      <span style={{ color: 'var(--status-success)' }}>✓</span>
                    ) : isCurrent ? (
                      <span style={{ color: 'var(--text-primary)' }}>●</span>
                    ) : (
                      <span style={{ color: 'var(--border-strong)' }}>○</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: '100%', maxWidth: '1400px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header & Project Name Input */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>New Project</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0.2rem 0 0' }}>
            Configure plot, floors, room schedule, and spatial relationships
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Project Name:</label>
          <input
            type="text"
            className="form-input"
            data-testid="input-project-name"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            style={{ width: '220px', padding: '0.35rem 0.65rem', fontSize: '0.875rem' }}
          />
        </div>
      </div>

      {/* 5-Step Progress Indicator (Section 4) */}
      <div
        className="card"
        style={{
          padding: '0.75rem 1.25rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--bg-secondary)',
        }}
      >
        {WIZARD_STEPS.map((step, idx) => {
          const isActive = currentStep === step.id;
          const isPassed = currentStep > step.id;
          return (
            <React.Fragment key={step.id}>
              <div
                data-testid={`wizard-step-tab-${step.id}`}
                onClick={() => setCurrentStep(step.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  cursor: 'pointer',
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? 'var(--text-primary)' : isPassed ? 'var(--text-secondary)' : 'var(--text-muted)',
                  fontSize: '0.875rem',
                }}
              >
                <span
                  style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.75rem',
                    background: isActive ? 'var(--text-primary)' : isPassed ? 'var(--border-strong)' : 'var(--border-default)',
                    color: isActive ? 'var(--bg-primary)' : 'var(--text-primary)',
                  }}
                >
                  {isPassed ? '✓' : step.id}
                </span>
                <span>{step.title}</span>
              </div>
              {idx < WIZARD_STEPS.length - 1 && (
                <div style={{ flex: 1, height: '1px', background: 'var(--border-default)', margin: '0 0.75rem' }} />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Step Content Container */}
      <div className="card" style={{ padding: '1.5rem' }}>
        {/* STEP 1: PLOT (Section 5) */}
        {currentStep === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Plot Boundary</h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>
                  Define the legal parcel boundary and municipal setbacks
                </p>
              </div>
            </div>

            {/* Plot Editor Component */}
            <PlotEditor
              plotData={plotData}
              onChange={setPlotData}
              onValidationChange={(valid) => setIsPlotValid(valid)}
            />
            {!isPlotValid && (
              <div style={{ color: '#f87171', fontSize: '0.8rem' }}>
                Please ensure plot boundary is closed with at least 3 non-intersecting vertices.
              </div>
            )}
          </div>
        )}

        {/* STEP 2: FLOORS */}
        {currentStep === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Floor Configuration</h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>
                Select number of floors for the residence
              </p>
            </div>

            <div style={{ display: 'flex', gap: '1rem' }}>
              <button
                type="button"
                className={`btn ${targetFloors === 1 ? 'btn-primary' : 'btn-outline'}`}
                data-testid="target-floors-1"
                onClick={() => setTargetFloors(1)}
                style={{ padding: '1.25rem 2rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.35rem' }}
              >
                <span style={{ fontSize: '1.2rem', fontWeight: 700 }}>1 Floor</span>
                <span style={{ fontSize: '0.8rem', opacity: 0.8 }}>Single Story Bungalow</span>
              </button>

              <button
                type="button"
                className={`btn ${targetFloors === 2 ? 'btn-primary' : 'btn-outline'}`}
                data-testid="target-floors-2"
                onClick={() => setTargetFloors(2)}
                style={{ padding: '1.25rem 2rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.35rem' }}
              >
                <span style={{ fontSize: '1.2rem', fontWeight: 700 }}>2 Floors</span>
                <span style={{ fontSize: '0.8rem', opacity: 0.8 }}>Duplex with Vertical Staircase</span>
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: ROOMS (Section 6) */}
        {currentStep === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Rooms</h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>
                  Define the functional room schedule and target floor levels
                </p>
              </div>
              <button className="btn btn-outline btn-sm" onClick={handleAddRoom}>
                + Add Room
              </button>
            </div>

            {/* Editable Room Table (Section 6) */}
            <div className="table-container" style={{ border: '1px solid var(--border-default)' }}>
              <table className="data-table" style={{ width: '100%', fontSize: '0.875rem' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', padding: '0.65rem 0.75rem' }}>Room</th>
                    <th style={{ textAlign: 'center', padding: '0.65rem 0.75rem', width: '100px' }}>Count</th>
                    <th style={{ textAlign: 'center', padding: '0.65rem 0.75rem', width: '100px' }}>Floor</th>
                    <th style={{ textAlign: 'right', padding: '0.65rem 0.75rem', width: '140px' }}>
                      Min Area ({plotData.unit === 'm' ? 'm²' : 'sq ft'})
                    </th>
                    <th style={{ textAlign: 'center', padding: '0.65rem 0.75rem', width: '60px' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rooms.map((room) => (
                    <tr key={room.id}>
                      <td style={{ padding: '0.5rem 0.75rem' }}>
                        <select
                          className="form-select"
                          value={room.type}
                          onChange={(e) => handleUpdateRoom(room.id, 'type', e.target.value)}
                          style={{ padding: '0.3rem 0.5rem', fontSize: '0.875rem', width: '100%' }}
                        >
                          {ROOM_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                        <input
                          type="number"
                          className="form-input"
                          min={1}
                          max={10}
                          value={room.count}
                          onChange={(e) => handleUpdateRoom(room.id, 'count', parseInt(e.target.value) || 1)}
                          style={{ width: '60px', textAlign: 'center', padding: '0.3rem' }}
                        />
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                        <select
                          className="form-select"
                          value={room.floor}
                          onChange={(e) => handleUpdateRoom(room.id, 'floor', parseInt(e.target.value) || 1)}
                          style={{ padding: '0.3rem', width: '70px', textAlign: 'center' }}
                        >
                          {Array.from({ length: targetFloors }, (_, i) => i + 1).map((f) => (
                            <option key={f} value={f}>
                              Floor {f}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>
                        <input
                          type="number"
                          className="form-input"
                          min={0}
                          value={room.targetArea || ''}
                          placeholder="Auto"
                          onChange={(e) => handleUpdateRoom(room.id, 'targetArea', parseFloat(e.target.value) || 0)}
                          style={{ width: '90px', textAlign: 'right', padding: '0.3rem' }}
                        />
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => handleDeleteRoom(room.id)}
                          style={{ padding: '0.2rem 0.5rem', color: '#f87171' }}
                          title="Remove Room"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* STEP 4: RELATIONSHIPS (Section 7) */}
        {currentStep === 4 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Spatial Relationships</h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>
                  Define adjacencies, private attached suites, and acoustic separations
                </p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-outline btn-sm" onClick={() => handleAddRelationship('required')}>
                  + Required
                </button>
                <button className="btn btn-outline btn-sm" onClick={() => handleAddRelationship('separation')}>
                  + Separation
                </button>
                <button className="btn btn-outline btn-sm" onClick={() => handleAddRelationship('attached')}>
                  + Attached
                </button>
              </div>
            </div>

            {/* Compact Relationship Rows (Section 7) */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {relationships.map((rel) => {
                const badgeClass =
                  rel.type === 'required'
                    ? 'badge-info'
                    : rel.type === 'attached'
                    ? 'badge-success'
                    : rel.type === 'separation'
                    ? 'badge-danger'
                    : 'badge-neutral';
                const symbol = rel.type === 'separation' ? '↔ (separate)' : '→ (adjacent)';

                return (
                  <div
                    key={rel.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.5rem 0.75rem',
                      background: 'var(--bg-secondary)',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '0.875rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <span className={`badge ${badgeClass}`} style={{ width: '85px', textAlign: 'center' }}>
                        {rel.type}
                      </span>
                      <select
                        className="form-select"
                        value={rel.room1}
                        onChange={(e) => handleUpdateRelationship(rel.id, 'room1', e.target.value)}
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem' }}
                      >
                        {ROOM_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                      <span style={{ color: 'var(--text-muted)' }}>{symbol}</span>
                      <select
                        className="form-select"
                        value={rel.room2}
                        onChange={(e) => handleUpdateRelationship(rel.id, 'room2', e.target.value)}
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem' }}
                      >
                        <option value="Main Entrance">Main Entrance</option>
                        {ROOM_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={() => handleDeleteRelationship(rel.id)}
                      style={{ padding: '0.15rem 0.45rem', fontSize: '0.75rem' }}
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* STEP 5: REVIEW (Section 8) */}
        {currentStep === 5 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Review Project</h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>
                Verify program specifications before generating floor plan alternatives
              </p>
            </div>

            {/* Simple Summary Table (Section 8) */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '1rem',
                background: 'var(--bg-secondary)',
                padding: '1.25rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-default)',
              }}
            >
              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                  PROJECT
                </span>
                <div style={{ fontSize: '1rem', fontWeight: 600, marginTop: '0.25rem' }}>{projectName}</div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                  PLOT
                </span>
                <div style={{ fontSize: '0.95rem', fontWeight: 600, marginTop: '0.25rem' }}>
                  {plotData.mode === 'rectangle' ? `${plotData.width} × ${plotData.length} ${plotData.unit}` : `${plotData.vertices.length}-gon`}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {calculatedPlotArea.toFixed(1)} {plotData.unit === 'm' ? 'm²' : 'sq ft'} ({targetFloors} Floor{targetFloors > 1 ? 's' : ''})
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                  ROOMS
                </span>
                <div style={{ fontSize: '0.95rem', fontWeight: 600, marginTop: '0.25rem' }}>{totalRoomCount} rooms</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {rooms.slice(0, 3).map((r) => r.type).join(', ')}...
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                  RELATIONSHIPS
                </span>
                <div style={{ fontSize: '0.95rem', fontWeight: 600, marginTop: '0.25rem' }}>
                  {relationships.length} defined
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {relationships.filter((r) => r.type === 'required').length} required,{' '}
                  {relationships.filter((r) => r.type === 'separation').length} separation
                </div>
              </div>
            </div>

            {/* Strategy Options */}
            <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center', fontSize: '0.85rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <label style={{ color: 'var(--text-secondary)' }}>Alternatives:</label>
                <select
                  className="form-select"
                  value={numAlternatives}
                  onChange={(e) => setNumAlternatives(parseInt(e.target.value) || 3)}
                  style={{ padding: '0.25rem 0.5rem', width: '75px' }}
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                  <option value={4}>4</option>
                </select>
              </div>

              <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={enableRefinement}
                  onChange={(e) => setEnableRefinement(e.target.checked)}
                />
                Enable Closed-Loop Refinement
              </label>
            </div>

            {/* Compiled Brief Accordion / Textarea */}
            <div>
              <button
                type="button"
                onClick={() => setShowAdvancedBrief(!showAdvancedBrief)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  padding: 0,
                  textDecoration: 'underline',
                  marginBottom: '0.5rem',
                }}
              >
                {showAdvancedBrief ? 'Hide Compiled Brief ▲' : 'View / Edit Compiled Brief ▼'}
              </button>

              {showAdvancedBrief && (
                <textarea
                  className="form-input"
                  data-testid="brief-textarea"
                  rows={6}
                  value={briefText}
                  onChange={(e) => setBriefText(e.target.value)}
                  style={{ width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', padding: '0.5rem' }}
                />
              )}
            </div>
          </div>
        )}

        {/* Wizard Bottom Navigation Buttons */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: '1.5rem',
            paddingTop: '1rem',
            borderTop: '1px solid var(--border-default)',
          }}
        >
          <div>
            {currentStep > 1 ? (
              <button
                type="button"
                className="btn btn-outline"
                data-testid="wizard-prev-btn"
                onClick={() => setCurrentStep(currentStep - 1)}
              >
                ← Back
              </button>
            ) : (
              <button type="button" className="btn btn-outline" onClick={onCancel}>
                Cancel
              </button>
            )}
          </div>

          <div>
            {currentStep < 5 ? (
              <button
                type="button"
                className="btn btn-primary"
                data-testid="wizard-next-btn"
                onClick={() => setCurrentStep(currentStep + 1)}
              >
                Next →
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                data-testid="generate-plan-btn"
                onClick={handleGenerate}
                style={{ padding: '0.65rem 1.75rem', fontSize: '0.95rem', fontWeight: 600 }}
              >
                Generate Floor Plans
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
