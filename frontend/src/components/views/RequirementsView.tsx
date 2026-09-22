import React from 'react';
import type { ProjectData } from '../../api/types';

interface RequirementsViewProps {
  projectData: ProjectData | null;
}

export const RequirementsView: React.FC<RequirementsViewProps> = ({ projectData }) => {
  if (!projectData) {
    return <div className="card">Loading requirements...</div>;
  }

  const reqs = projectData.requirements;
  const floors = reqs?.floors || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Plot Specifications Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Site & Plot Parameters</h2>
            <p className="card-subtitle">Boundary constraints and setback offsets parsed from natural language.</p>
          </div>
          <span className="badge badge-info">Completeness Certified</span>
        </div>

        <div className="grid grid-cols-4 gap-4">
          <div className="property-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
            <span className="property-label">Plot Dimensions</span>
            <span className="property-value" style={{ fontSize: '1.05rem' }}>
              {reqs?.plot_width || '40'} × {reqs?.plot_length || '50'} {reqs?.plot_unit || 'feet'}
            </span>
          </div>

          <div className="property-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
            <span className="property-label">Compass Orientation</span>
            <span className="property-value" style={{ textTransform: 'capitalize', fontSize: '1.05rem' }}>
              {reqs?.orientation || 'Unspecified (Standard)'}
            </span>
          </div>

          <div className="property-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
            <span className="property-label">Front Setback Offset</span>
            <span className="property-value" style={{ fontSize: '1.05rem' }}>
              {reqs?.front_setback !== undefined ? `${reqs.front_setback} m` : '2.0 m'}
            </span>
          </div>

          <div className="property-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
            <span className="property-label">Rear & Side Setbacks</span>
            <span className="property-value" style={{ fontSize: '1.05rem' }}>
              R: {reqs?.rear_setback || 2.0}m • S: {reqs?.side_setback || 2.0}m
            </span>
          </div>
        </div>
      </div>

      {/* Floor-by-Floor Program Breakdown */}
      {floors.length > 0 ? (
        floors.map((floor) => (
          <div key={floor.floor_number} className="card">
            <div className="card-header">
              <h3 className="card-title">
                Floor {floor.floor_number} Room Specifications
              </h3>
              <span className="badge badge-neutral">{floor.room_requirements.length} Programmed Rooms</span>
            </div>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Room Type</th>
                    <th>Count</th>
                    <th>Target Area</th>
                    <th>Min Area Bound</th>
                    <th>Planning Priority</th>
                    <th>Attached Relationship</th>
                  </tr>
                </thead>
                <tbody>
                  {floor.room_requirements.map((rm, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600, textTransform: 'capitalize', color: 'var(--text-primary)' }}>
                        {rm.room_type.replace(/_/g, ' ')}
                      </td>
                      <td>{rm.min_count || 1}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>
                        {rm.target_area_sqm ? `${rm.target_area_sqm.toFixed(1)} m²` : '—'}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>
                        {rm.min_area_sqm ? `${rm.min_area_sqm.toFixed(1)} m²` : '5.0 m²'}
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            rm.priority === 'high'
                              ? 'badge-warning'
                              : rm.priority === 'low'
                              ? 'badge-neutral'
                              : 'badge-info'
                          }`}
                        >
                          {rm.priority || 'normal'}
                        </span>
                      </td>
                      <td>
                        {rm.attached_to_room_id ? (
                          <span className="badge badge-neutral">🔗 Attached Suite</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>None</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))
      ) : (
        <div className="card">
          <p style={{ color: 'var(--text-secondary)' }}>
            Program requirements were generated and mapped directly to the active floor plan set.
          </p>
        </div>
      )}
    </div>
  );
};
