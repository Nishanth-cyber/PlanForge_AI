import React, { useEffect, useState } from 'react';
import { listProjects, deleteProject } from '../../api/projects';
import type { ProjectDetailResponse } from '../../api/types';

interface HomeViewProps {
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
  onStartAssistant?: () => void;
  onViewProjects: () => void;
  onViewBenchmarks?: () => void;
}

export const HomeView: React.FC<HomeViewProps> = ({
  onSelectProject,
  onNewProject,
  onStartAssistant,
  onViewProjects,
  onViewBenchmarks,
}) => {
  const [projects, setProjects] = useState<ProjectDetailResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;
    const fetchProjects = async () => {
      try {
        const list = await listProjects();
        if (mounted) setProjects(list);
      } catch (err) {
        console.error('Failed to load projects list', err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchProjects();
    return () => {
      mounted = false;
    };
  }, []);

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, projectId: string, projectName: string) => {
    e.stopPropagation();
    const confirmed = window.confirm(
      `Are you sure you want to remove project "${projectName}"? This will delete all generated floor plans and outputs.`
    );
    if (!confirmed) return;

    try {
      setDeletingId(projectId);
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.project_id !== projectId));
    } catch (err) {
      console.error('Failed to delete project', err);
      alert('Failed to remove project. Please try again.');
    } finally {
      setDeletingId(null);
    }
  };

  const recentProjects = projects.slice(0, 5);

  return (
    <div style={{ width: '100%', maxWidth: '1100px', margin: '2rem auto', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Brand Hero - Minimal & Direct */}
      <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
        <h1 style={{ fontSize: '2.25rem', fontWeight: 700, letterSpacing: '-0.03em', margin: 0 }}>
          PlanForge AI
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.05rem', margin: 0 }}>
          AI-assisted residential floor plan generation
        </p>

        {/* Primary Action Buttons */}
        <div style={{ display: 'flex', gap: '0.85rem', marginTop: '1.25rem', flexWrap: 'wrap', justifyContent: 'center' }}>
          {onStartAssistant && (
            <button
              className="btn btn-primary"
              onClick={onStartAssistant}
              style={{ padding: '0.65rem 1.4rem', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontWeight: 600 }}
              data-testid="home-start-assistant-btn"
            >
              <span>✨</span>
              <span>Chat with AI Architect</span>
            </button>
          )}
          <button
            className="btn btn-outline"
            onClick={onNewProject}
            style={{ padding: '0.65rem 1.4rem', fontSize: '0.95rem' }}
          >
            + New Project
          </button>
          <button
            className="btn btn-outline"
            onClick={onViewProjects}
            style={{ padding: '0.65rem 1.4rem', fontSize: '0.95rem' }}
          >
            View Projects
          </button>
        </div>
      </div>

      {/* Recent Projects Section */}
      <div className="card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Recent Projects</h2>
          {projects.length > 5 && (
            <button
              onClick={onViewProjects}
              className="btn btn-outline btn-sm"
              style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
            >
              View All ({projects.length}) →
            </button>
          )}
        </div>

        {loading ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Loading projects...
          </div>
        ) : recentProjects.length === 0 ? (
          <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            No recent projects found. Click <strong>+ New Project</strong> to begin.
          </div>
        ) : (
          <div className="table-container" style={{ border: 'none' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '0.875rem' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '0.5rem 0.75rem' }}>Project Name</th>
                  <th style={{ textAlign: 'center', padding: '0.5rem 0.75rem', width: '120px' }}>Floors</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem 0.75rem', width: '140px' }}>Status</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem 0.75rem', width: '150px' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {recentProjects.map((p) => {
                  const statusText = p.is_valid ? '✓ Completed' : p.status === 'completed' ? 'Warnings' : 'Draft';
                  const isDeleting = deletingId === p.project_id;
                  return (
                    <tr
                      key={p.project_id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onSelectProject(p.project_id)}
                    >
                      <td style={{ padding: '0.6rem 0.75rem', fontWeight: 500 }}>
                        {p.project_name}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        {(p as any).target_floors || 1}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem' }}>
                        <span
                          className={`badge ${p.is_valid ? 'badge-success' : 'badge-neutral'}`}
                          style={{ fontSize: '0.75rem' }}
                        >
                          {statusText}
                        </span>
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '0.4rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                          <button
                            className="btn btn-outline btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectProject(p.project_id);
                            }}
                          >
                            Open
                          </button>
                          <button
                            className="btn btn-outline btn-sm"
                            style={{
                              fontSize: '0.75rem',
                              padding: '0.2rem 0.6rem',
                              color: '#ef4444',
                              borderColor: 'rgba(239, 68, 68, 0.4)',
                            }}
                            disabled={isDeleting}
                            onClick={(e) => handleDelete(e, p.project_id, p.project_name)}
                            title="Remove project"
                          >
                            {isDeleting ? 'Removing...' : 'Remove'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Research Presets Link - Clean, unobtrusive footer */}
      {onViewBenchmarks && (
        <div style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Need evaluation test cases?{' '}
          <button
            onClick={onViewBenchmarks}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-primary)',
              textDecoration: 'underline',
              cursor: 'pointer',
              fontSize: 'inherit',
              padding: 0,
            }}
          >
            Open Research Benchmark Cases →
          </button>
        </div>
      )}
    </div>
  );
};
