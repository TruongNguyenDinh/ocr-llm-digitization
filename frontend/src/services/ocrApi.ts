export type OcrPage = {
  page_number: number
  markdown: string
}

export type OcrJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export type OcrJob = {
  job_id: string
  filename: string
  status: OcrJobStatus
  document_name: string | null
  completed_pages: number
  total_pages: number | null
  pages: OcrPage[]
  error: string | null
  stage: string
  stage_message: string
  stage_started_at: string | null
  last_activity_at: string | null
  current_page: number | null
  diagnostics: string[]
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `API request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export async function createOcrJob(file: File): Promise<string> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(`${apiBaseUrl}/api/ocr/jobs`, { method: 'POST', body })
  const result = await readResponse<{ job_id: string }>(response)
  return result.job_id
}

export async function getOcrJob(jobId: string): Promise<OcrJob> {
  const response = await fetch(`${apiBaseUrl}/api/ocr/jobs/${encodeURIComponent(jobId)}`)
  return readResponse<OcrJob>(response)
}

export async function cancelOcrJob(jobId: string, keepalive = false): Promise<OcrJob> {
  const response = await fetch(`${apiBaseUrl}/api/ocr/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
    keepalive,
  })
  return readResponse<OcrJob>(response)
}

export function getOcrAssetUrl(documentName: string, assetPath: string): string {
  const safePath = assetPath.split('/').map(encodeURIComponent).join('/')
  return `${apiBaseUrl}/api/ocr/documents/${encodeURIComponent(documentName)}/${safePath}`
}
