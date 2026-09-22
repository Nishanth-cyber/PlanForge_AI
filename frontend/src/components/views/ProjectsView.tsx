import React, { useEffect, useState } from 'react';
import { listProjects, deleteProject } from '../../api/projects';
import type { ProjectDetailResponse } from '../../api/types';

interface ProjectsViewProps {
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({
  onSelectProject,
  onNewProject,
}) => {
  const [projects, setProjects] = useState<ProjectDetailResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  return (
    <div style={{ width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>Projects</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0.25rem 0 0' }}>
            All residential floor plan projects in your workspace
          </p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={onNewProject}>
          + New Project
        </button>
      </div>

      {/* Projects Table */}
      <div className="card" style={{ padding: '0.5rem' }}>
        {loading ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading projects...
          </div>
        ) : projects.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <p>No projects found.</p>
            <button className="btn btn-primary btn-sm" onClick={onNewProject} style={{ marginTop: '0.75rem' }}>
              Create Your First Project
            </button>
          </div>
        ) : (
          <div className="table-container" style={{ border: 'none' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '0.875rem' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '0.65rem 1rem' }}>Project</th>
                  <th style={{ textAlign: 'center', padding: '0.65rem 1rem', width: '100px' }}>Floors</th>
                  <th style={{ textAlign: 'left', padding: '0.65rem 1rem', width: '160px' }}>Status</th>
                  <th style={{ textAlign: 'left', padding: '0.65rem 1rem', width: '160px' }}>Validation</th>
                  <th style={{ textAlign: 'right', padding: '0.65rem 1rem', width: '150px' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((proj) => {
                  const statusLabel = proj.is_valid
                    ? '✓ Completed'
                    : proj.status === 'completed'
                    ? 'Completed'
                    : 'Draft';
                  const validationLabel = proj.validation_summary
                    ? `${proj.validation_summary.total_errors} err, ${proj.validation_summary.total_warnings} warn`
                    : 'Unchecked';
                  const isDeleting = deletingId === proj.project_id;

                  return (
                    <tr
                      key={proj.project_id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onSelectProject(proj.project_id)}
                    >
                      <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>
                        <div>{proj.project_name}</div>
                        <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          {proj.project_id.slice(0, 16)}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        {(proj as any).target_floors || 1}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span className={`badge ${proj.is_valid ? 'badge-success' : 'badge-neutral'}`}>
                          {statusLabel}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        {validationLabel}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '0.4rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                          <button
                            className="btn btn-outline btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.65rem' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectProject(proj.project_id);
                            }}
                          >
                            Open
                          </button>
                          <button
                            className="btn btn-outline btn-sm"
                            style={{
                              fontSize: '0.75rem',
                              padding: '0.25rem 0.65rem',
                              color: '#ef4444',
                              borderColor: 'rgba(239, 68, 68, 0.4)',
                            }}
                            disabled={isDeleting}
                            onClick={(e) => handleDelete(e, proj.project_id, proj.project_name)}
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
    </div>
  );
};
