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

import { getProjectData, generateFloorPlan } from './api/projects';
import type {
  ProjectData,
  GenerationRequest,
  GenerationResponse,
  GeoRoom,
  FloorPlan,
  FloorPlanSet,
} from './api/types';

import './styles/index.css';
import './styles/components.css';

export function App() {
  const [currentView, setCurrentView] = useState<'home' | 'projects' | 'benchmarks' | 'new_project' | 'project_detail'>('home');
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview');

  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [projectData, setProjectData] = useState<ProjectData | null>(null);
  const [generationResponse, setGenerationResponse] = useState<GenerationResponse | null>(null);

  const [activeFloor, setActiveFloor] = useState<number>(1);
  const [selectedAlternativeIndex, setSelectedAlternativeIndex] = useState<number>(1);
  const [selectedRoom, setSelectedRoom] = useState<GeoRoom | null>(null);

  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isLoadingProject, setIsLoadingProject] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

      if (resp.status === 'incomplete_requirements') {
        setErrorMessage(
          `Incomplete Requirements: ${resp.missing_fields?.join(', ') || 'Clarification required'}. Questions: ${resp.clarification_questions?.join(' ')}`
        );
        setIsGenerating(false);
        return;
      }

      if (!resp.is_success && resp.error_message) {
        setErrorMessage(`Generation stopped: ${resp.error_message}`);
        setIsGenerating(false);
        return;
      }

      // Success -> navigate to project detail
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

  return (
    <div className="app-container">
      <Header
        onNewProject={() => handleOpenNewProject()}
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
          activeTab={activeTab}
          onTabChange={setActiveTab}
          hasTrace={projectData?.decision_trace !== undefined}
          alternativesCount={alternativesList.length || 1}
        />
      )}

      <main className="main-content">
        {errorMessage && (
          <div
            style={{
              padding: '0.75rem 1.25rem',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--status-danger-bg)',
              border: '1px solid var(--status-danger-border)',
              color: '#f87171',
              fontSize: '0.875rem',
              marginBottom: '1rem',
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

        {/* View 1: Home Page (Section 3) */}
        {currentView === 'home' && (
          <HomeView
            onSelectProject={handleSelectProject}
            onNewProject={() => handleOpenNewProject()}
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

                    {/* Dominant Element: Floor Plan Canvas (Section 10 & 13) */}
                    <div style={{ minHeight: '620px', width: '100%' }}>
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
                          <span style={{ fontWeight: 700, fontSize: '0.875rem', letterSpacing: '0.04em', color: totalErrors === 0 ? 'var(--status-success)' : '#f87171' }}>
                            {totalErrors === 0 ? 'VALID' : 'INVALID'}
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
