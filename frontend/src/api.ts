import type { Job, Paper } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`
    try {
      const body = (await res.json()) as { error?: string; detail?: string }
      detail = body.error ?? body.detail ?? detail
    } catch {
      // ignore parse errors, keep default message
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export interface CreatedJob {
  id: string
  error?: string
}

export function createJob(query: string, count: number): Promise<CreatedJob> {
  return request<CreatedJob>('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, count }),
  })
}

export function getJob(id: string): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`)
}

export function getResults(): Promise<Paper[]> {
  return request<Paper[]>('/api/results')
}