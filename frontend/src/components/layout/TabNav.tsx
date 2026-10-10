import React from 'react';

export type ActiveTab =
  | 'overview'
  | 'requirements'
  | 'plot'
  | 'floorplan'
  | 'alternatives'
  | 'validation'
  | 'explainability'
  | 'refinement'
  | 'export';

interface TabNavProps {
  projectName: string;
  projectId: string;
  isValid?: boolean;
  statusLabel?: string;
  statusBadgeClass?: string;
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  hasTrace?: boolean;
  alternativesCount?: number;
}

export const TabNav: React.FC<TabNavProps> = ({
  projectName,
  projectId,
  isValid,
  statusLabel,
  statusBadgeClass,
  activeTab,
  onTabChange,
  alternativesCount = 1,
}) => {
  const tabs: { id: ActiveTab; label: string; badge?: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'requirements', label: 'Requirements' },
    { id: 'plot', label: 'Plot' },
    { id: 'floorplan', label: 'Floor Plan' },
    { id: 'alternatives', label: 'Alternatives', badge: alternativesCount > 1 ? `${alternativesCount}` : undefined },
    { id: 'validation', label: 'Validation' },
    { id: 'explainability', label: 'Explainability' },
    { id: 'refinement', label: 'Refinement' },
    { id: 'export', label: 'Export' },
  ];

  return (
    <div className="subnav-container">
      <div className="project-title-bar">
        <span className="project-title-text">{projectName || projectId}</span>
        {(statusLabel || isValid !== undefined) && (
          <span className={`badge ${statusBadgeClass || (isValid ? 'badge-success' : 'badge-danger')}`}>
            {statusLabel || (isValid ? 'Valid Design' : 'Violations Found')}
          </span>
        )}
      </div>

      <nav className="nav-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`nav-tab-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
            {tab.badge && (
              <span
                style={{
                  marginLeft: '0.4rem',
                  fontSize: '0.7rem',
                  padding: '0.1rem 0.35rem',
                  borderRadius: '10px',
                  background: 'rgba(56, 189, 248, 0.2)',
                  color: 'var(--accent-sky)',
                }}
              >
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
};
