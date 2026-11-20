import { wordChange } from '../services/editContext'
import { rehypeHighlights } from '../services/reviewHighlights'
import { Component, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ErrorInfo, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'katex/dist/katex.min.css'
import { FormulaEditor } from './FormulaEditor'
import { findFormulas } from '../services/formulas'
import { getOcrAssetUrl } from '../services/ocrApi'
import { getReviewLabels, getReviewOriginalPageUrl, previewReview, type ReviewDraft, type ReviewEditLogEntry, type ReviewPreviewPage, type ReviewSource } from '../services/llmApi'

type ReviewModalProps = {
  open: boolean
  review: ReviewDraft
  documentName: string
  isSaving: boolean
  externalError: string | null
  onCancel: () => void
  onFinalize: (source: ReviewSource, approvedPages: Record<string, string>, editLog: ReviewEditLogEntry[], labelCode: string | undefined, displayName: string) => void
}

type PageTextState = { ocr: string; llm: string }
type TextRange = { start: number; end: number }
type HighlightRange = TextRange
type MarkdownPreviewBoundaryProps = { children: ReactNode; markdown: string; pageId: string }
type ReviewRenderBoundaryProps = { children: ReactNode; review: ReviewDraft; open: boolean }

class MarkdownPreviewBoundary extends Component<MarkdownPreviewBoundaryProps, { error: Error | null; lastMarkdown: string }> {
  state = { error: null as Error | null, lastMarkdown: this.props.markdown }

  static getDerivedStateFromProps(props: Readonly<MarkdownPreviewBoundaryProps>, state: { error: Error | null; lastMarkdown: string }) {
    return props.markdown !== state.lastMarkdown
      ? { error: null, lastMarkdown: props.markdown }
      : null
  }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Could not render LLM Markdown for ${this.props.pageId}`, error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return <div className="markdown-render-fallback" role="alert">
        <p>Không thể hiển thị định dạng của trang này. Nội dung LLM vẫn được giữ bên dưới.</p>
        <pre>{this.props.markdown}</pre>
      </div>
    }
    return this.props.children
  }
}

class ReviewRenderBoundary extends Component<ReviewRenderBoundaryProps, { error: Error | null }> {
  state = { error: null as Error | null }

  componentDidUpdate(previousProps: Readonly<ReviewRenderBoundaryProps>) {
    if (!previousProps.open && this.props.open && this.state.error) {
      this.setState({ error: null })
    }
  }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Could not render LLM review; showing the returned Markdown as text', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      if (!this.props.open) return null
      const pages = Array.isArray(this.props.review.markdown_pages) ? this.props.review.markdown_pages : []
      return <section className="review-render-fallback" role="alert">
        <h2>LLM đã hiệu đính xong, nhưng không thể dựng bản xem trước.</h2>
        <p>Nội dung LLM vẫn còn nguyên bên dưới; tải lại trang hoặc mở lại đối chiếu sau.</p>
        {pages.length ? pages.map(page => <article key={page.page_id}>
          <h3>{page.page_id.toUpperCase()}</h3>
          <pre>{page.llm_markdown ?? ''}</pre>
        </article>) : this.props.review.pages.map(page => <article key={page.page_id}>
          <h3>{page.page_id.toUpperCase()}</h3>
          <pre>{page.corrected_text ?? ''}</pre>
        </article>)}
      </section>
    }
    return this.props.children
  }
}

function createInitialPreview(review: ReviewDraft): ReviewPreviewPage[] {
  return review.markdown_pages.map((page) => ({
    ...page,
    ocr_manual_changes: [],
    llm_manual_changes: [],
  }))
}

function mergeRanges(ranges: TextRange[]): TextRange[] {
  const merged: TextRange[] = []
  for (const range of ranges.filter(r => r.end > r.start).sort((a, b) => a.start - b.start)) {
    const previous = merged[merged.length - 1]
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end)
    else merged.push({ ...range })
  }
  return merged
}

function position(text: string, start: number, end: number) {
  const point = (offset: number) => {
    const prefix = text.slice(0, offset).split('\n')
    return { line: prefix.length, column: Array.from(prefix[prefix.length - 1]).length + 1 }
  }
  const a = point(start), b = point(end)
  return { start_offset: start, end_offset: end, start_line: a.line, start_column: a.column, end_line: b.line, end_column: b.column }
}
function operation(before: string, after: string): 'insert' | 'delete' | 'replace' {
  return !before ? 'insert' : !after ? 'delete' : 'replace'
}
function describePosition(p?: ReturnType<typeof position>) {
  return p ? `Dòng ${p.start_line}, cột ${p.start_column} → dòng ${p.end_line}, cột ${p.end_column} (offset ${p.start_offset}–${p.end_offset})` : 'Không có dữ liệu vị trí'
}

function findSingleEdit(before: string, after: string): { start: number; end: number; inserted: string } {
  let start = 0
  while (start < before.length && start < after.length && before[start] === after[start]) start += 1
  let beforeEnd = before.length
  let afterEnd = after.length
  while (beforeEnd > start && afterEnd > start && before[beforeEnd - 1] === after[afterEnd - 1]) {
    beforeEnd -= 1
    afterEnd -= 1
  }
  return { start, end: beforeEnd, inserted: after.slice(start, afterEnd) }
}

function resolveMarkdownUrl(url: string, documentName: string): string {
  if (/^(https?:|data:|blob:|mailto:)/i.test(url)) return url
  return getOcrAssetUrl(documentName, url.replace(/^\.\//, ''))
}

function HighlightedEditor({ value, label, onChange, disabled = false }: {
  value: string; ranges: HighlightRange[]; label: string
  onChange: (value: string) => void; onScroll: () => void
  compact?: boolean; disabled?: boolean
}) {
  const input = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const element = input.current
    if (!element) return
    const column = element.closest('.review-column-scroll')
    const scrollTop = column?.scrollTop ?? 0
    element.style.height = '0px'
    element.style.height = `${Math.max(100, element.scrollHeight + 2)}px`
    if (column) column.scrollTop = scrollTop
  }, [value])
  return <textarea ref={input} className="review-editor-textarea" aria-label={label}
    value={value} disabled={disabled} onChange={event => onChange(event.target.value)}
    spellCheck={false} />
}

  function moveRanges(ranges: TextRange[], start: number, end: number, insertedLength: number): TextRange[] {
    const delta = insertedLength - (end - start)
    return ranges.map((range) => {
      if (range.end <= start) return range
      if (range.start >= end && start !== end) return { start: range.start + delta, end: range.end + delta }
      if (range.start >= start && start === end) return { start: range.start + delta, end: range.end + delta }
      if (range.start < end && range.end > start) {
        return { start: Math.min(range.start, start), end: Math.max(start + insertedLength, range.end + delta) }
      }
      return range
    })
  }


const PageEditor = memo(function PageEditor({ pageId, side, value, ranges, pendingFormula, updateText, onPending, onScroll }: {
  pageId: string; side: ReviewSource; value: string; ranges: TextRange[]; pendingFormula: string | null
  updateText: (pageId: string, side: ReviewSource, value: string, formulaIndex?: number) => boolean
  onPending: (id: string, pending: boolean, commit?: () => boolean) => void
  onScroll: (side: ReviewSource) => void
}) {
    const [fullMarkdown, setFullMarkdown] = useState(false)
    const formulas = useMemo(() => findFormulas(value), [value])
    const elements: ReactNode[] = []
    let cursor = 0
    function textEditor(start: number, end: number, key: string) {
      if (start === end && formulas.length) return
      elements.push(<HighlightedEditor key={key} value={value.slice(start, end)}
        compact={formulas.length > 0} disabled={pendingFormula !== null}
        ranges={ranges.filter((range) => range.end > start && range.start < end)
          .map((range) => ({ start: Math.max(0, range.start - start), end: Math.min(end, range.end) - start }))}
        label={`Sửa văn bản ${side.toUpperCase()} ${pageId} ${key}`}
        onChange={(text) => { updateText(pageId, side, value.slice(0, start) + text + value.slice(end)) }}
        onScroll={() => onScroll(side)} />)
    }
    formulas.forEach((formula, index) => {
      textEditor(cursor, formula.start, `text-${index}`)
      const id = `${pageId}-${side}-${index}`
      elements.push(<FormulaEditor key={`${id}-${formula.text}`} formula={formula}
        label={`Công thức ${index + 1} · ${pageId} · ${side.toUpperCase()}`}
        disabled={pendingFormula !== null && pendingFormula !== id}
        changed={ranges.some((range) => range.end > formula.start && range.start < formula.end)}
        onPending={(pending, commit) => onPending(id, pending, commit)}
        onApply={(body) => updateText(pageId, side, body, index)} />)
      cursor = formula.end
    })
    textEditor(cursor, value.length, 'text-last')
    return <>
      <label className="review-edit-mode"><input type="checkbox" checked={fullMarkdown} disabled={pendingFormula !== null}
        onChange={event => setFullMarkdown(event.target.checked)} /> Sửa toàn bộ Markdown (gồm cấu trúc, liên kết và công thức)</label>
      {fullMarkdown ? <HighlightedEditor value={value} ranges={ranges} label={`Sửa toàn bộ ${pageId}`}
        onChange={text => { updateText(pageId, side, text) }} onScroll={() => onScroll(side)} /> : elements}
    </>
  })

function OriginalPage({ reviewId, pageId }: { reviewId: string; pageId: string }) {
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  return failed ? <div role="alert">Không tải được trang gốc. <button type="button" onClick={() => { setFailed(false); setAttempt(value => value + 1) }}>Thử lại</button></div>
    : <img className="review-original-image" src={`${getReviewOriginalPageUrl(reviewId, pageId)}?attempt=${attempt}`} alt={`Tài liệu gốc ${pageId}`} onError={() => setFailed(true)} />
}

function ReviewModalContent({ open, review, documentName, isSaving, externalError, onCancel, onFinalize }: ReviewModalProps) {
  const [labelCode, setLabelCode] = useState(review.metadata.label_code)
  const [labels, setLabels] = useState<Record<string, string>>({ [review.metadata.label_code]: review.metadata.label_name })
  const [labelsError, setLabelsError] = useState<string | null>(null)
  const [labelsLoading, setLabelsLoading] = useState(false)
  const labelsRequest = useRef(0)
  const reloadLabels = useCallback(async () => {
    const request = ++labelsRequest.current
    setLabelsLoading(true)
    setLabelsError(null)
    try {
      const value = await getReviewLabels()
      if (!value || typeof value !== 'object' || Object.keys(value).length < 2) throw new Error('Empty labels')
      if (request === labelsRequest.current) {
        const names: Record<string, string> = {
          letter: 'Thư', document: 'Tài liệu', official_letter: 'Công văn',
          meeting_minutes: 'Biên bản', book: 'Sách', unclassified: 'Chưa phân loại',
        }
        const next = Object.fromEntries(Object.entries(value)
          .filter(([code]) => code !== '0')
          .map(([code, name]) => [code, names[name] ?? name]))
        if (review.metadata.label_code === '0') next['0'] = names.unclassified
        else if (!next[review.metadata.label_code]) next[review.metadata.label_code] = review.metadata.label_name
        setLabels(next)
      }
    } catch {
      if (request === labelsRequest.current) setLabelsError('Không tải được danh sách phân loại. Bấm Tải lại danh sách để thử lại.')
    } finally {
      if (request === labelsRequest.current) setLabelsLoading(false)
    }
  }, [review.metadata.label_code, review.metadata.label_name])
  useEffect(() => {
    if (open) void reloadLabels()
    return () => { labelsRequest.current += 1 }
  }, [open, reloadLabels])
  const classificationChanged = labelCode !== review.metadata.label_code
  const [pageTexts, setPageTexts] = useState<Record<string, PageTextState>>(() => Object.fromEntries(
    review.markdown_pages.map((page) => [page.page_id, { ocr: page.ocr_markdown, llm: page.llm_markdown }]),
  ))
  const pageTextsRef = useRef(pageTexts)
  const editLogRef = useRef<ReviewEditLogEntry[]>([])
  const auditGroup = useRef<{ key: string; source: string; target: string; logIndex: number } | null>(null)
  const pendingCommit = useRef<(() => boolean) | null>(null)
  const [previewPages, setPreviewPages] = useState<ReviewPreviewPage[]>(() => createInitialPreview(review))
  const [editLog, setEditLog] = useState<ReviewEditLogEntry[]>([])
  const [manualHighlights, setManualHighlights] = useState<Record<string, PageTextState & { ocrRanges: TextRange[]; llmRanges: TextRange[] }>>(() =>
    Object.fromEntries(review.markdown_pages.map((page) => [page.page_id, { ocr: page.ocr_markdown, llm: page.llm_markdown, ocrRanges: [], llmRanges: [] }])),
  )
  const llmLog = useMemo<ReviewEditLogEntry[]>(() => review.markdown_pages.flatMap(page => page.llm_changes.map(change => {
    const start = Array.from(page.ocr_markdown).slice(0, change.before_start ?? 0).join('').length
    const end = Array.from(page.ocr_markdown).slice(0, change.before_end ?? 0).join('').length
    const context = wordChange(page.ocr_markdown, page.llm_markdown, start, end, change.start, change.end)
    return { actor: 'llm', actor_name: `${review.provider} / ${review.model}`, content_type: 'text',
      page_id: page.page_id, source_side: 'llm', timestamp: '', before: context.before, after: context.after,
      mirrored_before: '', mirrored_after: '', operation: operation(change.before, change.after),
      position_basis: 'Markdown OCR trước sửa / Markdown LLM sau sửa',
      before_position: position(page.ocr_markdown, context.start, context.end),
      after_position: position(page.llm_markdown, context.afterStart, context.afterEnd),
      context_before: page.ocr_markdown.slice(Math.max(0, start - 40), end + 40),
      context_after: page.llm_markdown.slice(Math.max(0, change.start - 40), change.end + 40),
    }
  })), [review])
  const [showLog, setShowLog] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [saveName, setSaveName] = useState(documentName)
  const [saveTimestamp, setSaveTimestamp] = useState(new Date())
  const [saveNameError, setSaveNameError] = useState<string | null>(null)
  useEffect(() => {
    if (!saveDialogOpen || isSaving) return
    const timer = window.setInterval(() => setSaveTimestamp(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [saveDialogOpen, isSaving])
  const [pendingFormula, setPendingFormula] = useState<string | null>(null)
  const [isRefreshingPreview, setIsRefreshingPreview] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mirroredScroll = useRef(new WeakMap<HTMLElement, number>())

  const previewById = Object.fromEntries(previewPages.map((page) => [page.page_id, page]))
  const logByPage = (pageId: string, side: ReviewSource) => {
    const highlight = manualHighlights[pageId]
    return side === 'ocr' ? highlight.ocrRanges : highlight.llmRanges
  }

  function syncScroll(source: HTMLElement, target: HTMLElement | null) {
    if (!target) return
    const expected = mirroredScroll.current.get(source)
    mirroredScroll.current.delete(source)
    if (expected !== undefined && Math.abs(source.scrollTop - expected) < 1) return
    const sourceMax = source.scrollHeight - source.clientHeight
    if (sourceMax <= 0) return
    const targetMax = Math.max(0, target.scrollHeight - target.clientHeight)
    let next = source.scrollTop / sourceMax * targetMax
    const pages = Array.from(source.querySelectorAll<HTMLElement>('[data-page-id]'))
    const top = (element: HTMLElement, container: HTMLElement) => element.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
    const index = Math.max(0, pages.findLastIndex(page => top(page, source) <= source.scrollTop + 1))
    const page = pages[index]
    const targetPage = page && Array.from(target.querySelectorAll<HTMLElement>('[data-page-id]')).find(item => item.dataset.pageId === page.dataset.pageId)
    if (page && targetPage) {
      const pageTop = top(page, source)
      const end = pages[index + 1] ? top(pages[index + 1], source) : source.scrollHeight
      const targetPages = Array.from(target.querySelectorAll<HTMLElement>('[data-page-id]'))
      const targetIndex = targetPages.indexOf(targetPage)
      const targetTop = top(targetPage, target)
      const targetEnd = targetPages[targetIndex + 1] ? top(targetPages[targetIndex + 1], target) : target.scrollHeight
      next = targetTop + Math.max(0, Math.min(1, (source.scrollTop - pageTop) / Math.max(1, end - pageTop))) * (targetEnd - targetTop)
      if (source.scrollTop >= sourceMax - 1) next = targetMax
      next = Math.min(targetMax, next)
    }
    if (Math.abs(target.scrollTop - next) < 1) return
    target.scrollTop = next
    mirroredScroll.current.set(target, target.scrollTop)
  }

  const leftColumn = useRef<HTMLDivElement>(null)
  const rightColumn = useRef<HTMLDivElement>(null)

  const updateText = useCallback((pageId: string, side: ReviewSource, nextValue: string, formulaIndex?: number): boolean => {
    setError(null)
    const current = pageTextsRef.current[pageId]
    const sourceBefore = side === 'ocr' ? current.ocr : current.llm
    const targetBefore = side === 'ocr' ? current.llm : current.ocr
    if (formulaIndex !== undefined) {
      const formula = findFormulas(sourceBefore)[formulaIndex]
      if (!formula) return false
      nextValue = sourceBefore.slice(0, formula.start) + formula.delimiter + nextValue + formula.delimiter + sourceBefore.slice(formula.end)
    }
    if (sourceBefore === nextValue) return true
    const edit = findSingleEdit(sourceBefore, nextValue)
    // The original and OCR baseline are immutable. Human edits never need to
    // match a second version, including when overriding an LLM correction.
    const mirrorAfter = targetBefore
    const next = { ...current, [side]: nextValue }
    pageTextsRef.current = { ...pageTextsRef.current, [pageId]: next }
    setPageTexts(pageTextsRef.current)
    setManualHighlights((existing) => {
      const page = existing[pageId]
      const sourceRanges = side === 'ocr' ? page.ocrRanges : page.llmRanges
      const nextSourceRanges = moveRanges(sourceRanges, edit.start, edit.end, edit.inserted.length)
      nextSourceRanges.push({ start: edit.start, end: edit.start + edit.inserted.length })
      return { ...existing, [pageId]: side === 'ocr'
        ? { ...page, ocr: next.ocr, llm: next.llm, ocrRanges: mergeRanges(nextSourceRanges), llmRanges: page.llmRanges }
        : { ...page, ocr: next.ocr, llm: next.llm, ocrRanges: page.ocrRanges, llmRanges: mergeRanges(nextSourceRanges) } }
    })
    const groupKey = `${pageId}:${side}:${formulaIndex ?? 'text'}`
    if (auditGroup.current?.key !== groupKey) {
      auditGroup.current = { key: groupKey, source: sourceBefore, target: targetBefore, logIndex: editLogRef.current.length }
    }
    const group = auditGroup.current
    const auditEdit = findSingleEdit(group.source, nextValue)
    const context = wordChange(group.source, nextValue, auditEdit.start, auditEdit.end, auditEdit.start, auditEdit.start + auditEdit.inserted.length)
    const auditMirror = findSingleEdit(group.target, mirrorAfter)
    const priorLog = editLogRef.current.slice(0, group.logIndex)
    editLogRef.current = group.source === nextValue && group.target === mirrorAfter ? priorLog : [...priorLog, {
      actor: 'user',
      actor_name: 'Người dùng trong phiên duyệt',
      operation: operation(group.source.slice(auditEdit.start, auditEdit.end), auditEdit.inserted),
      position_basis: 'Markdown trang tại thời điểm chỉnh sửa; offset UTF-16, bắt đầu từ 0; dòng/cột từ 1; điểm cuối không bao gồm',
      before_position: position(group.source, context.start, context.end),
      after_position: position(nextValue, context.afterStart, context.afterEnd),
      mirrored_before_position: position(group.target, auditMirror.start, auditMirror.end),
      mirrored_after_position: position(mirrorAfter, auditMirror.start, auditMirror.start + auditMirror.inserted.length),
      context_before: group.source.slice(Math.max(0, auditEdit.start - 40), auditEdit.end + 40),
      context_after: nextValue.slice(Math.max(0, auditEdit.start - 40), auditEdit.start + auditEdit.inserted.length + 40),
      content_type: formulaIndex === undefined ? 'text' : 'formula',
      page_id: pageId,
      source_side: side,
      timestamp: new Date().toISOString(),
      before: context.before,
      after: context.after,
      mirrored_before: group.target.slice(auditMirror.start, auditMirror.end),
      mirrored_after: auditMirror.inserted,
    }]
    setEditLog(editLogRef.current)
    return true
  }, [])

  const onPending = useCallback((id: string, pending: boolean, commit?: () => boolean) => {
    pendingCommit.current = pending ? commit ?? null : null
    setPendingFormula(pending ? id : null)
  }, [])
  const editorScroll = useCallback((side: ReviewSource) => {
    const source = side === 'ocr' ? leftColumn.current : rightColumn.current
    const target = side === 'ocr' ? rightColumn.current : leftColumn.current
    if (source && target) syncScroll(source, target)
  }, [])
  function commitPendingFormula() {
    if (pendingCommit.current && !pendingCommit.current()) return false
    pendingCommit.current = null
    setPendingFormula(null)
    return true
  }

  async function toggleEdit() {
    if (!commitPendingFormula()) return
    if (editing) {
      setIsRefreshingPreview(true)
      setError(null)
      try {
        const pages = Object.fromEntries(Object.entries(pageTextsRef.current).map(([pageId, value]) => [pageId, {
          ocr_text: value.ocr,
          llm_text: value.llm,
        }]))
        setPreviewPages(await previewReview(review.review_id, pages))
        setEditing(false)
      } catch (previewError) {
        setError(previewError instanceof Error ? previewError.message : 'Không tạo được bản xem trước Markdown.')
      } finally {
        setIsRefreshingPreview(false)
      }
    } else {
      setEditing(true)
    }
  }

  function openSaveDialog() {
    if (!commitPendingFormula()) return
    setSaveName(documentName)
    setSaveTimestamp(new Date())
    setSaveNameError(null)
    setSaveDialogOpen(true)
  }

  function confirmSave() {
    const name = saveName.trim()
    if (!name || name.length > 200) {
      setSaveNameError('Nhập tên lưu từ 1 đến 200 ký tự.')
      return
    }
    const approvedPages = Object.fromEntries(
      Object.entries(pageTextsRef.current).map(([pageId, value]) => [pageId, value.llm]),
    )
    onFinalize('llm', approvedPages, [...llmLog, ...editLogRef.current], labelCode, name)
  }

  return (
    <div className="review-modal-backdrop" role="presentation" style={{ display: open ? 'flex' : 'none' }} aria-hidden={!open}>
      <section className="review-modal" role="dialog" aria-modal="true" aria-labelledby="review-title">
        <header className="review-modal-header">
          <div>
            <span className="eyebrow">KIỂM TRA CUỐI · {review.provider.toUpperCase()} / {review.model}</span>
            <h2 id="review-title">Đối chiếu tài liệu gốc và nội dung đã sửa</h2>
            <p>{review.document_name} · {review.page_count} trang · {labels[labelCode] || labelCode}</p>
          </div>
        </header>

        <div className="review-legend">
          <span><i className="review-legend-llm" /> LLM đã sửa</span>
          <span><i className="review-legend-manual" /> Người dùng đã sửa</span>
          {editLog.length > 0 && <span>{editLog.length} thay đổi đã ghi log</span>}
        </div>

        <div className="review-audit">
          <button type="button" onClick={() => setShowLog(!showLog)}>{showLog ? 'Ẩn' : 'Xem'} lịch sử chỉnh sửa ({editLog.length} người dùng · {llmLog.length} LLM)</button>
          {showLog && <div style={{ maxHeight: 220, overflow: 'auto' }}>
            {classificationChanged && <p><strong>Người dùng · Sửa phân loại toàn tài liệu:</strong> {review.metadata.label_name} ({review.metadata.label_code}) → {labels[labelCode]} ({labelCode}). Sẽ ghi log khi Save.</p>}
            <p>Dòng/cột tính từ 1; offset UTF-16 tính từ 0, điểm cuối không bao gồm. Vị trí thuộc bản văn tại thời điểm sửa.</p>
            {[...editLog].reverse().concat(llmLog).map((entry, index) => <details key={index}>
              <summary><strong>{entry.actor === 'llm' ? 'LLM' : 'Người dùng'}</strong> · {entry.page_id} · {entry.operation === 'insert' ? 'Thêm' : entry.operation === 'delete' ? 'Xóa' : 'Thay thế'} {entry.content_type === 'formula' ? 'công thức' : 'văn bản'} · dòng {entry.before_position?.start_line ?? '?'}, cột {entry.before_position?.start_column ?? '?'} · {entry.timestamp ? new Date(entry.timestamp).toLocaleString('vi-VN') : 'LLM xử lý trước phiên duyệt (không có thời gian chi tiết)'}</summary>
              <div>Người/model: {entry.actor_name} · Bên thao tác: {entry.source_side.toUpperCase()}</div>
              <div>Cơ sở vị trí: {entry.position_basis}</div>
              <div>Trước: {describePosition(entry.before_position)}</div><pre>{entry.before || '(trống)'}</pre>
              <div>Sau: {describePosition(entry.after_position)}</div><pre>{entry.after || '(đã xóa)'}</pre>
              <div>Ngữ cảnh trước:</div><pre>{entry.context_before}</pre>
              <div>Ngữ cảnh sau:</div><pre>{entry.context_after}</pre>

            </details>)}
          </div>}
        </div>
        <div className="review-columns">
          <div className="review-column">
            <div className="review-column-heading">Tài liệu gốc</div>
            <div className="review-column-scroll" ref={leftColumn} onScroll={event => syncScroll(event.currentTarget, rightColumn.current)}>
              {review.pages.map(page => <article className="review-page review-source-page" data-page-id={page.page_id} key={page.page_id}>
                <div className="review-page-label">{page.page_id.toUpperCase()}</div>
                <OriginalPage reviewId={review.review_id} pageId={page.page_id} />
              </article>)}
            </div>
          </div>
          <div className="review-column">
            <div className="review-column-heading">Bản cuối · LLM đề xuất, người dùng quyết định</div>
            <div className="review-column-scroll" ref={rightColumn} onScroll={event => syncScroll(event.currentTarget, leftColumn.current)}>
              {review.pages.map((page) => {
                const preview = previewById[page.page_id]
                return <article className="review-page" data-page-id={page.page_id} key={page.page_id}>
                  <div className="review-page-label">{page.page_id.toUpperCase()}</div>
                  {editing ? (
                    <PageEditor pageId={page.page_id} side="llm" value={pageTexts[page.page_id].llm} ranges={logByPage(page.page_id, 'llm')} pendingFormula={pendingFormula} updateText={updateText} onPending={onPending} onScroll={editorScroll} />
                  ) : <MarkdownPreviewBoundary key={page.page_id}
                    pageId={page.page_id} markdown={preview?.llm_markdown ?? ''}>
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeSanitize, rehypeHighlights(preview?.llm_changes ?? [], preview?.llm_manual_changes ?? []), rehypeKatex]}
                      urlTransform={(url) => resolveMarkdownUrl(url, documentName)}>{preview?.llm_markdown ?? ''}</ReactMarkdown>
                  </MarkdownPreviewBoundary>}
                </article>
              })}
            </div>
          </div>
        </div>

        <div className="review-metadata">
          <strong>Thông tin trích xuất</strong>
          <label>Phân loại: <select aria-label="Phân loại tài liệu" onFocus={() => { if (Object.keys(labels).length < 2 && !labelsLoading) void reloadLabels() }} value={labelCode} disabled={isSaving || isRefreshingPreview} onChange={event => setLabelCode(event.target.value)}>
            {Object.entries(labels).map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}
          </select></label>
          {(labelsError || Object.keys(labels).length < 2) && <button type="button" disabled={labelsLoading} onClick={() => void reloadLabels()}>{labelsLoading ? 'Đang tải phân loại…' : 'Tải lại danh sách'}</button>}
          {labelsError && <span role="alert">{labelsError}</span>}
          <span>Nơi gửi: {review.metadata.sender ?? '—'}</span>
          <span>Nơi nhận: {review.metadata.recipient ?? '—'}</span>
          <span>Ngày: {review.metadata.date_time ?? '—'}</span>
          <span>Loại: {classificationChanged ? labels[labelCode] : review.metadata.document_type}</span>
        </div>
        {(error || externalError) && <p className="review-error" role="alert">{error ?? externalError}</p>}
        {pendingFormula !== null && <p className="review-progress" role="status">Bấm Save hoặc Xem trước để áp dụng công thức vào bản cuối.</p>}
        {isRefreshingPreview && <p className="review-progress" role="status">Đang cập nhật bản xem trước…</p>}
        <footer className="review-modal-actions">
          <button type="button" className="review-save-llm" disabled={isSaving || isRefreshingPreview} onClick={openSaveDialog}>Save</button>
          <button type="button" className="review-edit" disabled={isSaving || isRefreshingPreview} onClick={() => void toggleEdit()}>
            {editing ? 'Xem trước' : 'Edit'}
          </button>
          <button type="button" className="review-cancel" disabled={isSaving} onClick={onCancel}>Cancel</button>
        </footer>
        {isSaving && <p className="review-progress" role="status">Đang lưu tài liệu cuối…</p>}
        {saveDialogOpen && <div className="save-confirm-backdrop">
          <section className="save-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="save-confirm-title">
            <h3 id="save-confirm-title">Lưu tài liệu</h3>
            <label htmlFor="saved-document-name">Tên lưu</label>
            <input id="saved-document-name" autoFocus maxLength={200} value={saveName}
              disabled={isSaving} onChange={event => { setSaveName(event.target.value); setSaveNameError(null) }} />
            <p>Ngày giờ lưu: {saveTimestamp.toLocaleString('vi-VN')}</p>
            {saveNameError && <p className="save-name-error" role="alert">{saveNameError}</p>}
            {(error || externalError) && <p className="save-name-error" role="alert">{error ?? externalError}</p>}
            <div className="save-confirm-actions">
              <button type="button" disabled={isSaving} onClick={() => setSaveDialogOpen(false)}>Hủy</button>
              <button type="button" disabled={isSaving} onClick={confirmSave}>{isSaving ? 'Đang lưu…' : 'Save'}</button>
            </div>
          </section>
        </div>}
      </section>
    </div>
  )
}

export function ReviewModal(props: ReviewModalProps) {
  return <ReviewRenderBoundary key={props.review.review_id} review={props.review} open={props.open}>
    <ReviewModalContent {...props} />
  </ReviewRenderBoundary>
}
