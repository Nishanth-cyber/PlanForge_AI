import React from 'react';

interface BenchmarkPreset {
  id: string;
  name: string;
  category: string;
  floors: number;
  description: string;
  brief: string;
}

export const BENCHMARK_CASES: BenchmarkPreset[] = [
  {
    id: 'case_01',
    name: 'Small Single-Floor Bungalow',
    category: 'Single Floor',
    floors: 1,
    description: '40ft x 50ft plot with living, dining, kitchen, bedroom, and bathroom.',
    brief: `Single floor residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
Floor 1:
- 1 living room of 260 sq ft adjacent to dining room
- 1 dining room of 150 sq ft
- 1 kitchen of 130 sq ft
- 1 bedroom of 160 sq ft
- 1 bathroom of 60 sq ft`,
  },
  {
    id: 'case_04',
    name: 'Two-Floor Family Residence',
    category: 'Multi Floor',
    floors: 2,
    description: '50ft x 60ft plot with ground social zone, upstairs bedrooms, and staircase.',
    brief: `Two floor family house on a 50 feet by 60 feet plot with front setback: 3m, rear setback: 2m, side setback: 2m.
Target floors: 2
Floor 1:
- 1 living room of 320 sq ft
- 1 dining room of 180 sq ft
- 1 kitchen of 150 sq ft
- 1 powder room of 50 sq ft
Floor 2:
- 1 master bedroom of 220 sq ft
- 2 bedroom of 140 sq ft
- 1 bathroom of 70 sq ft`,
  },
  {
    id: 'case_06',
    name: 'Irregular L-Shaped Boundary',
    category: 'Irregular Plot',
    floors: 1,
    description: 'Non-convex L-shaped polygon plot testing geometric setback boundary offsets.',
    brief: `Single floor home on an L-shaped plot polygon: (0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20).
Front setback: 2m, rear setback: 2m, side setback: 2m.
Floor 1:
- 1 living room of 220 sq ft
- 1 kitchen of 110 sq ft
- 1 bedroom of 140 sq ft
- 1 bathroom of 55 sq ft`,
  },
  {
    id: 'case_07',
    name: 'Constrained Narrow Urban Infill',
    category: 'Tight Parcel',
    floors: 1,
    description: 'Narrow 30ft x 60ft urban infill parcel evaluating corridor and circulation efficiency.',
    brief: `Single floor home on a narrow 30 feet by 60 feet urban infill plot with front setback: 2m, rear setback: 2m, side setback: 1.5m.
Floor 1:
- 1 living room of 200 sq ft
- 1 kitchen of 100 sq ft
- 1 bedroom of 130 sq ft
- 1 bathroom of 50 sq ft`,
  },
  {
    id: 'case_09',
    name: 'Master Bedroom Attached Ensuite Suite',
    category: 'Attached Constraint',
    floors: 1,
    description: '45ft x 55ft plot verifying direct private master ensuite bathroom attachment.',
    brief: `Single floor residence on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
Floor 1:
- 1 living room of 280 sq ft
- 1 kitchen of 140 sq ft
- 1 master bedroom of 220 sq ft attached to ensuite bathroom
- 1 ensuite bathroom of 70 sq ft
- 1 guest bedroom of 140 sq ft`,
  },
  {
    id: 'case_10',
    name: 'Acoustic Separation Residence',
    category: 'Separation Constraint',
    floors: 1,
    description: '50ft x 60ft plot evaluating strict acoustic buffer between social and sleeping zones.',
    brief: `Single floor residence on a 50 feet by 60 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
Floor 1:
- 1 living room of 300 sq ft separate from bedroom
- 1 dining room of 160 sq ft
- 1 kitchen of 140 sq ft
- 2 bedroom of 160 sq ft
- 1 bathroom of 70 sq ft`,
  },
];

interface BenchmarksViewProps {
  onLoadBenchmark: (brief: string, name: string) => void;
  onBack: () => void;
}

export const BenchmarksView: React.FC<BenchmarksViewProps> = ({
  onLoadBenchmark,
  onBack,
}) => {
  return (
    <div style={{ width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <button
            onClick={onBack}
            className="btn btn-outline btn-sm"
            style={{ marginBottom: '0.75rem', fontSize: '0.775rem' }}
          >
            ← Back to Home
          </button>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>Research Benchmark Cases</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0.25rem 0 0' }}>
            Canonical residential cases evaluated in the PlanForge research paper
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: '0.5rem' }}>
        <table className="data-table" style={{ width: '100%', fontSize: '0.875rem' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '0.65rem 1rem' }}>Benchmark Case</th>
              <th style={{ textAlign: 'left', padding: '0.65rem 1rem', width: '150px' }}>Category</th>
              <th style={{ textAlign: 'center', padding: '0.65rem 1rem', width: '80px' }}>Floors</th>
              <th style={{ textAlign: 'left', padding: '0.65rem 1rem' }}>Key Architectural Evaluation</th>
              <th style={{ textAlign: 'right', padding: '0.65rem 1rem', width: '160px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {BENCHMARK_CASES.map((b) => (
              <tr key={b.id}>
                <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{b.name}</td>
                <td style={{ padding: '0.75rem 1rem' }}>
                  <span className="badge badge-neutral" style={{ fontSize: '0.75rem' }}>
                    {b.category}
                  </span>
                </td>
                <td style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  {b.floors}
                </td>
                <td style={{ padding: '0.75rem 1rem', color: 'var(--text-secondary)', fontSize: '0.825rem' }}>
                  {b.description}
                </td>
                <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                  <button
                    className="btn btn-primary btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.3rem 0.75rem' }}
                    onClick={() => onLoadBenchmark(b.brief, b.name)}
                  >
                    Load & Configure →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
