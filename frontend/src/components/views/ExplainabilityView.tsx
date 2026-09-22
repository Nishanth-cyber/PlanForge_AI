import React, { useState } from 'react';
import type { DecisionTrace, FloorPlanSet } from '../../api/types';

interface ExplainabilityViewProps {
  decisionTrace?: DecisionTrace | null;
  floorPlanSet?: FloorPlanSet | null;
}

const STAGE_LABELS: Record<string, string> = {
  requirement: 'Requirement',
  planning: 'Planning',
  asaa_allocation: 'ASAA Allocation',
  architectural_design: 'Architectural Design',
  geometry: 'Geometry',
  validation: 'Validation',
  refinement: 'Refinement',
  diversity: 'Diversity',
  final_selection: 'Final Selection',
};

function formatStageName(stage: string): string {
  const norm = stage.toLowerCase().trim();
  return STAGE_LABELS[norm] || norm.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export const ExplainabilityView: React.FC<ExplainabilityViewProps> = ({
  decisionTrace,
  floorPlanSet,
}) => {
  const [selectedStage, setSelectedStage] = useState<string>('all');
  const [selectedRoomId, setSelectedRoomId] = useState<string>('');

  if (!decisionTrace) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <p style={{ color: 'var(--text-secondary)' }}>
          Decision trace is not recorded or currently unavailable for this project run.
        </p>
      </div>
    );
  }

  const stages = decisionTrace.stages || [];
  const entityChains = decisionTrace.entity_chains || {};

  // Rooms list from active floor plans for room traceability
  const allRooms = floorPlanSet?.floor_plans.flatMap((fp) => fp.geometry?.rooms || []) || [];

  // Active room chain
  const activeChain = selectedRoomId ? entityChains[selectedRoomId] : null;

  // Filtered stage events
  const displayStages = selectedStage === 'all' ? stages : stages.filter((s) => s.stage_name === selectedStage);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Intro Card */}
      <div className="card">
        <h2 className="card-title">Explainability & Decision Trace System</h2>
        <p className="card-subtitle">
          Phase 10 provenance tracking capturing structured architectural decisions, evidence, and entity lifecycle
          lineage across all generative pipeline stages. Strictly zero synthetic chain-of-thought or model scratchpad leakage.
        </p>
      </div>

      {/* Room Lifecycle Traceability Explorer */}
      <div className="card" style={{ border: '1px solid var(--accent-sky)' }}>
        <div className="card-header">
          <div>
            <h3 className="card-title" style={{ color: 'var(--accent-sky)' }}>
              🔗 Room Entity Lifecycle Traceability
            </h3>
            <p className="card-subtitle">
              See how each room moves from the user requirement through planning, allocation, architectural design, geometry, and validation.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label className="form-label" style={{ marginBottom: 0 }}>Select Room:</label>
            <select
              className="form-select"
              value={selectedRoomId}
              onChange={(e) => setSelectedRoomId(e.target.value)}
              style={{ width: 'auto', minWidth: '200px' }}
            >
              <option value="">— Choose a Room —</option>
              {allRooms.map((r) => (
                <option key={r.id} value={r.id}>
                  Floor {r.floor_number}: {r.room_type.replace(/_/g, ' ')} ({r.area_sqm.toFixed(1)} m²)
                </option>
              ))}
            </select>
          </div>
        </div>

        {selectedRoomId ? (
          activeChain && activeChain.events.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                <span className="badge badge-info">Entity ID: {selectedRoomId}</span>
                <span className="badge badge-neutral">Events in Chain: {activeChain.events.length}</span>
              </div>

              {/* Chain Steps Timeline */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
                {activeChain.events.map((ev, i) => (
                  <div
                    key={ev.event_id || i}
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      padding: '0.85rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.4rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                        {formatStageName(ev.stage)}
                      </span>
                      <span style={{ fontSize: '0.675rem', color: 'var(--text-muted)' }}>
                        {ev.source}
                      </span>
                    </div>

                    <strong style={{ fontSize: '0.85rem', color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                      {ev.event_type.replace(/_/g, ' ')}
                    </strong>

                    <p style={{ fontSize: '0.775rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      {ev.reason || 'Rationale not provided'}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ padding: '1.25rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', textAlign: 'center', color: 'var(--text-muted)' }}>
              No discrete event chain recorded specifically for ID <code>{selectedRoomId}</code>. Inspect global stage timeline below.
            </div>
          )
        ) : (
          <div style={{ padding: '1.5rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Select a room to view its lifecycle trace.
          </div>
        )}
      </div>

      {/* Global Pipeline Stage Trace Timeline */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Stage Decision Logs</h3>
            <p className="card-subtitle">Structured records showing the decisions and evidence produced at each stage.</p>
          </div>

          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            <button
              className={`btn btn-sm ${selectedStage === 'all' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setSelectedStage('all')}
            >
              All Stages
            </button>
            {stages.map((st) => (
              <button
                key={st.stage_name}
                className={`btn btn-sm ${selectedStage === st.stage_name ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setSelectedStage(st.stage_name)}
              >
                {formatStageName(st.stage_name)}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {displayStages.map((stage) => (
            <div
              key={stage.stage_name}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                padding: '1.25rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--accent-sky)' }}>
                  {formatStageName(stage.stage_name)} Stage
                </h4>
                <span className="badge badge-neutral">{stage.events.length} Decision Events</span>
              </div>

              {stage.summary && (
                <p style={{ fontSize: '0.825rem', color: 'var(--text-secondary)', marginBottom: '1rem', fontStyle: 'italic' }}>
                  {stage.summary}
                </p>
              )}

              {stage.events.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.85rem', margin: '0.5rem 0' }}>
                  No events recorded.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                  {stage.events.map((ev, i) => (
                    <div
                      key={ev.event_id || i}
                      style={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '0.75rem 1rem',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.35rem',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span className="badge badge-info" style={{ fontSize: '0.675rem', textTransform: 'capitalize' }}>
                            {ev.event_type.replace(/_/g, ' ')}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            Source: <strong>{ev.source}</strong>
                          </span>
                        </div>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          {ev.timestamp ? ev.timestamp.substring(11, 19) : ''}
                        </span>
                      </div>

                      <p style={{ fontSize: '0.825rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                        {ev.reason || 'Rationale not provided'}
                      </p>

                      {ev.evidence && Object.keys(ev.evidence).length > 0 && (
                        <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          Evidence: {JSON.stringify(ev.evidence)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
