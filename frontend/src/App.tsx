import { useState, useEffect } from 'react';
import { Header } from './components/layout/Header';
import { TabNav, type ActiveTab } from './components/layout/TabNav';
import { FloorPlanCanvas } from './components/floorplan/FloorPlanCanvas';
import { RoomInspector } from './components/floorplan/RoomInspector';

import { HomeView } from './components/views/HomeView';
import { ProjectsView } from './components/views/ProjectsView';
import { BenchmarksView } from './components/views/BenchmarksView';
import { NewProjectView } from './components/views/NewProjectView';
import { PlotView } from './components/views/PlotView';
import { AlternativesView } from './components/views/AlternativesView';
import { ValidationView } from './components/views/ValidationView';
import { ExplainabilityView } from './components/views/ExplainabilityView';
import { RefinementView } from './components/views/RefinementView';
import { ExportView } from './components/views/ExportView';

import {
  getProjectData,
  generateFloorPlan,
  submitClarificationResponse,
  resumeProject,
  cancelProject,
  editProjectDesign,
  undoProjectDesign,
  getProjectVersions,
} from './api/projects';
import type {
  ProjectData,
  GenerationRequest,
  GenerationResponse,
  GeoRoom,
  FloorPlan,
  FloorPlanSet,
  VersionSummary,
} from './api/types';

import { ConversationalStudio } from './components/chat/ConversationalStudio';

import './styles/index.css';
import './styles/components.css';
import { getValidationDisplayStatus } from './utils/validationStatus';

export function App() {
  const [currentView, setCurrentView] = useState<'home' | 'assistant' | 'projects' | 'benchmarks' | 'new_project' | 'project_detail'>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const v = params.get('view');
      if (v === 'assistant' || v === 'projects' || v === 'benchmarks' || v === 'new_project' || v === 'project_detail') {
        return v;
      }
      if (params.get('project')) return 'project_detail';
    }
    return 'home';
  });
  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const t = params.get('tab') as ActiveTab;
      if (t && ['overview', 'plot', 'alternatives', 'validation', 'refinement', 'explainability', 'export'].includes(t)) {
        return t;
      }
    }
    return 'overview';
  });

  const [activeProjectId, setActiveProjectId] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get('project') || null;
    }
    return null;
  });
  const [projectData, setProjectData] = useState<ProjectData | null>(null);
  const [generationResponse, setGenerationResponse] = useState<GenerationResponse | null>(null);

  const [activeFloor, setActiveFloor] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const f = parseInt(params.get('floor') || '1', 10);
      return isNaN(f) ? 1 : f;
    }
    return 1;
  });
  const [selectedAlternativeIndex, setSelectedAlternativeIndex] = useState<number>(1);
  const [selectedRoom, setSelectedRoom] = useState<GeoRoom | null>(null);

  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isLoadingProject, setIsLoadingProject] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Edit Existing Design State (Section 9)
  const [editInput, setEditInput] = useState<string>('');
  const [isEditingDesign, setIsEditingDesign] = useState<boolean>(false);
  const [editSummary, setEditSummary] = useState<string | null>(null);
  const [canUndoDesign, setCanUndoDesign] = useState<boolean>(false);
  const [versionHistory, setVersionHistory] = useState<VersionSummary[]>([]);
  const [isVersionModalOpen, setIsVersionModalOpen] = useState<boolean>(false);

  // Preset briefs for NewProjectView
  const [initialBrief, setInitialBrief] = useState<string | undefined>(undefined);
  const [initialName, setInitialName] = useState<string | undefined>(undefined);

  // Theme state: default to 'light' (clean white/black paper mode) with user toggle
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (localStorage.getItem('planforge_theme') as 'light' | 'dark') || 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('planforge_theme', theme);
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  };

  // Load project data when activeProjectId changes
  useEffect(() => {
    if (!activeProjectId) return;
    let mounted = true;
    setIsLoadingProject(true);
    setErrorMessage(null);

    getProjectData(activeProjectId)
      .then((data) => {
        if (mounted) {
          setProjectData(data);
          setActiveFloor(1);
          setSelectedRoom(null);
        }
      })
      .catch((err) => {
        if (mounted) {
          console.error('Failed to load project data', err);
          setErrorMessage(err.message || 'Failed to load project data');
        }
      })
      .finally(() => {
        if (mounted) setIsLoadingProject(false);
      });

    return () => {
      mounted = false;
    };
  }, [activeProjectId]);

  const handleReloadProjectData = async () => {
    if (!activeProjectId) return;
    try {
      const data = await getProjectData(activeProjectId);
      setProjectData(data);
      const vList = await getProjectVersions(activeProjectId);
      setVersionHistory(vList);
      setCanUndoDesign(vList.length > 1);
    } catch (err: any) {
      console.warn('Failed to refresh project data', err);
    }
  };

  const handleEditProject = async (instruction?: string) => {
    const text = (instruction || editInput).trim();
    if (!text || !activeProjectId || isEditingDesign) return;
    setIsEditingDesign(true);
    setEditSummary(null);
    try {
      const resp = await editProjectDesign(activeProjectId, {
        instruction: text,
        floor_number: activeFloor,
        alternative_index: selectedAlternativeIndex,
      });
      if (resp.success) {
        setEditSummary(resp.summary);
        setEditInput('');
        setCanUndoDesign(resp.can_undo);
        await handleReloadProjectData();
      } else {
        setErrorMessage(resp.summary || resp.error_message || 'Edit could not be applied');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Edit request failed');
    } finally {
      setIsEditingDesign(false);
    }
  };

  const handleUndoProject = async () => {
    if (!activeProjectId || isEditingDesign) return;
    setIsEditingDesign(true);
    try {
      const resp = await undoProjectDesign(activeProjectId);
      if (resp.success) {
        setEditSummary(`Restored previous design (${resp.version_id}).`);
        setCanUndoDesign(resp.can_undo);
        await handleReloadProjectData();
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Undo failed');
    } finally {
      setIsEditingDesign(false);
    }
  };

  const handleOpenNewProject = (presetBrief?: string, presetName?: string) => {
    setInitialBrief(presetBrief);
    setInitialName(presetName);
    setCurrentView('new_project');
    setErrorMessage(null);
  };

  const handleSelectProject = (projectId: string) => {
    setActiveProjectId(projectId);
    setCurrentView('project_detail');
    setActiveTab('overview');
  };

  const handleGenerateSubmit = async (req: GenerationRequest) => {
    setIsGenerating(true);
    setErrorMessage(null);
    try {
      const resp = await generateFloorPlan(req);
      setGenerationResponse(resp);

      if (resp.status === 'waiting_for_clarification' || resp.pending_clarification) {
        // Paused workflow waiting for user response
        setActiveProjectId(resp.project_id);
        setIsGenerating(false);
        return;
      }

      if (resp.status === 'incomplete_requirements') {
        setErrorMessage(
          `Incomplete Requirements: ${resp.missing_fields?.join(', ') || 'Clarification required'}. Questions: ${resp.clarification_questions?.join(' ')}`
        );
        setIsGenerating(false);
        return;
      }

      if (!resp.is_success) {
        if (resp.status === 'failed' || (resp.error_message && resp.error_message.toLowerCase().includes('infeasible'))) {
          setErrorMessage(`Requirements are infeasible: ${resp.error_message || 'Room requirements exceed buildable plot boundaries'}`);
        } else {
          setErrorMessage(`Plan could not be validated: ${resp.error_message || `${resp.validation_summary?.total_errors || 'Hard'} building code violations found.`}`);
        }
      }

      // Navigate to project detail
      setActiveProjectId(resp.project_id);
      setCurrentView('project_detail');
      setActiveTab('overview');
    } catch (err: any) {
      console.error('Generation failed', err);
      setErrorMessage(err.message || 'Floor plan generation failed');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleClarificationSubmit = async (
    selectedOptionId?: string,
    responseText?: string,
    numericOverrides?: Record<string, number>
  ) => {
    if (!generationResponse?.project_id || !generationResponse.pending_clarification) return;
    setIsGenerating(true);
    setErrorMessage(null);
    try {
      await submitClarificationResponse(
        generationResponse.project_id,
        generationResponse.pending_clarification.request_id,
        {
          selected_option_id: selectedOptionId,
          user_response_text: responseText,
          numeric_overrides: numericOverrides,
          expected_state_version: generationResponse.pending_clarification.state_version,
        }
      );
      // Auto-resume workflow following accepted response
      const resumed = await resumeProject(generationResponse.project_id);
      setGenerationResponse(resumed);
      if (resumed.is_success) {
        const data = await getProjectData(resumed.project_id);
        setProjectData(data);
        setActiveProjectId(resumed.project_id);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to submit clarification response');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleClarificationResume = async () => {
    if (!generationResponse?.project_id) return;
    setIsGenerating(true);
    setErrorMessage(null);
    try {
      const resumed = await resumeProject(generationResponse.project_id);
      setGenerationResponse(resumed);
      if (resumed.is_success) {
        const data = await getProjectData(resumed.project_id);
        setProjectData(data);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to resume generation');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleClarificationCancel = async () => {
    if (!generationResponse?.project_id) return;
    setIsGenerating(true);
    try {
      const cancelled = await cancelProject(generationResponse.project_id);
      setGenerationResponse(cancelled);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to cancel project');
    } finally {
      setIsGenerating(false);
    }
  };

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
  const projectName = projectData?.project_metadata?.project_name || generationResponse?.project_name || activeProjectId || 'My House';

  const totalErrors = validationReport?.total_errors || (validationReport?.results?.reduce((acc, r) => acc + (r.issues?.filter((i) => i.severity === 'error').length || 0), 0) ?? 0);
  const totalWarnings = validationReport?.total_warnings || (validationReport?.results?.reduce((acc, r) => acc + (r.issues?.filter((i) => i.severity === 'warning').length || 0), 0) ?? 0);
  const isOverallValid = validationReport?.overall_valid ?? (totalErrors === 0);

  const availableFloors = activeFloorPlanSet?.floor_plans || [];
  const alternativesList = projectData?.alternatives || [];

  const validationStatus = getValidationDisplayStatus(
    validationReport,
    projectData?.refinement_result,
    projectData?.status || generationResponse?.status
  );

  return (
    <div className="app-container">
      <Header
        onNewProject={() => handleOpenNewProject()}
        onAssistant={() => {
          setCurrentView('assistant');
          setErrorMessage(null);
        }}
        onDashboard={() => setCurrentView('home')}
        onProjects={() => setCurrentView('projects')}
        onBenchmarks={() => setCurrentView('benchmarks')}
        currentView={currentView}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

      {currentView === 'project_detail' && activeProjectId && (
        <TabNav
          projectName={projectName}
          projectId={activeProjectId}
          isValid={isOverallValid}
          statusLabel={validationStatus.label}
          statusBadgeClass={validationStatus.badgeClass}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          hasTrace={projectData?.decision_trace !== undefined}
          alternativesCount={alternativesList.length || 1}
        />
      )}

      <main className={`main-content ${currentView === 'assistant' ? 'assistant-mode' : ''}`} style={currentView === 'assistant' ? { padding: 0, overflow: 'hidden' } : undefined}>
        {errorMessage && (
          <div
            style={{
              padding: '0.75rem 1.25rem',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--status-danger-bg)',
              border: '1px solid var(--status-danger-border)',
              color: '#f87171',
              fontSize: '0.875rem',
              marginBottom: currentView === 'assistant' ? 0 : '1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div>
              <strong>Alert:</strong> {errorMessage}
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '1rem' }}
            >
              ✕
            </button>
          </div>
        )}

        {/* View 0: Conversational AI Assistant (Two-Panel Studio) */}
        {currentView === 'assistant' && (
          <ConversationalStudio
            initialBrief={initialBrief}
            initialProjectName={initialName}
            isGenerating={isGenerating}
            projectData={projectData}
            generationResponse={generationResponse}
            onGenerateSubmit={handleGenerateSubmit}
            activeFloor={activeFloor}
            onSelectFloor={setActiveFloor}
            selectedAlternativeIndex={selectedAlternativeIndex}
            onSelectAlternative={setSelectedAlternativeIndex}
            selectedRoom={selectedRoom}
            onSelectRoom={setSelectedRoom}
            theme={theme}
            onViewTrace={() => {
              setCurrentView('project_detail');
              setActiveTab('explainability');
            }}
            onViewExports={() => {
              setCurrentView('project_detail');
              setActiveTab('export');
            }}
            onClarificationSubmit={handleClarificationSubmit}
            onClarificationResume={handleClarificationResume}
            onClarificationCancel={handleClarificationCancel}
            onProjectUpdated={handleReloadProjectData}
          />
        )}

        {/* View 1: Home Page (Section 3) */}
        {currentView === 'home' && (
          <HomeView
            onSelectProject={handleSelectProject}
            onNewProject={() => handleOpenNewProject()}
            onStartAssistant={() => {
              setCurrentView('assistant');
              setErrorMessage(null);
            }}
            onViewProjects={() => setCurrentView('projects')}
            onViewBenchmarks={() => setCurrentView('benchmarks')}
          />
        )}

        {/* View 2: Projects Table (Section 19) */}
        {currentView === 'projects' && (
          <ProjectsView
            onSelectProject={handleSelectProject}
            onNewProject={() => handleOpenNewProject()}
          />
        )}

        {/* View 3: Benchmarks Presets (Section 22) */}
        {currentView === 'benchmarks' && (
          <BenchmarksView
            onLoadBenchmark={(brief, name) => handleOpenNewProject(brief, name)}
            onBack={() => setCurrentView('home')}
          />
        )}

        {/* View 4: New Project 5-Step Wizard (Section 4-9) */}
        {currentView === 'new_project' && (
          <NewProjectView
            initialBrief={initialBrief}
            initialName={initialName}
            onSubmit={handleGenerateSubmit}
            isLoading={isGenerating}
            onCancel={() => setCurrentView('home')}
          />
        )}

        {/* View 5: Results Page (Section 10-18) */}
        {currentView === 'project_detail' && (
          <div style={{ width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {isLoadingProject ? (
              <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                Loading floor plan geometry and verification records...
              </div>
            ) : (
              <>
                {/* DEFAULT & PRIMARY RESULTS VIEW: FLOOR PLAN (Section 10) */}
                {(activeTab === 'overview' || activeTab === 'floorplan') && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {/* Top Switcher Bar: Alternatives & Floors (Sections 11 & 12) */}
                    <div
                      className="card"
                      style={{
                        padding: '0.65rem 1rem',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '0.75rem',
                      }}
                    >
                      {/* Left: Floor Selector (Section 12) */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>FLOOR:</span>
                        {availableFloors.length > 1 ? (
                          <div style={{ display: 'flex', gap: '0.35rem' }}>
                            {availableFloors.map((fp) => (
                              <button
                                key={fp.floor_number}
                                className={`btn ${activeFloor === fp.floor_number ? 'btn-primary' : 'btn-outline'} btn-sm`}
                                onClick={() => {
                                  setActiveFloor(fp.floor_number);
                                  setSelectedRoom(null);
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

                      {/* Right: Alternative Switcher (Section 11) */}
                      {alternativesList.length > 1 && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>ALTERNATIVE:</span>
                          <div style={{ display: 'flex', gap: '0.35rem' }}>
                            {alternativesList.map((alt) => (
                              <button
                                key={alt.index}
                                className={`btn ${selectedAlternativeIndex === alt.index ? 'btn-primary' : 'btn-outline'} btn-sm`}
                                onClick={() => {
                                  setSelectedAlternativeIndex(alt.index);
                                  setSelectedRoom(null);
                                }}
                                style={{ padding: '0.25rem 0.65rem', fontSize: '0.8rem' }}
                              >
                                Alternative {alt.index}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* NATURAL-LANGUAGE EDIT DESIGN BAR (Section 9 & 10) */}
                    <div
                      className="card"
                      style={{
                        padding: '0.75rem 1rem',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem',
                      }}
                    >
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.825rem', whiteSpace: 'nowrap' }}>
                          <span>✨ Edit Design:</span>
                        </div>
                        <input
                          type="text"
                          className="input input-sm"
                          placeholder="Type natural-language instruction (e.g. 'Make master bedroom larger', 'Change living room to L-shaped', 'Add window')..."
                          value={editInput}
                          onChange={(e) => setEditInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleEditProject();
                          }}
                          disabled={isEditingDesign}
                          style={{ flex: 1, fontSize: '0.825rem' }}
                        />
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => handleEditProject()}
                          disabled={isEditingDesign || !editInput.trim()}
                          style={{ padding: '0.35rem 0.85rem', fontSize: '0.8rem', whiteSpace: 'nowrap' }}
                        >
                          {isEditingDesign ? 'Applying...' : 'Apply Edit'}
                        </button>

                        {canUndoDesign && (
                          <button
                            className="btn btn-outline btn-sm"
                            onClick={handleUndoProject}
                            disabled={isEditingDesign}
                            title="Undo last edit and restore previous design version"
                            style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem', whiteSpace: 'nowrap', color: 'var(--color-primary)' }}
                          >
                            ↶ Undo
                          </button>
                        )}

                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => setIsVersionModalOpen(!isVersionModalOpen)}
                          title="View design version history"
                          style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem', whiteSpace: 'nowrap' }}
                        >
                          📜 Versions
                        </button>
                      </div>

                      {/* Suggestions */}
                      {!isEditingDesign && !editSummary && (
                        <div style={{ display: 'flex', gap: '0.35rem', overflowX: 'auto', paddingBottom: '0.1rem', scrollbarWidth: 'none' }}>
                          <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)', alignSelf: 'center', marginRight: '0.2rem' }}>Suggestions:</span>
                          {[
                            'Make the master bedroom larger',
                            'Change the living room to an L-shaped design',
                            'Add a window to the master bedroom',
                            'Move the entrance to the east side',
                            'Increase kitchen area to 15 square meters',
                            'Improve circulation flow',
                          ].map((s, idx) => (
                            <button
                              key={idx}
                              className="btn btn-outline btn-xs"
                              onClick={() => handleEditProject(s)}
                              style={{ fontSize: '0.725rem', padding: '0.15rem 0.45rem', whiteSpace: 'nowrap', borderRadius: 'var(--radius-full)' }}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      )}

                      {/* Editing Progress */}
                      {isEditingDesign && (
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
                          <span>Executing Design Editing Agent: analyzing modification, drafting CAD geometry, verifying building codes...</span>
                        </div>
                      )}

                      {/* Change Summary Banner */}
                      {editSummary && !isEditingDesign && (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '0.45rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.8rem',
                            backgroundColor: 'var(--status-success-bg)',
                            color: 'var(--status-success)',
                            border: '1px solid var(--status-success-border)',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span>✓</span>
                            <span>{editSummary}</span>
                          </div>
                          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                            {canUndoDesign && (
                              <button
                                className="btn btn-xs"
                                onClick={handleUndoProject}
                                style={{ fontSize: '0.725rem', padding: '0.1rem 0.45rem' }}
                              >
                                Undo
                              </button>
                            )}
                            <button
                              onClick={() => setEditSummary(null)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: '0.9rem' }}
                            >
                              ×
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Dominant Element: Floor Plan Canvas (Section 10 & 13) */}
                    <div style={{ minHeight: '620px', width: '100%', position: 'relative' }}>
                      {/* Version History Modal Popup */}
                      {isVersionModalOpen && (
                        <div
                          style={{
                            position: 'absolute',
                            right: '1rem',
                            top: '1rem',
                            width: '360px',
                            maxWidth: '92%',
                            maxHeight: '80%',
                            zIndex: 40,
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
                              onClick={() => setIsVersionModalOpen(false)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.1rem', color: 'var(--text-muted)' }}
                            >
                              ×
                            </button>
                          </div>
                          <div style={{ padding: '0.75rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                            {versionHistory.map((ver, idx) => (
                              <div
                                key={ver.version_id}
                                style={{
                                  padding: '0.6rem',
                                  borderRadius: 'var(--radius-sm)',
                                  border: idx === versionHistory.length - 1 ? '1px solid var(--color-primary)' : '1px solid var(--border-color)',
                                  backgroundColor: idx === versionHistory.length - 1 ? 'var(--bg-surface)' : 'transparent',
                                  fontSize: '0.8rem',
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                                  <span style={{ fontWeight: 700, color: idx === versionHistory.length - 1 ? 'var(--color-primary)' : 'inherit' }}>
                                    {ver.version_id.toUpperCase()} {idx === versionHistory.length - 1 ? '(Active)' : ''}
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
                      <FloorPlanCanvas
                        floorPlan={activeFloorPlan}
                        plotBoundary={activeFloorPlanSet?.plot_boundary || []}
                        buildableBoundary={activeFloorPlanSet?.buildable_boundary || []}
                        selectedRoom={selectedRoom}
                        onSelectRoom={setSelectedRoom}
                        projectId={activeProjectId || ''}
                        alternativeIndex={selectedAlternativeIndex}
                        theme={theme}
                        orientation={projectData?.requirements?.orientation || 'north'}
                      />
                    </div>

                    {/* Bottom Split Panels: Room Information & Validation (Section 10) */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', alignItems: 'start' }}>
                      {/* Left: Room Information (Section 14) */}
                      {selectedRoom ? (
                        <RoomInspector
                          room={selectedRoom}
                          geometry={activeFloorPlan?.geometry || null}
                          validationResult={activeFloorPlan?.validation}
                          onClose={() => setSelectedRoom(null)}
                          onViewTrace={() => setActiveTab('explainability')}
                        />
                      ) : (
                        <div className="card" style={{ padding: '1.25rem', height: '100%', minHeight: '140px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.4rem 0' }}>Room Information</h3>
                          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', margin: 0 }}>
                            Click a room on the floor plan to inspect its details.
                          </p>
                        </div>
                      )}

                      {/* Right: Validation Summary (Section 10 & 15) */}
                      <div className="card" style={{ padding: '1.25rem', height: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
                          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Validation Summary</h3>
                          <span style={{ fontWeight: 700, fontSize: '0.825rem', letterSpacing: '0.03em', color: validationStatus.type === 'valid' || validationStatus.type === 'refined' ? 'var(--status-success)' : '#f87171' }}>
                            {validationStatus.label}
                          </span>
                        </div>

                        <div style={{ display: 'flex', gap: '1.25rem', fontSize: '0.825rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                          <span><strong style={{ color: totalErrors > 0 ? '#f87171' : 'inherit' }}>{totalErrors}</strong> hard errors</span>
                          <span><strong style={{ color: totalWarnings > 0 ? '#fbbf24' : 'inherit' }}>{totalWarnings}</strong> warnings/advisories</span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', fontSize: '0.825rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span style={{ color: 'var(--status-success)' }}>✓</span>
                            <span>Boundary</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span style={{ color: 'var(--status-success)' }}>✓</span>
                            <span>Dimensions</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span style={{ color: 'var(--status-success)' }}>✓</span>
                            <span>Adjacency</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span style={{ color: 'var(--status-success)' }}>✓</span>
                            <span>Connectivity</span>
                          </div>
                        </div>

                        <button
                          className="btn btn-outline btn-sm"
                          style={{ marginTop: '0.85rem', fontSize: '0.775rem', width: '100%' }}
                          onClick={() => setActiveTab('validation')}
                        >
                          View Full Validation Report →
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Sub-Tabs for Detailed Inspection */}
                {activeTab === 'validation' && (
                  <ValidationView validationReport={validationReport} />
                )}

                {activeTab === 'alternatives' && (
                  <AlternativesView
                    alternatives={alternativesList}
                    projectId={activeProjectId || ''}
                    selectedAlternativeIndex={selectedAlternativeIndex}
                    onSelectAlternative={setSelectedAlternativeIndex}
                    onViewFloorPlan={() => setActiveTab('overview')}
                  />
                )}

                {activeTab === 'explainability' && (
                  <ExplainabilityView
                    decisionTrace={projectData?.decision_trace}
                    floorPlanSet={activeFloorPlanSet}
                  />
                )}

                {activeTab === 'refinement' && (
                  <RefinementView refinementResult={projectData?.refinement_result} />
                )}

                {activeTab === 'export' && (
                  <ExportView
                    projectId={activeProjectId || ''}
                    floorPlanSet={activeFloorPlanSet}
                  />
                )}

                {activeTab === 'plot' && projectData && (
                  <PlotView
                    projectData={projectData}
                    onAdjustPlot={() => {
                      handleOpenNewProject(
                        projectData.requirements?.raw_input,
                        `${projectData.project_metadata?.project_name || 'Project'} (Revised Plot)`
                      );
                    }}
                  />
                )}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
