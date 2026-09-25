import React, { useEffect, useState } from 'react';
import { getHealth } from '../../api/projects';
import type { HealthResponse } from '../../api/types';

interface HeaderProps {
  onNewProject: () => void;
  onDashboard: () => void;
  onAssistant?: () => void;
  onProjects?: () => void;
  onBenchmarks?: () => void;
  currentView: string;
  theme?: 'light' | 'dark';
  onToggleTheme?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  onNewProject,
  onDashboard,
  onAssistant,
  onProjects,
  onBenchmarks,
  currentView,
  theme = 'light',
  onToggleTheme,
}) => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isOnline, setIsOnline] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const res = await getHealth();
        if (mounted) {
          setHealth(res);
          setIsOnline(true);
        }
      } catch {
        if (mounted) {
          setIsOnline(false);
        }
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="app-header">
      <div className="brand-container" onClick={onDashboard} style={{ cursor: 'pointer' }}>
        <div className="brand-logo">
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
        </div>
        <div className="brand-title">
          PlanForge <span style={{ color: 'var(--text-muted)' }}>AI</span>
        </div>
      </div>

      <div className="header-actions">
        {onAssistant && (
          <button
            className={`btn ${currentView === 'assistant' ? 'btn-primary' : 'btn-outline'} btn-sm`}
            onClick={onAssistant}
            data-testid="header-assistant-btn"
            style={{ fontWeight: 600 }}
          >
            ✨ AI Assistant
          </button>
        )}

        <button
          className={`btn ${currentView === 'dashboard' || currentView === 'home' ? 'btn-secondary' : 'btn-outline'} btn-sm`}
          onClick={onDashboard}
        >
          Home
        </button>

        <button
          className={`btn ${currentView === 'projects' ? 'btn-secondary' : 'btn-outline'} btn-sm`}
          onClick={onProjects || onDashboard}
        >
          Projects
        </button>

        <button
          className={`btn ${currentView === 'new_project' ? 'btn-secondary' : 'btn-primary'} btn-sm`}
          onClick={onNewProject}
        >
          + New Project
        </button>

        {onBenchmarks && (
          <button
            className={`btn ${currentView === 'benchmarks' ? 'btn-secondary' : 'btn-outline'} btn-sm`}
            onClick={onBenchmarks}
            style={{ fontSize: '0.8rem' }}
          >
            Benchmarks
          </button>
        )}

        {onToggleTheme && (
          <button
            className="btn btn-outline btn-sm"
            onClick={onToggleTheme}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
            style={{ fontWeight: 500 }}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        )}

        <div
          className="health-badge"
          title={health ? `${health.service} (${health.llm_provider || 'Local'})` : 'Backend status'}
          style={{ padding: '0.3rem 0.6rem' }}
        >
          <div className={`health-dot ${isOnline ? '' : 'offline'}`} />
          <span style={{ fontSize: '0.75rem' }}>{isOnline ? 'Online' : 'Offline'}</span>
        </div>
      </div>
    </header>
  );
};
