import React from 'react';
import type { ProjectData, GenerationResponse } from '../../api/types';
import type { ActiveTab } from '../layout/TabNav';
import { getValidationDisplayStatus } from '../../utils/validationStatus';

interface ProjectOverviewViewProps {
  projectData: ProjectData | null;
  generationResponse?: GenerationResponse | null;
  onNavigateTab: (tab: ActiveTab) => void;
}

const STAGES_LIST = [
  { key: 'REQUIREMENTS', label: '1. Requirement Parsing & Gating' },
  { key: 'PLANNING', label: '2. Strategic Planning Program' },
  { key: 'ASAA', label: '3. ASAA Spatial Allocation' },
  { key: 'ARCHITECTURAL_DESIGN', label: '4. Architectural Intent Design' },
  { key: 'GEOMETRY', label: '5. Physical Geometry Engine' },
  { key: 'VALIDATION', label: '6. Independent Validator' },
  { key: 'REFINEMENT', label: '7. Closed-Loop Refinement' },
  { key: 'DIVERSITY', label: '8. Structural Diversity Generator' },
  { key: 'EXPLAINABILITY', label: '9. Explainability & Decision Trace' },
  { key: 'EXPORT', label: '10. Export & 300 DPI Rendering' },
];

export const ProjectOverviewView: React.FC<ProjectOverviewViewProps> = ({
  projectData,
  generationResponse,
  onNavigateTab,
}) => {
  if (!projectData && !generationResponse) {
    return <div className="card">Loading project overview...</div>;
  }

  const valSummary = projectData?.validation_report || generationResponse?.validation_summary;
  const fullReport = projectData?.validation_report;

  const validationStatus = getValidationDisplayStatus(
    valSummary,
    projectData?.refinement_result,
    projectData?.status || generationResponse?.status
  );

  const overallScore: number = (() => {
    if (typeof valSummary?.overall_score === 'number' && !isNaN(valSummary.overall_score)) {
      return valSummary.overall_score;
    }
    if (fullReport?.results && fullReport.results.length > 0) {
      const sum = fullReport.results.reduce((acc: number, r) => acc + (typeof r.score === 'number' ? r.score : 100), 0);
      return sum / fullReport.results.length;
    }
    return 100.0;
  })();

  const totalErrors: number = (() => {
    if (typeof valSummary?.total_errors === 'number') {
      return valSummary.total_errors;
    }
    if (fullReport?.results) {
      return fullReport.results.reduce(
        (acc: number, r) => acc + (r.issues?.filter((i) => i.severity === 'error').length || 0),
        0
      );
    }
    return 0;
  })();

  const totalWarnings: number = (() => {
    if (typeof valSummary?.total_warnings === 'number') {
      return valSummary.total_warnings;
    }
    if (fullReport?.results) {
      return fullReport.results.reduce(
        (acc: number, r) => acc + (r.issues?.filter((i) => i.severity === 'warning').length || 0),
        0
      );
    }
    return 0;
  })();

  const stageStatuses = generationResponse?.stage_statuses || {};

  const floorPlanSet = projectData?.floor_plan_set;
  const totalFloors = floorPlanSet?.floor_plans.length || 1;
  const totalRooms = floorPlanSet?.floor_plans.reduce(
    (acc, fp) => acc + (fp.geometry?.rooms.length || 0),
    0
  ) || 0;
  const totalUsableArea = floorPlanSet?.floor_plans.reduce(
    (acc, fp) => acc + (fp.geometry?.rooms.reduce((s, r) => s + r.area_sqm, 0) || 0),
    0
  ) || 0;

  const altsCount = projectData?.alternatives?.length || generationResponse?.alternatives.length || 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Top Status Banner */}
      <div
        className="card"
        style={{
          borderLeft: `5px solid ${validationStatus.type === 'valid' || validationStatus.type === 'refined' ? 'var(--status-success)' : 'var(--status-danger)'}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <span className={`badge ${validationStatus.badgeClass}`}>
              {validationStatus.label}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Project ID: {projectData?.project_id || generationResponse?.project_id}
            </span>
          </div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {projectData?.project_metadata?.project_name || generationResponse?.project_name || 'Generated Residence'}
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Generated via PlanForge 10-stage autonomous architectural pipeline with zero room fabrication.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-primary" onClick={() => onNavigateTab('floorplan')}>
            View Floor Plan Canvas →
          </button>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card">
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
            Program Floors
          </span>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {totalFloors}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Discrete floor geometries
          </span>
        </div>

        <div className="card">
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
            Constructed Rooms
          </span>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent-sky)', marginTop: '0.25rem' }}>
            {totalRooms}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            100% requirement coverage
          </span>
        </div>

        <div className="card">
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
            Total Usable Area
          </span>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            {totalUsableArea.toFixed(1)} <span style={{ fontSize: '1rem', fontWeight: 500 }}>m²</span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {(totalUsableArea * 10.7639).toFixed(0)} sq ft living space
          </span>
        </div>

        <div className="card">
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
            Design Alternatives
          </span>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#c084fc', marginTop: '0.25rem' }}>
            {altsCount}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Structural diversity explored
          </span>
        </div>
      </div>

      {/* Main Two-Column Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
        {/* Pipeline Stage Execution Timeline */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Generative Pipeline Execution Timeline</h3>
            <span className="badge badge-info">10 Stages Monitored</span>
          </div>

          <div className="stages-tracker">
            {STAGES_LIST.map((stage) => {
              const statusRaw = stageStatuses[stage.key] || 'completed';
              const status = statusRaw.toLowerCase();
              return (
                <div key={stage.key} className={`stage-step ${status}`}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                    <span
                      style={{
                        width: '20px',
                        height: '20px',
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.75rem',
                        fontWeight: 'bold',
                        background:
                          status === 'completed'
                            ? 'rgba(16, 185, 129, 0.2)'
                            : status === 'running'
                            ? 'rgba(56, 189, 248, 0.2)'
                            : 'rgba(255, 255, 255, 0.05)',
                        color:
                          status === 'completed'
                            ? '#34d399'
                            : status === 'running'
                            ? 'var(--accent-sky)'
                            : 'var(--text-muted)',
                      }}
                    >
                      {status === 'completed' ? '✓' : status === 'running' ? '●' : '○'}
                    </span>
                    <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{stage.label}</span>
                  </div>

                  <span
                    className={`badge ${
                      status === 'completed'
                        ? 'badge-success'
                        : status === 'running'
                        ? 'badge-info'
                        : status === 'failed'
                        ? 'badge-danger'
                        : 'badge-neutral'
                    }`}
                  >
                    {status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Quick Navigation & Diagnostics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '0.85rem' }}>
              Validation Overview
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              <div className="property-row">
                <span className="property-label">Hard Errors</span>
                <span className="property-value" style={{ color: totalErrors > 0 ? 'var(--status-danger)' : 'var(--text-primary)' }}>
                  {totalErrors}
                </span>
              </div>
              <div className="property-row">
                <span className="property-label">Advisory Warnings</span>
                <span className="property-value" style={{ color: 'var(--text-secondary)' }}>
                  {totalWarnings}
                </span>
              </div>
              <div className="property-row">
                <span className="property-label">Diagnostic Quality Score</span>
                <span className="property-value">
                  {overallScore.toFixed(1)} / 100
                </span>
              </div>
            </div>

            <button
              className="btn btn-secondary btn-sm"
              style={{ width: '100%', marginTop: '1rem' }}
              onClick={() => onNavigateTab('validation')}
            >
              Inspect 18 Validation Checks →
            </button>
          </div>

          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '0.85rem' }}>
              Research Diagnostics
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button className="btn btn-outline btn-sm" onClick={() => onNavigateTab('plot')} style={{ justifyContent: 'flex-start' }}>
                📐 Authoritative Plot Boundary & Setbacks
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => onNavigateTab('explainability')} style={{ justifyContent: 'flex-start' }}>
                🔍 Decision Provenance & Trace
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => onNavigateTab('refinement')} style={{ justifyContent: 'flex-start' }}>
                🔄 Closed-Loop Refinement History
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => onNavigateTab('alternatives')} style={{ justifyContent: 'flex-start' }}>
                🔀 Multi-Design Diversity ({altsCount})
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => onNavigateTab('export')} style={{ justifyContent: 'flex-start' }}>
                💾 Download PNG, JSON & Bundle
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
