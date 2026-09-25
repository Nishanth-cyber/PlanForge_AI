import React from 'react';
import { FloorPlanCanvas } from '../floorplan/FloorPlanCanvas';
import { RoomInspector } from '../floorplan/RoomInspector';
import type {
  FloorPlan,
  FloorPlanSet,
  GeoRoom,
  ProjectData,
  GenerationResponse,
} from '../../api/types';

interface FloorPlanWorkspaceProps {
  isGenerating: boolean;
  projectData: ProjectData | null;
  generationResponse: GenerationResponse | null;
  activeFloor: number;
  onSelectFloor: (floor: number) => void;
  selectedAlternativeIndex: number;
  onSelectAlternative: (index: number) => void;
  selectedRoom: GeoRoom | null;
  onSelectRoom: (room: GeoRoom | null) => void;
  theme?: 'light' | 'dark';
  onViewTrace?: () => void;
  onViewExports?: () => void;
}

export const FloorPlanWorkspace: React.FC<FloorPlanWorkspaceProps> = ({
  isGenerating,
  projectData,
  generationResponse,
  activeFloor,
  onSelectFloor,
  selectedAlternativeIndex,
  onSelectAlternative,
  selectedRoom,
  onSelectRoom,
  theme = 'light',
  onViewTrace,
  onViewExports,
}) => {
  // Determine active floor plan set (selected alternative or base project)
  const activeFloorPlanSet: FloorPlanSet | undefined = (() => {
    if (!projectData) return undefined;
    if (projectData.alternatives && projectData.alternatives.length > 0) {
      const alt = projectData.alternatives.find((a) => a.index === selectedAlternativeIndex);
      if (alt && alt.floor_plan_set) return alt.floor_plan_set;
    }
    return projectData.floor_plan_set;
  })();

  const activeFloorPlan: FloorPlan | null = (() => {
    if (!activeFloorPlanSet || !activeFloorPlanSet.floor_plans) return null;
    return (
      activeFloorPlanSet.floor_plans.find((fp) => fp.floor_number === activeFloor) ||
      activeFloorPlanSet.floor_plans[0] ||
      null
    );
  })();

  const validationReport = projectData?.validation_report || activeFloorPlanSet?.validation_report;
  const totalErrors = validationReport?.total_errors || (validationReport?.results?.reduce((acc, r) => acc + (r.issues?.filter((i) => i.severity === 'error').length || 0), 0) ?? 0);
  const isOverallValid = validationReport?.overall_valid ?? (totalErrors === 0);

  const availableFloors = activeFloorPlanSet?.floor_plans || [];
  const alternativesList = projectData?.alternatives || [];
  const projectId = projectData?.project_metadata?.project_id || generationResponse?.project_id || '';
  const projectName = projectData?.project_metadata?.project_name || generationResponse?.project_name || 'PlanForge Residence';

  const hasFloorPlan = !!activeFloorPlan;

  return (
    <div className="canvas-workspace-container" data-testid="floor-plan-workspace">
      {/* 1. STATE: GENERATING IN PROGRESS */}
      {isGenerating && (
        <div className="workspace-generating-state" data-testid="generating-state">
          <div className="generating-spinner-box" />
          <h3 className="generating-title">Generating your floor plan...</h3>
          <p className="generating-desc">
            Executing deterministic multi-stage pipeline across spatial allocation, physical geometry drafting, and independent building code validation.
          </p>
          <div className="stage-pills-row">
            <span className="stage-pill active">Requirement Agent</span>
            <span className="stage-pill active">Planning Strategy</span>
            <span className="stage-pill active">ASAA Allocator</span>
            <span className="stage-pill active">Architectural LLM</span>
            <span className="stage-pill active">Geometry Engine</span>
            <span className="stage-pill active">Independent Validator</span>
          </div>
        </div>
      )}

      {/* 2. STATE: PRE-GENERATION EMPTY BLUEPRINT */}
      {!isGenerating && !hasFloorPlan && (
        <div className="workspace-empty-state" data-testid="workspace-empty-state">
          <div className="blueprint-grid-bg" />
          <div className="empty-state-icon-box">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18" />
              <path d="M9 21V9" />
              <circle cx="6" cy="6" r="1" fill="currentColor" />
              <circle cx="15" cy="15" r="1" fill="currentColor" />
            </svg>
          </div>
          <h3 className="empty-state-title">Your floor plan will appear here</h3>
          <p className="empty-state-desc">
            Chat with PlanForge AI on the left or use the interactive cards to define your plot, number of floors, and room requirements.
            Once you confirm, the layout will be generated here in real time.
          </p>
          <div className="empty-state-pills">
            <span className="empty-state-pill">📐 True Meter Scale</span>
            <span className="empty-state-pill">🛡 18 Building Code Check Groups</span>
            <span className="empty-state-pill">🚪 Dynamic Door Swing Arcs</span>
            <span className="empty-state-pill">🪜 Aligned Multi-Floor Stairs</span>
          </div>
        </div>
      )}

      {/* 3. STATE: GENERATED ACTIVE FLOOR PLAN */}
      {!isGenerating && hasFloorPlan && (
        <>
          {/* Top Bar Switchers */}
          <div className="workspace-top-bar">
            {/* Left: Project Title & Floor Selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {projectName}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>
                Floor:
              </span>
              {availableFloors.length > 1 ? (
                <div style={{ display: 'flex', gap: '0.35rem' }}>
                  {availableFloors.map((fp) => (
                    <button
                      key={fp.floor_number}
                      className={`btn ${activeFloor === fp.floor_number ? 'btn-primary' : 'btn-outline'} btn-sm`}
                      onClick={() => {
                        onSelectFloor(fp.floor_number);
                        onSelectRoom(null);
                      }}
                      style={{ padding: '0.25rem 0.65rem', fontSize: '0.8rem' }}
                    >
                      Floor {fp.floor_number}
                    </button>
                  ))}
                </div>
              ) : (
                <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Floor 1</span>
              )}
            </div>

            {/* Middle: Alternative Switcher */}
            {alternativesList.length > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>
                  Alternative:
                </span>
                <div style={{ display: 'flex', gap: '0.35rem' }}>
                  {alternativesList.map((alt) => (
                    <button
                      key={alt.index}
                      className={`btn ${selectedAlternativeIndex === alt.index ? 'btn-primary' : 'btn-outline'} btn-sm`}
                      onClick={() => {
                        onSelectAlternative(alt.index);
                        onSelectRoom(null);
                      }}
                      style={{ padding: '0.25rem 0.65rem', fontSize: '0.8rem' }}
                    >
                      Alt {alt.index}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Right: Validation & Export Link */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '0.2rem 0.6rem',
                  borderRadius: 'var(--radius-full)',
                  backgroundColor: isOverallValid ? 'var(--status-success-bg)' : 'var(--status-danger-bg)',
                  color: isOverallValid ? 'var(--status-success)' : 'var(--status-danger)',
                  border: `1px solid ${isOverallValid ? 'var(--status-success-border)' : 'var(--status-danger-border)'}`,
                }}
              >
                {isOverallValid ? '✓ VALID LAYOUT' : `${totalErrors} CODE ISSUES`}
              </span>

              {projectId && (
                onViewExports ? (
                  <button
                    className="btn btn-outline btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.25rem 0.55rem' }}
                    onClick={() => onViewExports()}
                  >
                    Downloads / Files ↗
                  </button>
                ) : (
                  <a
                    href={`/projects/${encodeURIComponent(projectId)}/export`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-outline btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.25rem 0.55rem', textDecoration: 'none' }}
                  >
                    Downloads / Files ↗
                  </a>
                )
              )}
            </div>
          </div>

          {/* Interactive Vector Canvas */}
          <div className="workspace-canvas-body">
            <FloorPlanCanvas
              floorPlan={activeFloorPlan}
              plotBoundary={activeFloorPlanSet?.plot_boundary || []}
              buildableBoundary={activeFloorPlanSet?.buildable_boundary || []}
              selectedRoom={selectedRoom}
              onSelectRoom={onSelectRoom}
              projectId={projectId}
              alternativeIndex={selectedAlternativeIndex}
              theme={theme}
              orientation={projectData?.requirements?.orientation || 'north'}
            />

            {/* Slide-out Room Inspector Drawer */}
            {selectedRoom && (
              <div
                style={{
                  position: 'absolute',
                  right: '1rem',
                  top: '1rem',
                  width: '320px',
                  maxWidth: '90%',
                  zIndex: 20,
                  boxShadow: 'var(--shadow-lg)',
                }}
              >
                <RoomInspector
                  room={selectedRoom}
                  geometry={activeFloorPlan?.geometry || null}
                  validationResult={activeFloorPlan?.validation}
                  onClose={() => onSelectRoom(null)}
                  onViewTrace={onViewTrace}
                />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
