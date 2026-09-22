import React from 'react';
import type { GeoRoom, Geometry, ValidationResult } from '../../api/types';
import { getPolygonBoundingBox } from '../../utils/geometry';

interface RoomInspectorProps {
  room: GeoRoom | null;
  geometry: Geometry | null;
  validationResult?: ValidationResult;
  onClose: () => void;
  onViewTrace?: (entityId: string) => void;
}

export const RoomInspector: React.FC<RoomInspectorProps> = ({
  room,
  geometry,
  validationResult,
  onClose,
  onViewTrace,
}) => {
  if (!room) return null;

  // Compute dimensions from bounding box
  const poly = room.usable_polygon || room.built_polygon || [];
  const bbox = getPolygonBoundingBox(poly);
  const dimensionsText = poly.length >= 3 ? `${bbox.width.toFixed(2)}m × ${bbox.height.toFixed(2)}m` : 'N/A';

  // Find connected rooms via door objects
  const connectedRoomNames: string[] = [];
  if (geometry && geometry.doors) {
    for (const d of geometry.doors) {
      if (d.connects_from === room.id || d.connects_from === room.room_type) {
        connectedRoomNames.push(d.connects_to);
      } else if (d.connects_to === room.id || d.connects_to === room.room_type) {
        connectedRoomNames.push(d.connects_from);
      }
    }
  }

  // Find any validation issues associated with this room
  const roomIssues = validationResult?.issues.filter(
    (i) => i.entity_id === room.id || i.description.toLowerCase().includes(room.room_type.toLowerCase())
  ) || [];

  const isValid = roomIssues.filter((i) => i.severity === 'error').length === 0;

  return (
    <div
      className="card"
      style={{
        width: '100%',
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.85rem',
        background: 'var(--bg-card)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '0.85rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
        <div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, textTransform: 'capitalize' }}>
            {room.room_type.replace(/_/g, ' ')}
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Room Information</span>
        </div>
        <button
          className="btn btn-outline btn-sm"
          style={{ padding: '0.15rem 0.45rem', fontSize: '0.75rem' }}
          onClick={onClose}
          title="Close"
        >
          ✕
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.65rem' }}>
        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Area</span>
          <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>
            {room.area_sqm.toFixed(2)} m² <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>({(room.area_sqm * 10.7639).toFixed(1)} sq ft)</span>
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Floor</span>
          <span style={{ fontWeight: 600 }}>Floor {room.floor_number}</span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Dimensions</span>
          <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{dimensionsText}</span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Validation</span>
          <span style={{ fontWeight: 600, color: isValid ? 'var(--status-success)' : '#f87171' }}>
            {isValid ? '✓ Valid' : '✗ Issues Found'}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Room ID</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{room.id.slice(0, 16)}</span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Allocation ID</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
            {room.architectural_room_id ? room.architectural_room_id.slice(0, 16) : room.id.slice(0, 12)}
          </span>
        </div>
      </div>

      {roomIssues.length > 0 && (
        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          {roomIssues.map((issue, idx) => (
            <div key={idx} style={{ color: issue.severity === 'error' ? '#f87171' : '#fbbf24' }}>
              • {issue.description}
            </div>
          ))}
        </div>
      )}

      {connectedRoomNames.length > 0 && (
        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
            Connected To
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
            {connectedRoomNames.map((c, idx) => (
              <span key={idx} className="badge badge-neutral" style={{ fontSize: '0.7rem', textTransform: 'capitalize' }}>
                {c.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {onViewTrace && (
        <button
          className="btn btn-outline btn-sm"
          style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}
          onClick={() => onViewTrace(room.id)}
        >
          Explore Room Traceability →
        </button>
      )}
    </div>
  );
};
