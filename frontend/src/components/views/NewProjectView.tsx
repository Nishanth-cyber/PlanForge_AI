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

export const ROOM_PRESETS: Record<
  string,
  { label: string; description: string; rooms: Omit<RoomItem, 'id'>[] }
> = {
  '2bhk': {
    label: '2BHK Preset',
    description: 'Living, Dining, Kitchen, Master Bedroom, Bedroom, 2 Bathrooms',
    rooms: [
      { type: 'Living Room', targetArea: 24, count: 1, floor: 1 },
      { type: 'Dining Room', targetArea: 14, count: 1, floor: 1 },
      { type: 'Kitchen', targetArea: 12, count: 1, floor: 1 },
      { type: 'Master Bedroom', targetArea: 18, count: 1, floor: 1 },
      { type: 'Bedroom', targetArea: 14, count: 1, floor: 1 },
      { type: 'Bathroom', targetArea: 6, count: 2, floor: 1 },
    ],
  },
  '3bhk': {
    label: '3BHK Preset',
    description: 'Living, Dining, Kitchen, Master Bedroom, 2 Bedrooms, 3 Bathrooms, Balcony',
    rooms: [
      { type: 'Living Room', targetArea: 28, count: 1, floor: 1 },
      { type: 'Dining Room', targetArea: 16, count: 1, floor: 1 },
      { type: 'Kitchen', targetArea: 14, count: 1, floor: 1 },
      { type: 'Master Bedroom', targetArea: 20, count: 1, floor: 1 },
      { type: 'Bedroom', targetArea: 14, count: 2, floor: 1 },
      { type: 'Bathroom', targetArea: 6, count: 3, floor: 1 },
      { type: 'Balcony', targetArea: 8, count: 1, floor: 1 },
    ],
  },
  'compact_studio': {
    label: 'Compact Studio',
    description: 'Living Room, Kitchen, Bedroom, Bathroom',
    rooms: [
      { type: 'Living Room', targetArea: 20, count: 1, floor: 1 },
      { type: 'Kitchen', targetArea: 10, count: 1, floor: 1 },
      { type: 'Bedroom', targetArea: 14, count: 1, floor: 1 },
      { type: 'Bathroom', targetArea: 6, count: 1, floor: 1 },
    ],
  },
};

export function parseRoomsFromBrief(brief: string): RoomItem[] {
  if (!brief) return [];
  const lines = brief.split('\n');
  const parsedRooms: RoomItem[] = [];
  let currentFloor = 1;

  for (const line of lines) {
    const trimmed = line.trim();
    const floorMatch = trimmed.match(/^floor\s+(\d+)[:.]?/i);
    if (floorMatch) {
      currentFloor = parseInt(floorMatch[1], 10);
      continue;
    }

    if (trimmed.startsWith('-')) {
      const itemText = trimmed.replace(/^[-\s*]+/, '').trim();
      const match = itemText.match(
        /^(\d+)?\s*([a-zA-Z\s]+?)(?:\s+of\s+(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqm|m²))?(?:\s+(?:adjacent|attached|near|separate).*|$)/i
      );
      if (match) {
        const count = match[1] ? parseInt(match[1], 10) : 1;
        const rawType = match[2].trim();
        const area = match[3] ? parseFloat(match[3]) : 0;

        const matchedType =
          ROOM_TYPES.find(
            (t) =>
              t.toLowerCase() === rawType.toLowerCase() ||
              t.toLowerCase().replace(/\s+/g, '') === rawType.toLowerCase().replace(/\s+/g, '')
          ) ||
          rawType
            .split(' ')
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
            .join(' ');

        parsedRooms.push({
          id: `r_init_${parsedRooms.length + 1}`,
          type: matchedType,
          targetArea: area,
          count: count,
          floor: currentFloor,
        });
      }
    }
  }

  return parsedRooms;
}

export function parseFloorsFromBrief(brief: string): number {
  if (!brief) return 1;
  const match = brief.match(/target\s+floors:\s*(\d+)/i) || brief.match(/(\d+)\s+floor/i);
  if (match) {
    return parseInt(match[1], 10) || 1;
  }
  const floorMatches = Array.from(brief.matchAll(/floor\s+(\d+)[:.]?/gi));
  if (floorMatches.length > 0) {
    const floorNums = floorMatches.map((m) => parseInt(m[1], 10));
    return Math.max(...floorNums, 1);
  }
  return 1;
}

export function parsePlotFromBrief(brief: string): Partial<PlotData> | null {
  if (!brief) return null;
  const polyMatch = brief.match(/polygon:\s*([^\n\r]+)/i);
  if (polyMatch) {
    const rawCoords = polyMatch[1];
    const coordMatches = Array.from(rawCoords.matchAll(/\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/g));
    if (coordMatches.length >= 3) {
      const vertices: Point2D[] = coordMatches.map((m) => [parseFloat(m[1]), parseFloat(m[2])]);
      return {
        mode: 'irregular',
        vertices,
        isClosed: true,
      };
    }
  }

  const rectMatch = brief.match(
    /(\d+(?:\.\d+)?)\s*(?:feet|ft|meter|meters|m)?\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(feet|ft|meter|meters|m)/i
  );
  if (rectMatch) {
    const w = parseFloat(rectMatch[1]);
    const l = parseFloat(rectMatch[2]);
    const rawUnit = rectMatch[3].toLowerCase();
    const unit: 'm' | 'ft' = rawUnit === 'feet' || rawUnit === 'ft' ? 'ft' : 'm';
    return {
      mode: 'rectangle',
      width: w,
      length: l,
      unit,
      vertices: [
        [0, 0],
        [unit === 'ft' ? w * 0.3048 : w, 0],
        [unit === 'ft' ? w * 0.3048 : w, unit === 'ft' ? l * 0.3048 : l],
        [0, unit === 'ft' ? l * 0.3048 : l],
      ],
      isClosed: true,
    };
  }

  return null;
}

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
  const [plotData, setPlotData] = useState<PlotData>(() => {
    if (initialBrief) {
      const parsed = parsePlotFromBrief(initialBrief);
      if (parsed) {
        return {
          mode: parsed.mode || 'irregular',
          vertices: parsed.vertices || [
            [0, 0],
            [20, 0],
            [20, 10],
            [10, 10],
            [10, 20],
            [0, 20],
          ],
          width: parsed.width || 20,
          length: parsed.length || 20,
          unit: parsed.unit || 'm',
          frontSetback: parsed.frontSetback ?? 2,
          rearSetback: parsed.rearSetback ?? 2,
          sideSetback: parsed.sideSetback ?? 2,
          orientation: parsed.orientation || 'north',
          isClosed: true,
        };
      }
    }
    return {
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
    };
  });
  const [isPlotValid, setIsPlotValid] = useState<boolean>(true);

  // Step 2: Floors
  const [targetFloors, setTargetFloors] = useState<number>(() => {
    if (initialBrief) return parseFloorsFromBrief(initialBrief);
    return 1;
  });

  // Step 3: Rooms Schedule — STRICTLY EMPTY initially for new projects. Never pre-populated.
  const [rooms, setRooms] = useState<RoomItem[]>(() => {
    if (initialBrief) return parseRoomsFromBrief(initialBrief);
    return [];
  });

  // Step 4: Relationships — STRICTLY EMPTY initially.
  const [relationships, setRelationships] = useState<RelationshipItem[]>([]);

  // Validation error to gate wizard progression if room schedule is empty
  const [roomValidationError, setRoomValidationError] = useState<string | null>(null);

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

  // Handler for adding a room explicitly
  const handleAddRoom = () => {
    const newRoom: RoomItem = {
      id: `r_${Date.now()}_${rooms.length}`,
      type: rooms.length === 0 ? 'Living Room' : 'Bedroom',
      targetArea: plotData.unit === 'm' ? 14 : 150,
      count: 1,
      floor: 1,
    };
    setRooms([...rooms, newRoom]);
    setRoomValidationError(null);
  };

  const handleLoadPreset = (presetKey: string) => {
    const preset = ROOM_PRESETS[presetKey];
    if (!preset) return;
    const isFt = plotData.unit === 'ft';
    const newRooms: RoomItem[] = preset.rooms.map((r, i) => {
      const flr = targetFloors > 1 && (r.type === 'Bedroom' || r.type === 'Master Bedroom' || r.type === 'Balcony') ? 2 : 1;
      return {
        id: `r_${Date.now()}_${i}`,
        type: r.type,
        targetArea: isFt ? Math.round(r.targetArea * 10.7639) : r.targetArea,
        count: r.count,
        floor: Math.min(flr, targetFloors),
      };
    });
    setRooms(newRooms);
    setRoomValidationError(null);
  };

  const handleClearRooms = () => {
    setRooms([]);
    setRelationships([]);
    setRoomValidationError(null);
  };

  const handleStepChange = (targetStep: number) => {
    // Cannot skip Step 3 without defining rooms
    if (targetStep > 3 && rooms.length === 0) {
      setRoomValidationError('Please add at least one room requirement before continuing.');
      setCurrentStep(3);
      return;
    }
    setRoomValidationError(null);
    setCurrentStep(targetStep);
  };

  const handleNextStep = () => {
    if (currentStep === 1 && !isPlotValid) {
      return;
    }
    if (currentStep === 3 && rooms.length === 0) {
      setRoomValidationError('Please add at least one room requirement before continuing.');
      return;
    }
    setRoomValidationError(null);
    setCurrentStep((prev) => Math.min(prev + 1, 5));
  };

  const handleUpdateRoom = (id: string, field: keyof RoomItem, val: any) => {
    setRooms(rooms.map((r) => (r.id === id ? { ...r, [field]: val } : r)));
  };

  const handleDeleteRoom = (id: string) => {
    setRooms(rooms.filter((r) => r.id !== id));
  };

  // Handler for relationships
  const handleAddRelationship = (type: RelationshipItem['type']) => {
    const availableTypes = rooms.length > 0 ? Array.from(new Set(rooms.map((r) => r.type))) : ROOM_TYPES;
    const defaultR1 = availableTypes[0] || 'Living Room';
    const defaultR2 = availableTypes[1] || (type === 'required' ? 'Main Entrance' : availableTypes[0] || 'Kitchen');
    const newRel: RelationshipItem = {
      id: `rel_${Date.now()}_${relationships.length}`,
      type,
      room1: defaultR1,
      room2: defaultR2,
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
    if (rooms.length === 0) {
      setRoomValidationError('Please add at least one room requirement before continuing.');
      setCurrentStep(3);
      return;
    }

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
                onClick={() => handleStepChange(step.id)}
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Rooms</h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>
                  Define the functional room schedule and target floor levels
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                <select
                  data-testid="room-preset-select"
                  className="form-select form-select-sm"
                  style={{ width: 'auto', fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
                  onChange={(e) => {
                    if (e.target.value) handleLoadPreset(e.target.value);
                    e.target.value = '';
                  }}
                  defaultValue=""
                >
                  <option value="" disabled>
                    Load Room Preset...
                  </option>
                  <option value="2bhk">2BHK Preset (6 rooms)</option>
                  <option value="3bhk">3BHK Preset (7 rooms)</option>
                  <option value="compact_studio">Compact Studio (4 rooms)</option>
                </select>

                <button
                  type="button"
                  data-testid="add-room-btn"
                  className="btn btn-primary btn-sm"
                  onClick={handleAddRoom}
                >
                  + Add Room
                </button>

                {rooms.length > 0 && (
                  <button
                    type="button"
                    data-testid="clear-rooms-btn"
                    className="btn btn-outline btn-sm"
                    onClick={handleClearRooms}
                    style={{ color: 'var(--text-muted)' }}
                    title="Clear all rooms to empty state"
                  >
                    Clear All
                  </button>
                )}
              </div>
            </div>

            {/* Validation gate warning message */}
            {roomValidationError && (
              <div
                data-testid="room-validation-error"
                style={{
                  padding: '0.65rem 1rem',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid #ef4444',
                  borderRadius: 'var(--radius-sm)',
                  color: '#f87171',
                  fontSize: '0.85rem',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span>⚠️</span>
                <span>{roomValidationError}</span>
              </div>
            )}

            {/* Empty State when no rooms are defined */}
            {rooms.length === 0 ? (
              <div
                data-testid="rooms-empty-state"
                style={{
                  border: '2px dashed var(--border-default)',
                  borderRadius: 'var(--radius-md)',
                  padding: '3rem 2rem',
                  textAlign: 'center',
                  background: 'var(--bg-secondary)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.75rem',
                }}
              >
                <div style={{ fontSize: '2rem', opacity: 0.7 }}>🏠</div>
                <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-primary)' }}>
                  No rooms added yet
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', maxWidth: '420px', margin: 0 }}>
                  Define your project's room requirements before proceeding. Add rooms individually or choose an architectural preset.
                </p>
                <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <button
                    type="button"
                    data-testid="add-first-room-btn"
                    className="btn btn-primary btn-sm"
                    onClick={handleAddRoom}
                  >
                    + Add Room
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    onClick={() => handleLoadPreset('2bhk')}
                  >
                    Load 2BHK Preset
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    onClick={() => handleLoadPreset('3bhk')}
                  >
                    Load 3BHK Preset
                  </button>
                </div>
              </div>
            ) : (
              /* Editable Room Table (Section 6) */
              <div className="table-container" style={{ border: '1px solid var(--border-default)' }}>
                <table className="data-table" data-testid="room-table" style={{ width: '100%', fontSize: '0.875rem' }}>
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
                            type="button"
                            data-testid="delete-room-btn"
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
            )}
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
              {relationships.length === 0 ? (
                <div
                  style={{
                    padding: '2rem 1rem',
                    textAlign: 'center',
                    border: '1px dashed var(--border-default)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text-muted)',
                    background: 'var(--bg-secondary)',
                    fontSize: '0.85rem',
                  }}
                >
                  <p style={{ margin: '0 0 0.35rem 0', fontWeight: 500, color: 'var(--text-primary)' }}>
                    No custom spatial relationships defined
                  </p>
                  <span style={{ fontSize: '0.775rem' }}>
                    Standard architectural adjacencies will be applied automatically (e.g. social core proximity, acoustic separation between social and private zones). Use the buttons above to specify constraints.
                  </span>
                </div>
              ) : (
                relationships.map((rel) => {
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
                })
              )}
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
                onClick={() => handleStepChange(currentStep - 1)}
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
                onClick={handleNextStep}
              >
                Next →
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                data-testid="generate-plan-btn"
                onClick={handleGenerate}
                disabled={rooms.length === 0}
                style={{
                  padding: '0.65rem 1.75rem',
                  fontSize: '0.95rem',
                  fontWeight: 600,
                  opacity: rooms.length === 0 ? 0.6 : 1,
                  cursor: rooms.length === 0 ? 'not-allowed' : 'pointer',
                }}
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
