import React from 'react';
import type { FloorPlan } from '../../api/types';

interface FloorTabsProps {
  floorPlans: FloorPlan[];
  activeFloor: number;
  onSelectFloor: (floorNumber: number) => void;
}

export const FloorTabs: React.FC<FloorTabsProps> = ({
  floorPlans,
  activeFloor,
  onSelectFloor,
}) => {
  if (!floorPlans || floorPlans.length <= 1) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
        <span className="badge badge-neutral">Single Floor</span>
        <span>Floor 1 (Ground Level)</span>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>FLOORS:</span>
      {floorPlans.map((fp) => (
        <button
          key={fp.floor_number}
          className={`btn btn-sm ${activeFloor === fp.floor_number ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => onSelectFloor(fp.floor_number)}
        >
          Floor {fp.floor_number}
          {fp.geometry && (
            <span style={{ fontSize: '0.7rem', opacity: 0.8, marginLeft: '0.25rem' }}>
              ({fp.geometry.rooms.length} rooms)
            </span>
          )}
        </button>
      ))}
    </div>
  );
};
