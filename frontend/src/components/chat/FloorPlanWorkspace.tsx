import React, { useState, useEffect } from 'react';
import { ClarificationPanel } from './ClarificationPanel';
import { FloorPlanCanvas } from '../floorplan/FloorPlanCanvas';
import { RoomInspector } from '../floorplan/RoomInspector';
import { getValidationDisplayStatus } from '../../utils/validationStatus';
import { editProjectDesign, undoProjectDesign, getProjectVersions } from '../../api/projects';
import type {
  FloorPlan,
  FloorPlanSet,
  GeoRoom,
  ProjectData,
  GenerationResponse,
  VersionSummary,
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
  onClarificationSubmit?: (
    selectedOptionId?: string,
    responseText?: string,
    numericOverrides?: Record<string, number>
  ) => Promise<void>;
  onClarificationResume?: () => Promise<void>;
  onClarificationCancel?: () => Promise<void>;
  onProjectUpdated?: () => Promise<void>;
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
  onClarificationSubmit,
  onClarificationResume,
  onClarificationCancel,
  onProjectUpdated,
}) => {
  // Editing state
  const [editInput, setEditInput] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editStatusText, setEditStatusText] = useState<string | null>(null);
  const [editFeedback, setEditFeedback] = useState<{
    success: boolean;
    summary: string;
    versionId?: string;
    canUndo?: boolean;
    error?: string;
  } | null>(null);
  const [canUndo, setCanUndo] = useState<boolean>(false);
  const [currentVersionId, setCurrentVersionId] = useState<string>('v1');
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);
  const [versionsList, setVersionsList] = useState<VersionSummary[]>([]);
  const [isLoadingVersions, setIsLoadingVersions] = useState<boolean>(false);

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

  const validationStatus = getValidationDisplayStatus(
    validationReport,
    projectData?.refinement_result,
    projectData?.status || generationResponse?.status
  );

  const availableFloors = activeFloorPlanSet?.floor_plans || [];
  const alternativesList = projectData?.alternatives || [];
  const projectId = projectData?.project_metadata?.project_id || generationResponse?.project_id || '';
  const projectName = projectData?.project_metadata?.project_name || generationResponse?.project_name || 'PlanForge Residence';

  const hasFloorPlan = !!activeFloorPlan;

  // Load version history when opened
  const loadVersionHistory = async () => {
    if (!projectId) return;
    setIsLoadingVersions(true);
    try {
      const vList = await getProjectVersions(projectId);
      setVersionsList(vList);
      if (vList.length > 0) {
        setCurrentVersionId(vList[vList.length - 1].version_id);
        setCanUndo(vList.length > 1);
      }
    } catch (e) {
      console.warn('Could not load version history', e);
    } finally {
      setIsLoadingVersions(false);
    }
  };

  useEffect(() => {
    if (projectId && hasFloorPlan) {
      loadVersionHistory();
    }
  }, [projectId, hasFloorPlan]);

  // Handle natural-language design editing
  const handleApplyEdit = async (instructionToUse?: string) => {
    const text = (instructionToUse || editInput).trim();
    if (!text || !projectId || isEditing) return;

    setIsEditing(true);
    setEditStatusText('Analyzing editing request & identifying target spaces...');
    setEditFeedback(null);

    try {
      setTimeout(() => {
        setEditStatusText('Applying architectural modifications & drafting CAD geometry...');
      }, 700);
      setTimeout(() => {
        setEditStatusText('Executing independent building code validation...');
      }, 1400);

      const resp = await editProjectDesign(projectId, {
        instruction: text,
        floor_number: activeFloor,
        alternative_index: selectedAlternativeIndex,
      });

      if (resp.success) {
        setEditFeedback({
          success: true,
          summary: resp.summary,
          versionId: resp.version_id,
          canUndo: resp.can_undo,
        });
        setCurrentVersionId(resp.version_id);
        setCanUndo(resp.can_undo);
        setEditInput('');
        if (onProjectUpdated) {
          await onProjectUpdated();
        }
        await loadVersionHistory();
      } else {
        setEditFeedback({
          success: false,
          summary: resp.summary || resp.error_message || 'Could not apply change.',
          error: resp.error_message,
          canUndo: resp.can_undo,
        });
      }
    } catch (err: any) {
      setEditFeedback({
        success: false,
        summary: err.message || 'Edit failed to execute.',
        error: err.message,
      });
    } finally {
      setIsEditing(false);
      setEditStatusText(null);
    }
  };

  // Handle undo design
  const handleUndo = async () => {
    if (!projectId || !canUndo || isEditing) return;
    setIsEditing(true);
    setEditStatusText('Restoring previous design version & re-verifying geometry...');
    try {
      const resp = await undoProjectDesign(projectId);
      if (resp.success) {
        setEditFeedback({
          success: true,
          summary: `Restored previous design version (${resp.version_id}).`,
          versionId: resp.version_id,
          canUndo: resp.can_undo,
        });
        setCurrentVersionId(resp.version_id);
        setCanUndo(resp.can_undo);
        if (onProjectUpdated) {
          await onProjectUpdated();
        }
        await loadVersionHistory();
      }
    } catch (err: any) {
      setEditFeedback({
        success: false,
        summary: err.message || 'Undo operation failed.',
      });
    } finally {
      setIsEditing(false);
      setEditStatusText(null);
    }
  };

  const sampleEdits = [
    'Make the master bedroom larger',
    'Change the living room to an L-shaped design',
    'Add a window to the master bedroom',
    'Move the entrance to the east side',
    'Increase kitchen area to 15 square meters',
    'Improve circulation flow',
  ];

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

      {/* 2. STATE: INTERACTIVE CLARIFICATION REQUIRED */}
      {!isGenerating && generationResponse?.pending_clarification && (
        <div style={{ overflowY: 'auto', height: '100%', padding: '1.5rem', width: '100%' }}>
          <ClarificationPanel
            projectId={projectId}
            clarification={generationResponse.pending_clarification}
            onSubmitResponse={onClarificationSubmit || (async () => {})}
            onResume={onClarificationResume}
            onCancel={onClarificationCancel}
          />
        </div>
      )}

      {/* 3. STATE: PRE-GENERATION EMPTY BLUEPRINT */}
      {!isGenerating && !hasFloorPlan && !generationResponse?.pending_clarification && (
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

      {/* 4. STATE: GENERATED ACTIVE FLOOR PLAN */}
      {!isGenerating && hasFloorPlan && !generationResponse?.pending_clarification && (
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

            {/* Right: Versioning, Undo & Validation */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {/* Version Badge & History toggle */}
              <button
                className="btn btn-outline btn-sm"
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.55rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                onClick={() => {
                  setIsHistoryOpen(!isHistoryOpen);
                  loadVersionHistory();
                }}
                title="View edit version history"
              >
                <span>📜 {currentVersionId.toUpperCase()}</span>
                {versionsList.length > 1 && <span style={{ fontSize: '0.7rem', opacity: 0.8 }}>({versionsList.length})</span>}
              </button>

              {/* Undo Button */}
              {canUndo && (
                <button
                  className="btn btn-outline btn-sm"
                  style={{ fontSize: '0.75rem', padding: '0.2rem 0.55rem', color: 'var(--color-primary)' }}
                  onClick={handleUndo}
                  disabled={isEditing}
                  title="Undo last edit and restore previous design"
                >
                  ↶ Undo
                </button>
              )}

              {/* Validation Badge */}
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '0.2rem 0.6rem',
                  borderRadius: 'var(--radius-full)',
                  backgroundColor: validationStatus.type === 'valid' || validationStatus.type === 'refined' ? 'var(--status-success-bg)' : 'var(--status-danger-bg)',
                  color: validationStatus.type === 'valid' || validationStatus.type === 'refined' ? 'var(--status-success)' : 'var(--status-danger)',
                  border: `1px solid ${validationStatus.type === 'valid' || validationStatus.type === 'refined' ? 'var(--status-success-border)' : 'var(--status-danger-border)'}`,
                }}
              >
                {validationStatus.label}
              </span>

              {projectId && (
                onViewExports ? (
                  <button
                    className="btn btn-outline btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.25rem 0.55rem' }}
                    onClick={() => onViewExports()}
                  >
                    Downloads ↗
                  </button>
                ) : (
                  <a
                    href={`/projects/${encodeURIComponent(projectId)}/export`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-outline btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.25rem 0.55rem', textDecoration: 'none' }}
                  >
                    Downloads ↗
                  </a>
                )
              )}
            </div>
          </div>

          {/* EDIT DESIGN INTERACTIVE BAR (Section 9) */}
          <div
            style={{
              padding: '0.65rem 1rem',
              backgroundColor: 'var(--bg-surface)',
              borderBottom: '1px solid var(--border-color)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            }}
          >
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                <span>✨ Edit Design:</span>
              </div>
              <input
                type="text"
                className="input input-sm"
                placeholder="Type instruction (e.g. 'Make master bedroom larger', 'Change living room to L-shaped', 'Add window')..."
                value={editInput}
                onChange={(e) => setEditInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleApplyEdit();
                }}
                disabled={isEditing}
                style={{ flex: 1, fontSize: '0.825rem' }}
              />
              <button
                className="btn btn-primary btn-sm"
                onClick={() => handleApplyEdit()}
                disabled={isEditing || !editInput.trim()}
                style={{ padding: '0.35rem 0.85rem', fontSize: '0.8rem', whiteSpace: 'nowrap' }}
              >
                {isEditing ? 'Applying...' : 'Apply Edit'}
              </button>
            </div>

            {/* Quick sample instruction chips */}
            {!isEditing && !editFeedback && (
              <div style={{ display: 'flex', gap: '0.35rem', overflowX: 'auto', paddingBottom: '0.1rem', scrollbarWidth: 'none' }}>
                <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)', alignSelf: 'center', marginRight: '0.2rem' }}>Suggestions:</span>
                {sampleEdits.map((sample, idx) => (
                  <button
                    key={idx}
                    className="btn btn-outline btn-xs"
                    onClick={() => handleApplyEdit(sample)}
                    style={{ fontSize: '0.725rem', padding: '0.15rem 0.45rem', whiteSpace: 'nowrap', borderRadius: 'var(--radius-full)' }}
                  >
                    {sample}
                  </button>
                ))}
              </div>
            )}

            {/* Editing Progress State Indicator */}
            {isEditing && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.6rem',
                  padding: '0.4rem 0.75rem',
                  backgroundColor: 'var(--status-info-bg, rgba(59, 130, 246, 0.08))',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.8rem',
                  color: 'var(--color-primary)',
                }}
              >
                <div className="generating-spinner-box" style={{ width: '14px', height: '14px', borderWidth: '2px', margin: 0 }} />
                <span>{editStatusText || 'Modifying floor plan...'}</span>
              </div>
            )}

            {/* Edit Feedback / Summary Banner */}
            {editFeedback && !isEditing && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.4rem 0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.8rem',
                  backgroundColor: editFeedback.success ? 'var(--status-success-bg)' : 'var(--status-danger-bg)',
                  color: editFeedback.success ? 'var(--status-success)' : 'var(--status-danger)',
                  border: `1px solid ${editFeedback.success ? 'var(--status-success-border)' : 'var(--status-danger-border)'}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <span>{editFeedback.success ? '✓' : '⚠'}</span>
                  <span>{editFeedback.summary}</span>
                </div>
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  {editFeedback.canUndo && (
                    <button
                      className="btn btn-xs"
                      onClick={handleUndo}
                      style={{ fontSize: '0.725rem', padding: '0.1rem 0.45rem' }}
                    >
                      Undo
                    </button>
                  )}
                  <button
                    onClick={() => setEditFeedback(null)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: '0.9rem' }}
                  >
                    ×
                  </button>
                </div>
              </div>
            )}
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

            {/* Version History Modal / Drawer */}
            {isHistoryOpen && (
              <div
                style={{
                  position: 'absolute',
                  right: '1rem',
                  top: '1rem',
                  width: '360px',
                  maxWidth: '92%',
                  maxHeight: '80%',
                  zIndex: 30,
                  backgroundColor: 'var(--bg-card)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: 'var(--shadow-xl)',
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                }}
              >
                <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600 }}>Design Version History</h4>
                  <button
                    onClick={() => setIsHistoryOpen(false)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.1rem', color: 'var(--text-muted)' }}
                  >
                    ×
                  </button>
                </div>
                <div style={{ padding: '0.75rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                  {isLoadingVersions && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Loading versions...</span>}
                  {versionsList.map((ver) => (
                    <div
                      key={ver.version_id}
                      style={{
                        padding: '0.6rem',
                        borderRadius: 'var(--radius-sm)',
                        border: ver.version_id === currentVersionId ? '1px solid var(--color-primary)' : '1px solid var(--border-color)',
                        backgroundColor: ver.version_id === currentVersionId ? 'var(--bg-surface)' : 'transparent',
                        fontSize: '0.8rem',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                        <span style={{ fontWeight: 700, color: ver.version_id === currentVersionId ? 'var(--color-primary)' : 'inherit' }}>
                          {ver.version_id.toUpperCase()} {ver.version_id === currentVersionId ? '(Active)' : ''}
                        </span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {new Date(ver.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.2rem' }}>
                        {ver.instruction}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        Score: {ver.validation_score}/100 • Errors: {ver.total_errors}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
