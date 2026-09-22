import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { App } from '../App';
import * as projectApi from '../api/projects';

vi.spyOn(projectApi, 'getHealth').mockResolvedValue({
  status: 'ok',
  service: 'PlanForge AI',
  version: '0.1.0',
  llm_provider: 'MockLLMClient',
  device: 'CPU',
});

vi.spyOn(projectApi, 'listProjects').mockResolvedValue([
  {
    project_id: 'proj_mock_001',
    project_name: 'Suburban Residence',
    status: 'completed',
    is_valid: true,
    alternatives_count: 3,
    validation_summary: {
      overall_valid: true,
      overall_score: 98.5,
      total_errors: 0,
      total_warnings: 1,
    },
    export_bundle_path: 'outputs/proj_mock_001',
    decision_trace_available: true,
  },
]);

describe('PlanForge Web UI — App Core Workflow', () => {
  it('renders application header and home page', async () => {
    render(<App />);

    expect(screen.getAllByText(/PlanForge/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/AI-assisted residential floor plan generation/i)).toBeDefined();
    expect(screen.getAllByRole('button', { name: /\+ New Project/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: /View Projects/i })).toBeDefined();
    expect(screen.getByText(/Recent Projects/i)).toBeDefined();
  });

  it('navigates to New Project view and allows canceling back to home', async () => {
    render(<App />);

    const newProjBtns = screen.getAllByRole('button', { name: /\+ New Project/i });
    fireEvent.click(newProjBtns[0]);

    expect(screen.getByText(/Plot Boundary/i)).toBeDefined();
    expect(screen.getByTestId('input-project-name')).toBeDefined();

    // Cancel returns to home
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);

    expect(screen.getByText(/AI-assisted residential floor plan generation/i)).toBeDefined();
  });

  it('navigates to Benchmarks view and loads preset into New Project', async () => {
    render(<App />);

    const benchmarksBtn = screen.getByRole('button', { name: /Benchmarks/i });
    fireEvent.click(benchmarksBtn);

    expect(screen.getByText(/Research Benchmark Cases/i)).toBeDefined();
    expect(screen.getByText(/Small Single-Floor Bungalow/i)).toBeDefined();

    const loadBtns = screen.getAllByRole('button', { name: /Load & Configure →/i });
    fireEvent.click(loadBtns[0]);

    // Should load into New Project with preset name
    const titleInput = screen.getByDisplayValue(/Small Single-Floor Bungalow/i);
    expect(titleInput).toBeDefined();
  });

  it('navigates to Projects table page', async () => {
    render(<App />);

    const viewProjectsBtn = screen.getByRole('button', { name: /View Projects/i });
    fireEvent.click(viewProjectsBtn);

    expect(screen.getByText(/All residential floor plan projects in your workspace/i)).toBeDefined();
    const projRow = await screen.findByText(/Suburban Residence/i);
    expect(projRow).toBeDefined();
  });
});
