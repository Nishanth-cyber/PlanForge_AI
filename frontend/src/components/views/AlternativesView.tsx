import React from 'react';
import type { DesignAlternative, FloorPlanSet } from '../../api/types';
import { getExportFileUrl } from '../../api/client';

interface AlternativesViewProps {
  alternatives: DesignAlternative[];
  projectId: string;
  selectedAlternativeIndex: number;
  onSelectAlternative: (index: number) => void;
  onViewFloorPlan: (index: number) => void;
}

export const AlternativesView: React.FC<AlternativesViewProps> = ({
  alternatives = [],
  projectId,
  selectedAlternativeIndex,
  onSelectAlternative,
  onViewFloorPlan,
}) => {
  if (alternatives.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <p style={{ color: 'var(--text-secondary)' }}>
          Single alternative generated for this project. To explore architectural diversity, specify 2 to 4 alternatives during project generation.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Header Summary */}
      <div className="card">
        <h2 className="card-title">Architectural Alternatives & Diversity Exploration</h2>
        <p className="card-subtitle">
          Neutrally presented candidate designs generated using distinct architectural zoning strategies
          without subjective ranking or artificial winner selection.
        </p>
      </div>

      {/* Alternative Cards Grid */}
      <div className="grid grid-cols-3 gap-4">
        {alternatives.map((alt) => {
          const isSelected = selectedAlternativeIndex === alt.index;
          const fpSet: FloorPlanSet | undefined = alt.floor_plan_set;
          const totalRooms = fpSet?.floor_plans.reduce(
            (s, fp) => s + (fp.geometry?.rooms.length || 0),
            0
          ) || 0;
          const totalFloors = fpSet?.floor_plans.length || 1;
          const valRep = alt.validation_report;
          const isValid = alt.is_valid;
          const previewPng = getExportFileUrl(projectId, `alternatives/alternative_${alt.index}/floor_1.png`);

          return (
            <div
              key={alt.alternative_id || alt.index}
              className="card"
              style={{
                borderColor: isSelected ? 'var(--accent-sky)' : undefined,
                boxShadow: isSelected ? 'var(--shadow-glow)' : undefined,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {/* Preview Drawing Thumbnail */}
              <div
                style={{
                  height: '160px',
                  background: '#090d16',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: '1rem',
                  overflow: 'hidden',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <img
                  src={previewPng}
                  alt={`Alternative ${alt.index} preview`}
                  style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.4rem' }}>
                <div>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Alternative {alt.index}
                  </h3>
                  <span style={{ fontSize: '0.775rem', color: 'var(--accent-sky)', textTransform: 'capitalize' }}>
                    {alt.strategy.replace(/_/g, ' ')} Strategy
                  </span>
                </div>
                <span className={`badge ${isValid ? 'badge-success' : 'badge-danger'}`}>
                  {isValid ? 'Valid Design' : 'Issues Found'}
                </span>
              </div>

              <div style={{ display: 'flex', gap: '1rem', fontSize: '0.825rem', margin: '0.75rem 0' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>Rooms</span>
                  <strong>{totalRooms}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>Floors</span>
                  <strong>{totalFloors}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>Errors / Warnings</span>
                  <span style={{ color: (valRep?.total_errors || 0) > 0 ? '#f87171' : '#34d399' }}>
                    {valRep?.total_errors || 0} err / {valRep?.total_warnings || 0} warn
                  </span>
                </div>
              </div>

              {alt.characteristics && alt.characteristics.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginBottom: '1.25rem' }}>
                  {alt.characteristics.map((char, i) => (
                    <span key={i} className="badge badge-neutral" style={{ fontSize: '0.675rem' }}>
                      {char}
                    </span>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto' }}>
                <button
                  className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: 1 }}
                  onClick={() => {
                    onSelectAlternative(alt.index);
                    onViewFloorPlan(alt.index);
                  }}
                >
                  {isSelected ? 'Active on Canvas' : 'Load into Viewer →'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Factual Comparison Matrix Table */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: '1rem' }}>
          Structural Diversity Comparison Matrix
        </h3>
        <p className="card-subtitle" style={{ marginBottom: '1.25rem' }}>
          Objective comparison of topological zoning, room arrangement, circulation type, and validation outcomes.
        </p>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Design Alternative</th>
                <th>Architectural Strategy</th>
                <th>Circulation Organization</th>
                <th>Constructed Rooms</th>
                <th>Validity Status</th>
                <th>Hard Errors</th>
                <th>Advisory Warnings</th>
                <th>Pairwise Distance</th>
              </tr>
            </thead>
            <tbody>
              {alternatives.map((alt) => {
                const fpSet = alt.floor_plan_set;
                const rCount = fpSet?.floor_plans.reduce((s, fp) => s + (fp.geometry?.rooms.length || 0), 0) || 0;
                const sig = alt.design_signature;
                const valRep = alt.validation_report;
                const meanDist = alt.diversity_scores
                  ? Object.values(alt.diversity_scores).reduce((a, b) => a + b, 0) /
                    Math.max(1, Object.keys(alt.diversity_scores).length)
                  : 0.0;

                return (
                  <tr key={alt.alternative_id || alt.index}>
                    <td style={{ fontWeight: 600 }}>Alternative {alt.index}</td>
                    <td style={{ textTransform: 'capitalize' }}>{alt.strategy.replace(/_/g, ' ')}</td>
                    <td style={{ textTransform: 'capitalize' }}>{sig?.circulation_type || 'Direct Social Flow'}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{rCount}</td>
                    <td>
                      <span className={`badge ${alt.is_valid ? 'badge-success' : 'badge-danger'}`}>
                        {alt.is_valid ? 'Certified Valid' : 'Invalid'}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', color: (valRep?.total_errors || 0) > 0 ? '#f87171' : '#34d399' }}>
                      {valRep?.total_errors || 0}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', color: '#fbbf24' }}>
                      {valRep?.total_warnings || 0}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>
                      {meanDist > 0 ? meanDist.toFixed(3) : 'Baseline'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
