import { useEffect, useRef, useState } from 'react'
import { ChatPanel } from '../components/ChatPanel'
import { DocumentViewer } from '../components/DocumentViewer'
import type { OcrPage } from '../services/ocrApi'
import { parseAICommand } from '../services/searchCommands'
import { searchLibraryAI, type LibrarySearchHit } from '../services/llmApi'

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') + '/api/library'
type Item = { document_id: string; name: string; label_name: string; page_count: number; created_at: string }
type Document = Item & { pages: OcrPage[] }
type GlobalMessage = { role: 'user' | 'assistant'; content: string; results?: LibrarySearchHit[]; total?: number; page?: number; pageSize?: number; question?: string }

export function DashboardPage({ active = true, selectedDocumentId = null, onDocumentOpened }: {
  active?: boolean
  selectedDocumentId?: string | null
  onDocumentOpened?: (documentId: string) => void
}) {
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const searchSection = useRef<HTMLElement>(null)
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [document, setDocument] = useState<Document | null>(null)
  const [documentError, setDocumentError] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)
  const [globalMessages, setGlobalMessages] = useState<GlobalMessage[]>([])
  const [globalBusy, setGlobalBusy] = useState(false)
  const [globalError, setGlobalError] = useState<string | null>(null)
  const [targetPage, setTargetPage] = useState<number | undefined>()
  async function askLibrary(question: string, page = 0, includeQuestion = page === 0) {
    if (globalBusy) return
    if (includeQuestion) setGlobalMessages(messages => [...messages, { role: 'user', content: question }])
    setGlobalBusy(true); setGlobalError(null)
    try {
      const result = await searchLibraryAI(question, page)
      setGlobalMessages(messages => [...messages, { role: 'assistant', content: result.answer, results: result.results,
        total: result.total, page: result.page, pageSize: result.page_size, question }])
    } catch (cause) {
      setGlobalError(cause instanceof Error ? cause.message : 'Không thể tìm kiếm thư viện.')
    } finally { setGlobalBusy(false) }
  }
  function openCitation(hit: LibrarySearchHit) {
    setTargetPage(hit.page_number)
    setSelected(hit.document_id)
    onDocumentOpened?.(hit.document_id)
    setSearchOpen(false)
  }
  useEffect(() => {
    if (selectedDocumentId) setSelected(selectedDocumentId)
  }, [selectedDocumentId])
  useEffect(() => {
    if (!active || parseAICommand(query)) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${base}?q=${encodeURIComponent(query)}&offset=${offset}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Không tải được thư viện tài liệu.')
        const data = await response.json()
        if (!controller.signal.aborted) { setItems(data.items); setTotal(data.total) }
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Lỗi tìm kiếm') }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }, 300)
    return () => { clearTimeout(timer); controller.abort() }
  }, [query, offset, active])
  function submitSearch(event: React.FormEvent) {
    event.preventDefault()
    const aiQuery = parseAICommand(query)
    if (aiQuery) { void askLibrary(aiQuery); setSearchOpen(false) }
  }
  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !searchSection.current?.contains(event.target)) setSearchOpen(false)
    }
    window.document.addEventListener('pointerdown', closeOutside)
    return () => window.document.removeEventListener('pointerdown', closeOutside)
  }, [])
  useEffect(() => {
    if (!selected) return
    const controller = new AbortController()
    setOpening(true); setDocument(null); setDocumentError(null)
    fetch(`${base}/${encodeURIComponent(selected)}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error('Không mở được tài liệu.'); return response.json() })
      .then(data => { if (!controller.signal.aborted) setDocument(data) })
      .catch(e => { if (!controller.signal.aborted) setDocumentError(String(e.message)) })
      .finally(() => { if (!controller.signal.aborted) setOpening(false) })
    return () => controller.abort()
  }, [selected])
  return <main className={`dashboard-layout${document ? ' dashboard-document-open' : ''}`}>
    <aside className="left-column">
      <section className="search-section" ref={searchSection}>
        <form className="search-box" onSubmit={submitSearch}><span className="search-icon" aria-hidden="true" />
          <input type="search" placeholder="Tên, danh mục… hoặc /AI: câu hỏi" aria-label="Tìm kiếm tài liệu" value={query}
            onFocus={() => setSearchOpen(true)} onChange={e => { setQuery(e.target.value); setOffset(0); setSearchOpen(true); if (parseAICommand(e.target.value)) setLoading(false) }} />
          {parseAICommand(query) && <button type="submit" aria-label="Tìm bằng Trợ Lý">AI</button>}
        </form>
        {searchOpen && <div className="library-popover" role="region" aria-label="Kết quả tài liệu">
          {parseAICommand(query) ? <p>Nhấn Enter hoặc AI để tìm trong nội dung bằng Trợ Lý.</p> : loading ? <p role="status">Đang tìm kiếm…</p> : error ? <p role="alert">{error}</p> : <>
            {!items.length && <p>{query ? 'Không tìm thấy tài liệu phù hợp.' : 'Chưa có tài liệu đã lưu. Hoàn tất duyệt và bấm Save để thêm vào thư viện.'}</p>}
            <div className="library-results">{items.map(item => <button type="button" key={item.document_id}
              className={selected === item.document_id ? 'library-result active' : 'library-result'}
              onClick={() => { setSelected(item.document_id); onDocumentOpened?.(item.document_id); setSearchOpen(false) }}>
              <strong>{item.name}</strong><span>{item.label_name} · {item.page_count} trang</span>
              <span>{new Date(item.created_at).toLocaleString('vi-VN')}</span>
            </button>)}</div>
            {total > 20 && <div className="library-pagination">
              <button disabled={offset === 0} onClick={() => setOffset(n => Math.max(0, n - 20))}>Trước</button>
              <span>{offset + 1}–{Math.min(offset + 20, total)} / {total}</span>
              <button disabled={offset + 20 >= total} onClick={() => setOffset(n => n + 20)}>Sau</button>
            </div>}
          </>}
        </div>}
      </section>
      <ChatPanel document={document?.document_id === selected && !opening && active
        ? { id: document.document_id, name: document.name } : null}
        globalMessages={globalMessages} globalBusy={globalBusy} globalError={globalError}
        onGlobalSearch={askLibrary} onGlobalPage={(question, page) => askLibrary(question, page, false)} onOpenCitation={openCitation} />
    </aside>
    <DocumentViewer key={selected} file={null} status={opening ? 'running' : documentError ? 'failed' : document ? 'completed' : 'idle'}
      pages={document?.pages ?? []} totalPages={document?.page_count ?? null} documentName={null} error={documentError}
      showViewTabs={false}
      storedDocument={document ? { documentId: document.document_id, name: document.name,
        originalUrl: `${base}/${document.document_id}/original`, assetUrl: `${base}/${document.document_id}/assets/` } : undefined}
      targetPage={targetPage} />
  </main>
}
