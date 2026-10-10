import React, { useEffect, useState } from 'react';
import type { ExportResponse, FloorPlanSet } from '../../api/types';
import { getExportInventory } from '../../api/projects';
import { getExportFileUrl, getExportDxfUrl, getExportSvgUrl, getExportZipUrl } from '../../api/client';

interface ExportViewProps {
  projectId: string;
  floorPlanSet?: FloorPlanSet | null;
}

export const ExportView: React.FC<ExportViewProps> = ({ projectId, floorPlanSet }) => {
  const [inventory, setInventory] = useState<ExportResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;
    const fetchInventory = async () => {
      try {
        const inv = await getExportInventory(projectId);
        if (mounted) setInventory(inv);
      } catch (err) {
        console.error('Failed to load export inventory', err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchInventory();
    return () => {
      mounted = false;
    };
  }, [projectId]);

  const floorCount = floorPlanSet?.floor_plans.length || 1;
  const projectJsonUrl = getExportFileUrl(projectId, 'project.json');
  const summaryMdUrl = getExportFileUrl(projectId, 'summary.md');
  const traceJsonUrl = getExportFileUrl(projectId, 'decision_trace.json');
  const dxfUrl = getExportDxfUrl(projectId);
  const zipUrl = getExportZipUrl(projectId);

  const dxfFile = inventory?.files.find((f) => f.filename.endsWith('.dxf'));
  const dxfFilename = dxfFile?.filename || (floorCount > 1 ? 'floorplans.dxf' : 'floorplan.dxf');
  const isFloorPlanValid = floorPlanSet
    ? floorPlanSet.floor_plans.every((fp) => fp.is_valid !== false)
    : true;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Overview Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Publication Exports & Project Artifacts</h2>
            <p className="card-subtitle">
              Download publication-grade drawings, domain JSON representations, and Markdown research reports generated in Phase 11.
            </p>
          </div>
          <span className="badge badge-info">Filesystem Verified</span>
        </div>

        {/* Primary Download Buttons Grid */}
        <div style={{ marginTop: '0.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          {/* Floor Plans PNG */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                Floor Drawings (PNG)
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                300 DPI publication floor plans
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: 'auto' }}>
              {Array.from({ length: floorCount }, (_, i) => i + 1).map((fn) => {
                const url = getExportFileUrl(projectId, `alternatives/alternative_1/floor_${fn}.png`);
                return (
                  <a
                    key={fn}
                    href={url}
                    download={`floor_${fn}.png`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-secondary btn-sm"
                    style={{ justifyContent: 'center' }}
                  >
                    Download Floor {fn} PNG ↗
                  </a>
                );
              })}
            </div>
          </div>

          {/* Floor Plans SVG */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                Vector Drawings (SVG)
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                Clean XML vector graphics
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: 'auto' }}>
              {Array.from({ length: floorCount }, (_, i) => i + 1).map((fn) => {
                const url = getExportSvgUrl(projectId, fn);
                return (
                  <a
                    key={fn}
                    href={url}
                    download={`floor_${fn}.svg`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-secondary btn-sm"
                    style={{ justifyContent: 'center' }}
                  >
                    Download Floor {fn} SVG ↗
                  </a>
                );
              })}
            </div>
          </div>

          {/* CAD Drawing (DXF) */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                CAD Drawing (DXF)
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                Publication-ready CAD geometry
              </span>
            </div>
            {isFloorPlanValid ? (
              <a
                href={dxfUrl}
                download={dxfFilename}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary btn-sm"
                style={{ marginTop: 'auto', justifyContent: 'center' }}
              >
                Download DXF ↗
              </a>
            ) : (
              <span
                className="badge badge-warning"
                style={{ marginTop: 'auto', justifyContent: 'center', textAlign: 'center', padding: '0.45rem' }}
                title="DXF export is only permitted for validated designs"
              >
                Requires Valid Plan
              </span>
            )}
          </div>

          {/* Project JSON */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                Complete Project JSON
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                Polygons, walls, doors, validation
              </span>
            </div>
            <a
              href={projectJsonUrl}
              download="project.json"
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm"
              style={{ marginTop: 'auto', justifyContent: 'center' }}
            >
              Download project.json ↗
            </a>
          </div>

          {/* Markdown Report */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                Markdown Report
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                Generation audit & room tables
              </span>
            </div>
            <a
              href={summaryMdUrl}
              download="summary.md"
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm"
              style={{ marginTop: 'auto', justifyContent: 'center' }}
            >
              Download summary.md ↗
            </a>
          </div>

          {/* Decision Trace */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                Decision Trace JSON
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                Structured provenance events
              </span>
            </div>
            <a
              href={traceJsonUrl}
              download="decision_trace.json"
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm"
              style={{ marginTop: 'auto', justifyContent: 'center' }}
            >
              Download trace.json ↗
            </a>
          </div>

          {/* Complete ZIP Archive */}
          <div
            style={{
              padding: '1.25rem',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)', display: 'block', fontSize: '0.95rem' }}>
                ZIP Archive Bundle
              </strong>
              <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                All drawings, JSON, and reports
              </span>
            </div>
            <a
              href={zipUrl}
              download={`${projectId}.zip`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm"
              style={{ marginTop: 'auto', justifyContent: 'center' }}
            >
              Download Complete ZIP ↗
            </a>
          </div>
        </div>
      </div>

      {/* Complete Export Bundle Inventory Table */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: '1rem' }}>
          Bundle File Inventory
        </h3>
        <p className="card-subtitle" style={{ marginBottom: '1.25rem' }}>
          Exact filesystem files exported in <code>outputs/{projectId}/</code>.
        </p>

        {loading ? (
          <p style={{ color: 'var(--text-muted)' }}>Scanning bundle inventory...</p>
        ) : !inventory || inventory.files.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>Bundle inventory is empty or being prepared.</p>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Relative File Path</th>
                  <th>Media Type</th>
                  <th>File Size</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {inventory.files.map((file, idx) => {
                  const url = getExportFileUrl(projectId, file.relative_path);
                  return (
                    <tr key={idx}>
                      <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-sky)' }}>
                        {file.relative_path}
                      </td>
                      <td style={{ color: 'var(--text-muted)' }}>{file.media_type}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>
                        {(file.size_bytes / 1024).toFixed(1)} KB
                      </td>
                      <td>
                        <a
                          href={url}
                          download={file.filename}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-outline btn-sm"
                        >
                          Download ↗
                        </a>
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
