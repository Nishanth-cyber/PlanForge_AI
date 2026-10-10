/**
 * Centralized HTTP Client for PlanForge API.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '';

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      let errorData: any;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      const message = errorData?.detail || errorData?.message || `HTTP ${response.status}: ${response.statusText}`;
      throw new ApiError(message, response.status, errorData);
    }
    return await response.json();
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(err?.message || 'Network connection to backend failed', 0, err);
  }
}

export function getExportFileUrl(projectId: string, relativePath: string): string {
  return `${BASE_URL}/projects/${encodeURIComponent(projectId)}/export?file=${encodeURIComponent(relativePath)}`;
}

export function getExportDxfUrl(projectId: string, floor?: number): string {
  const query = floor !== undefined ? `?floor=${encodeURIComponent(floor)}` : '';
  return `${BASE_URL}/projects/${encodeURIComponent(projectId)}/export/dxf${query}`;
}

export function getExportSvgUrl(projectId: string, floor: number = 1): string {
  return `${BASE_URL}/projects/${encodeURIComponent(projectId)}/export/svg?floor=${encodeURIComponent(floor)}`;
}

export function getExportZipUrl(projectId: string): string {
  return `${BASE_URL}/projects/${encodeURIComponent(projectId)}/export/zip`;
}

