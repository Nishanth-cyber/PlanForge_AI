import React, { useState } from 'react';
import type { RequirementProgressItem } from '../../api/types';

interface RequirementProgressProps {
  progress: RequirementProgressItem[];
  remainingCount: number;
  isReadyForGeneration?: boolean;
}

export const RequirementProgress: React.FC<RequirementProgressProps> = ({
  progress,
  remainingCount,
  isReadyForGeneration = false,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(true);

  if (!progress || progress.length === 0) {
    return null;
  }

  return (
    <section className="req-progress-section" aria-label="Building requirements progress" data-testid="requirement-progress">
      <div
        className="req-progress-header"
        onClick={() => setIsOpen((prev) => !prev)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setIsOpen((prev) => !prev);
          }
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontWeight: 700, letterSpacing: '0.04em', fontSize: '0.75rem', textTransform: 'uppercase' }}>
            Building Requirements
          </span>
          <span className={`req-progress-badge ${isReadyForGeneration ? 'all-ready' : ''}`}>
            {isReadyForGeneration
              ? '✓ Ready to Generate'
              : `${remainingCount} requirement${remainingCount === 1 ? '' : 's'} remaining`}
          </span>
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {isOpen ? '▲' : '▼'}
        </span>
      </div>

      {isOpen && (
        <div className="req-progress-body">
          {progress.map((item, idx) => {
            const isDone = item.status === 'completed';
            const isCurr = item.status === 'current';
            return (
              <div key={idx} className={`req-progress-item ${item.status}`}>
                <div className="req-item-left">
                  {isDone ? (
                    <span className="req-icon-check">✓</span>
                  ) : isCurr ? (
                    <span className="req-icon-current">▶</span>
                  ) : (
                    <span className="req-icon-pending">○</span>
                  )}
                  <span>{item.name}</span>
                </div>
                {item.value && <span className="req-item-value">{item.value}</span>}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
