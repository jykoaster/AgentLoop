// 所有對後端 `/api/*` 的呼叫集中在這個檔案，元件測試用 `vi.mock('../api')` 取代。

const BASE = '/api'

export interface StageMap {
  analyze_plan: string
  human_confirm: string
  execute: string
  review: string
  archive: string
}

export interface ChangeRow {
  change_name: string
  branch_name: string
  task: string
  iteration: number
  stages: StageMap
  stage_notes: Record<string, string>
}

export type QuestionKind = 'text' | 'choice' | 'confirm' | 'pause'

export interface Question {
  id: string
  stage: string
  kind: QuestionKind
  prompt: string
  options: string[]
  required: boolean
  multiline: boolean
}

export interface RunStatus {
  active: boolean
  run_id?: string
  label?: string
  change_name?: string
  task?: string
  stage?: string
  question?: Question | null
}

export interface StageDetail {
  status: string
  note: string
  fields: Record<string, unknown>
  log: string
}

export interface ArchiveRow {
  dir: string
  date: string
  name: string
}

export interface SecretField {
  set: boolean
  last4: string
}

export interface SettingsView {
  target_project: string
  oauth_token: SecretField
  api_key: SecretField
  workspace_root: string
  run_active: boolean
}

export interface SettingsUpdate {
  target_project?: string
  oauth_token?: string
  api_key?: string
}

export interface SearchResult {
  answer: string
  references: { path: string; doc_type: string }[]
}

export interface FileContent {
  path: string
  content: string
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      if (data && typeof data.detail === 'string') detail = data.detail
    } catch {
      // body 不是 JSON，沿用 statusText
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export function getChanges(): Promise<ChangeRow[]> {
  return request('/changes')
}

export function getStageDetail(name: string, stage: string): Promise<StageDetail> {
  return request(`/changes/${encodeURIComponent(name)}/stages/${encodeURIComponent(stage)}`)
}

export function getChangeFiles(name: string): Promise<string[]> {
  return request(`/changes/${encodeURIComponent(name)}/files`)
}

export function getChangeFile(name: string, path: string): Promise<FileContent> {
  return request(`/changes/${encodeURIComponent(name)}/files/${path}`)
}

export function getRun(): Promise<RunStatus> {
  return request('/run')
}

export function postNewTask(task: string): Promise<{ run_id: string }> {
  return request('/runs', { method: 'POST', body: JSON.stringify({ task }) })
}

export function postRerun(name: string, stage: string): Promise<unknown> {
  return request(`/changes/${encodeURIComponent(name)}/rerun`, {
    method: 'POST',
    body: JSON.stringify({ stage }),
  })
}

export function postAnswer(questionId: string, answer: string): Promise<unknown> {
  return request('/run/answer', {
    method: 'POST',
    body: JSON.stringify({ question_id: questionId, answer }),
  })
}

export function postAbort(): Promise<unknown> {
  return request('/run/abort', { method: 'POST' })
}

export function getArchive(): Promise<ArchiveRow[]> {
  return request('/archive')
}

export function getArchiveFiles(dir: string): Promise<string[]> {
  return request(`/archive/${encodeURIComponent(dir)}/files`)
}

export function getArchiveFile(dir: string, path: string): Promise<FileContent> {
  return request(`/archive/${encodeURIComponent(dir)}/files/${path}`)
}

export function getSpecs(): Promise<string[]> {
  return request('/specs')
}

export function getSpec(domain: string): Promise<{ domain: string; content: string }> {
  return request(`/specs/${encodeURIComponent(domain)}`)
}

export function searchSpecs(query: string): Promise<SearchResult> {
  return request('/specs/search', { method: 'POST', body: JSON.stringify({ query }) })
}

export function getSettings(): Promise<SettingsView> {
  return request('/settings')
}

export function putSettings(body: SettingsUpdate): Promise<SettingsView> {
  return request('/settings', { method: 'PUT', body: JSON.stringify(body) })
}

export function getFs(path: string): Promise<string[]> {
  return request(`/fs?path=${encodeURIComponent(path)}`)
}
