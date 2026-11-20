const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export type LlmProvider = 'gemini' | 'qwen'
export type ReviewSource = 'ocr' | 'llm'

export type MarkdownChange = {
  before_start?: number
  before_end?: number
  start: number
  end: number
  before: string
  after: string
  title?: string
}

export type ReviewPage = {
  page_id: string
  raw_text: string
  corrected_text: string
}

export type ReviewMarkdownPage = {
  page_id: string
  ocr_markdown: string
  llm_markdown: string
  llm_changes: MarkdownChange[]
}

export type ReviewMetadata = {
  label_code: string
  label_name: string
  sender: string | null
  recipient: string | null
  date_time: string | null
  document_type: string
}

export type ReviewDraft = {
  review_id: string
  document_name: string
  page_count: number
  pages: ReviewPage[]
  markdown_pages: ReviewMarkdownPage[]
  metadata: ReviewMetadata
  provider: LlmProvider
  model: string
  status: string
}

export type ReviewPreviewPage = {
  page_id: string
  ocr_markdown: string
  llm_markdown: string
  ocr_manual_changes: MarkdownChange[]
  llm_changes: MarkdownChange[]
  llm_manual_changes: MarkdownChange[]
}

export type EditPosition = {
  start_offset: number; end_offset: number
  start_line: number; start_column: number; end_line: number; end_column: number
}
export type ReviewEditLogEntry = {
  actor?: 'user' | 'llm'
  actor_name?: string
  operation?: 'insert' | 'delete' | 'replace'
  position_basis?: string
  before_position?: EditPosition
  after_position?: EditPosition
  mirrored_before_position?: EditPosition
  mirrored_after_position?: EditPosition
  context_before?: string
  context_after?: string
  content_type?: 'text' | 'formula'
  page_id: string
  source_side: ReviewSource
  timestamp: string
  before: string
  after: string
  mirrored_before: string
  mirrored_after: string
}

export type FinalizeReviewResult = {
  document_id: string
  user_id: string
  sequence: number
  label_code: string
  label_name: string
  digitized_dir: string
  digitized_page_paths: string[]
  origin_pdf_path: string
  edit_log_path: string
  display_name: string
  created_at: string
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `API request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export async function createReview(documentName: string, provider: LlmProvider): Promise<ReviewDraft> {
  const response = await fetch(`${apiBaseUrl}/api/llm/reviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_name: documentName, provider }),
  })
  return readResponse<ReviewDraft>(response)
}

export async function previewReview(
  reviewId: string,
  pages: Record<string, { ocr_text: string; llm_text: string }>,
): Promise<ReviewPreviewPage[]> {
  const response = await fetch(`${apiBaseUrl}/api/llm/reviews/${encodeURIComponent(reviewId)}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages, content_format: 'markdown' }),
  })
  const result = await readResponse<{ pages: ReviewPreviewPage[] }>(response)
  return result.pages
}

export async function finalizeReview(
  reviewId: string,
  source: ReviewSource,
  approvedPages: Record<string, string>,
  editLog: ReviewEditLogEntry[],
  labelCode?: string,
  displayName?: string,
): Promise<FinalizeReviewResult> {
  const response = await fetch(`${apiBaseUrl}/api/llm/reviews/${encodeURIComponent(reviewId)}/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content_format: 'markdown', source, approved_pages: approvedPages, edit_log: editLog, label_code: labelCode, display_name: displayName }),
  })
  return readResponse<FinalizeReviewResult>(response)
}

export async function getReviewLabels(): Promise<Record<string, string>> {
  return readResponse<Record<string, string>>(await fetch(`${apiBaseUrl}/api/llm/labels`))
}

export function getReviewOriginalPageUrl(reviewId: string, pageId: string): string {
  return `${apiBaseUrl}/api/llm/reviews/${encodeURIComponent(reviewId)}/original/${encodeURIComponent(pageId)}`
}
