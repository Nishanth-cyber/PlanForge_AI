/**
 * API service endpoints for PlanForge projects and generation.
 */

import { request } from './client';
import type {
  HealthResponse,
  ProjectDetailResponse,
  ProjectData,
  GenerationRequest,
  GenerationResponse,
  AlternativeSummarySchema,
  ExportResponse,
  DecisionTrace,
} from './types';

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export async function listProjects(): Promise<ProjectDetailResponse[]> {
  return request<ProjectDetailResponse[]>('/projects');
}

export async function getProject(projectId: string): Promise<ProjectDetailResponse> {
  return request<ProjectDetailResponse>(`/projects/${encodeURIComponent(projectId)}`);
}

export async function deleteProject(projectId: string): Promise<{ status: string; project_id: string }> {
  return request<{ status: string; project_id: string }>(`/projects/${encodeURIComponent(projectId)}`, {
    method: 'DELETE',
  });
}

export async function getProjectData(projectId: string): Promise<ProjectData> {
  return request<ProjectData>(`/projects/${encodeURIComponent(projectId)}/data`);
}

export async function getProjectTrace(projectId: string): Promise<DecisionTrace> {
  return request<DecisionTrace>(`/projects/${encodeURIComponent(projectId)}/trace`);
}

export async function getProjectAlternatives(projectId: string): Promise<AlternativeSummarySchema[]> {
  return request<AlternativeSummarySchema[]>(`/projects/${encodeURIComponent(projectId)}/alternatives`);
}

export async function getExportInventory(projectId: string): Promise<ExportResponse> {
  return request<ExportResponse>(`/projects/${encodeURIComponent(projectId)}/export`);
}

export async function generateFloorPlan(payload: GenerationRequest): Promise<GenerationResponse> {
  return request<GenerationResponse>('/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
