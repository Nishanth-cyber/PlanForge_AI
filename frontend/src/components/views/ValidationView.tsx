import React, { useState } from 'react';
import type { ValidationReport } from '../../api/types';

interface ValidationViewProps {
  validationReport?: ValidationReport | null;
}

const CHECK_CATEGORIES = [
  { id: 'boundary', name: 'Boundary Containment' },
  { id: 'dimension', name: 'Room Dimensions & Area' },
  { id: 'adjacency', name: 'Required Adjacency' },
  { id: 'separation', name: 'Acoustic Separation' },
  { id: 'attached', name: 'Attached Relationships' },
  { id: 'connectivity', name: 'Graph Connectivity' },
  { id: 'door', name: 'Door Placement & Swing' },
  { id: 'window', name: 'Window Exterior Placement' },
  { id: 'staircase', name: 'Staircase Alignment' },
  { id: 'overlap', name: 'Room Non-Overlap' },
];

export const ValidationView: React.FC<ValidationViewProps> = ({ validationReport }) => {
  const [filterSeverity, setFilterSeverity] = useState<'all' | 'error' | 'warning'>('all');

  if (!validationReport) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '2rem' }}>
        <p style={{ color: 'var(--text-secondary)' }}>Validation report is not available for this project.</p>
      </div>
    );
  }

  const allIssues = validationReport.results.flatMap((r) => r.issues || []);
  const filteredIssues = allIssues.filter((i) => {
    if (filterSeverity === 'all') return true;
    return i.severity === filterSeverity;
  });

  const totalErrors: number = (() => {
    if (typeof validationReport.total_errors === 'number') return validationReport.total_errors;
    if (validationReport.results) {
      return validationReport.results.reduce(
        (acc, r) => acc + (r.issues?.filter((i) => i.severity === 'error').length || 0),
        0
      );
    }
    return 0;
  })();

  const totalWarnings: number = (() => {
    if (typeof validationReport.total_warnings === 'number') return validationReport.total_warnings;
    if (validationReport.results) {
      return validationReport.results.reduce(
        (acc, r) => acc + (r.issues?.filter((i) => i.severity === 'warning').length || 0),
        0
      );
    }
    return 0;
  })();

  const overallValid: boolean = (() => {
    if (typeof validationReport.overall_valid === 'boolean') return validationReport.overall_valid;
    if (validationReport.results && validationReport.results.length > 0) {
      return validationReport.results.every((r) => r.is_valid);
    }
    return true;
  })();

  return (
    <div style={{ width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Summary Banner (Section 15) */}
      <div
        className="card"
        style={{
          padding: '1.25rem 1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>Validation</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginTop: '0.35rem' }}>
            <span style={{ fontWeight: 700, fontSize: '0.95rem', letterSpacing: '0.04em', color: overallValid ? 'var(--status-success)' : '#f87171' }}>
              {overallValid ? 'VALID' : 'INVALID'}
            </span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              ({overallValid ? 'All mandatory architectural constraints satisfied' : 'Mandatory constraint violations exist'})
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.875rem' }}>
          <div>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Hard Errors</span>
            <strong style={{ fontSize: '1.1rem', color: totalErrors > 0 ? '#f87171' : 'inherit' }}>
              {totalErrors}
            </strong>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Warnings/Advisories</span>
            <strong style={{ fontSize: '1.1rem', color: totalWarnings > 0 ? '#fbbf24' : 'inherit' }}>
              {totalWarnings}
            </strong>
          </div>
        </div>
      </div>

      {/* Checklist of Verification Categories (Section 15) */}
      <div className="card" style={{ padding: '1.25rem 1.5rem' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.85rem 0' }}>Rule Checklist</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          {CHECK_CATEGORIES.map((cat) => {
            const hasCatError = allIssues.some((i) => i.category === cat.id && i.severity === 'error');
            const hasCatWarn = allIssues.some((i) => i.category === cat.id && i.severity === 'warning');

            const statusSymbol = hasCatError ? (
              <span style={{ color: '#f87171', fontWeight: 600 }}>✗ Failed</span>
            ) : hasCatWarn ? (
              <span style={{ color: '#fbbf24', fontWeight: 500 }}>⚠ Advisory</span>
            ) : (
              <span style={{ color: 'var(--status-success)', fontWeight: 600 }}>✓</span>
            );

            return (
              <div
                key={cat.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '0.45rem 0',
                  borderBottom: '1px solid var(--border-subtle)',
                  fontSize: '0.875rem',
                }}
              >
                <span style={{ color: 'var(--text-primary)' }}>{cat.name}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>{statusSymbol}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Issues Table (Only if issues exist) */}
      {allIssues.length > 0 && (
        <div className="card" style={{ padding: '1.25rem 1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Reported Issues</h3>
            <div style={{ display: 'flex', gap: '0.35rem' }}>
              <button
                className={`btn ${filterSeverity === 'all' ? 'btn-secondary' : 'btn-outline'} btn-sm`}
                style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem' }}
                onClick={() => setFilterSeverity('all')}
              >
                All ({allIssues.length})
              </button>
              <button
                className={`btn ${filterSeverity === 'error' ? 'btn-secondary' : 'btn-outline'} btn-sm`}
                style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem' }}
                onClick={() => setFilterSeverity('error')}
              >
                Errors ({totalErrors})
              </button>
              <button
                className={`btn ${filterSeverity === 'warning' ? 'btn-secondary' : 'btn-outline'} btn-sm`}
                style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem' }}
                onClick={() => setFilterSeverity('warning')}
              >
                Warnings ({totalWarnings})
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {filteredIssues.map((issue, idx) => (
              <div
                key={issue.id || idx}
                style={{
                  padding: '0.65rem 0.85rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-default)',
                  background: 'var(--bg-secondary)',
                  fontSize: '0.85rem',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.65rem',
                }}
              >
                <span
                  className={`badge ${issue.severity === 'error' ? 'badge-danger' : 'badge-warning'}`}
                  style={{ fontSize: '0.7rem', textTransform: 'uppercase' }}
                >
                  {issue.severity}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{issue.rule_name || issue.category}</div>
                  <div style={{ color: 'var(--text-secondary)', marginTop: '0.15rem' }}>{issue.description}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
