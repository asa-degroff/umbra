const BASE = '/api'

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// Memory
export const getBlocks = () => fetchJSON<any[]>('/memory/blocks')
export const updateBlock = (id: string, value: string) =>
  fetchJSON(`/memory/blocks/${id}`, { method: 'PUT', body: JSON.stringify({ value }) })
export const getArchival = (params: { query?: string; cursor?: string; limit?: number }) => {
  const sp = new URLSearchParams()
  if (params.query) sp.set('query', params.query)
  if (params.cursor) sp.set('cursor', params.cursor)
  if (params.limit) sp.set('limit', String(params.limit))
  return fetchJSON<any>(`/memory/archival?${sp}`)
}
export const deletePassage = (id: string) =>
  fetchJSON(`/memory/archival/${id}`, { method: 'DELETE' })

// Messages
export const getMessages = (params: { cursor?: string; limit?: number }) => {
  const sp = new URLSearchParams()
  if (params.cursor) sp.set('cursor', params.cursor)
  if (params.limit) sp.set('limit', String(params.limit))
  return fetchJSON<any>(`/messages/?${sp}`)
}

// Tools
export const getAttachedTools = () => fetchJSON<any[]>('/tools/attached')
export const getAvailableTools = () => fetchJSON<any[]>('/tools/available')
export const attachTool = (id: string) => fetchJSON(`/tools/attach/${id}`, { method: 'POST' })
export const detachTool = (id: string) => fetchJSON(`/tools/detach/${id}`, { method: 'POST' })
export const getEnvVars = () => fetchJSON<Record<string, string>>('/tools/env')
export const updateEnvVars = (vars: Record<string, string>) =>
  fetchJSON('/tools/env', { method: 'PUT', body: JSON.stringify(vars) })

// Tasks
export const getTasks = () => fetchJSON<any[]>('/tasks/')
export const getThreadStates = () => fetchJSON<any[]>('/tasks/threads')

// System
export const getHealth = () => fetchJSON<any>('/system/health')
export const getAgentInfo = () => fetchJSON<any>('/system/agent')
