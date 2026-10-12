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
  ChatTurnRequest,
  ChatTurnResponse,
  EditDesignRequest,
  EditDesignResponse,
  VersionSummary,
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

export async function clearProjects(): Promise<{ status: string; cleared_count: number }> {
  return request<{ status: string; cleared_count: number }>('/projects', {
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

export async function sendChatTurn(payload: ChatTurnRequest): Promise<ChatTurnResponse> {
  return request<ChatTurnResponse>('/api/v1/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getClarifications(projectId: string): Promise<import('./types').ClarificationListResponse> {
  return request<import('./types').ClarificationListResponse>(`/projects/${encodeURIComponent(projectId)}/clarifications`);
}

export async function submitClarificationResponse(
  projectId: string,
  requestId: string,
  payload: import('./types').ClarificationResponsePayload
): Promise<import('./types').ClarificationSubmitResponse> {
  return request<import('./types').ClarificationSubmitResponse>(
    `/projects/${encodeURIComponent(projectId)}/clarifications/${encodeURIComponent(requestId)}/response`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function resumeProject(projectId: string): Promise<GenerationResponse> {
  return request<GenerationResponse>(`/projects/${encodeURIComponent(projectId)}/resume`, {
    method: 'POST',
    body: JSON.stringify({ reason: 'User resumed workflow' }),
  });
}

export async function cancelProject(projectId: string, reason?: string): Promise<GenerationResponse> {
  return request<GenerationResponse>(`/projects/${encodeURIComponent(projectId)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason || 'User cancelled' }),
  });
}

export async function editProjectDesign(
  projectId: string,
  payload: EditDesignRequest
): Promise<EditDesignResponse> {
  return request<EditDesignResponse>(`/projects/${encodeURIComponent(projectId)}/edit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function undoProjectDesign(projectId: string): Promise<EditDesignResponse> {
  return request<EditDesignResponse>(`/projects/${encodeURIComponent(projectId)}/undo`, {
    method: 'POST',
  });
}

export async function getProjectVersions(projectId: string): Promise<VersionSummary[]> {
  return request<VersionSummary[]>(`/projects/${encodeURIComponent(projectId)}/versions`);
}


