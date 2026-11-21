import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import { rehypeHighlights } from '../services/reviewHighlights'
import type { MarkdownChange } from '../services/llmApi'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'katex/dist/katex.min.css'
import { getOcrAssetUrl, type OcrPage } from '../services/ocrApi'
import type { UploadStatus } from './UploadControl'

const tabs = [
  { id: 'original', label: 'Văn bản gốc', icon: '▧' },
  { id: 'digitized', label: 'Văn bản số hóa', icon: '≡' },
] as const
const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

type DocumentViewerProps = {
  storedDocument?: { documentId: string; name: string; originalUrl: string; assetUrl: string }
  file: File | null
  status: UploadStatus
  pages: OcrPage[]
  totalPages: number | null
  documentName: string | null
  error: string | null
  showViewTabs?: boolean
  targetPage?: number
}

export function DocumentViewer({ file, status, pages, totalPages, documentName, error, storedDocument, showViewTabs = true, targetPage }: DocumentViewerProps) {
  const [manualTab, setManualTab] = useState<{ file: File | null; tab: (typeof tabs)[number]['id'] } | null>(null)
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null)
  const [showHighlights, setShowHighlights] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const optionsRef = useRef<HTMLDivElement>(null)
  const hasDigitizedPages = pages.length > 0 && (status === 'completed' || status === 'failed')
  const activeTab = manualTab?.file === file ? manualTab.tab : !showViewTabs || storedDocument || hasDigitizedPages ? 'digitized' : 'original'
  const previewUrl = storedDocument?.originalUrl ?? (file && preview?.file === file ? preview.url : null)

  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file)
    const frame = window.requestAnimationFrame(() => setPreview({ file, url }))
    return () => {
      window.cancelAnimationFrame(frame)
      URL.revokeObjectURL(url)
    }
  }, [file])

  useEffect(() => {
    if (targetPage === undefined || !pages.some(page => page.page_number === targetPage)) return
    const frame = window.requestAnimationFrame(() => {
      window.document.querySelector<HTMLElement>(`.markdown-page[data-page-number="${targetPage}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [targetPage, pages])

  useEffect(() => {
    if (!menuOpen) return
    function closeMenu(event: PointerEvent) {
      if (event.target instanceof Node && !optionsRef.current?.contains(event.target)) setMenuOpen(false)
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('pointerdown', closeMenu)
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('pointerdown', closeMenu)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [menuOpen])

  async function downloadContent() {
    if (!storedDocument || downloading) return
    setDownloading(true)
    setDownloadError(null)
    try {
      const response = await fetch(`${apiBase}/api/library/${encodeURIComponent(storedDocument.documentId)}/download`)
      if (!response.ok) {
        let message = 'Không thể tạo file ZIP.'
        try {
          const data = await response.json()
          if (typeof data.detail === 'string') message = data.detail
        } catch { /* The API may return a non-JSON error page. */ }
        throw new Error(message)
      }
      const archive = await response.blob()
      const url = URL.createObjectURL(archive)
      const link = window.document.createElement('a')
      const filename = storedDocument.name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').trim() || 'document'
      link.href = url
      link.download = `${filename}.zip`
      window.document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMenuOpen(false)
    } catch (cause) {
      setDownloadError(cause instanceof Error ? cause.message : 'Không thể tải file ZIP.')
    } finally {
      setDownloading(false)
    }
  }

  function resolveMarkdownUrl(url: string): string {
    if (/^(https?:|data:|blob:|mailto:)/i.test(url)) return url
    if (storedDocument) return storedDocument.assetUrl + url.replace(/^\.\//, '').split('/').map(encodeURIComponent).join('/')
    if (!documentName) return url
    return getOcrAssetUrl(documentName, url.replace(/^\.\//, ''))
  }

  const isBusy = status === 'submitting' || status === 'queued' || status === 'running'
  const isPdf = Boolean(storedDocument || file && (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')))

  return (
    <section className={`document-panel panel${storedDocument ? ' stored-document-panel' : ''}`}>
      <div className="document-topline">
        <div className="document-heading"><span className="eyebrow">THƯ VIỆN TÀI LIỆU</span><h1>{storedDocument?.name ?? file?.name ?? 'Nội dung tài liệu'}</h1></div>
        <div className="document-options" ref={optionsRef}>
          <button type="button" className="more-button" aria-label="Tùy chọn tài liệu" aria-haspopup="menu"
            aria-expanded={menuOpen} disabled={!storedDocument} onClick={() => {
              setDownloadError(null)
              setMenuOpen(open => !open)
            }}>···</button>
          {menuOpen && storedDocument && <div className="document-options-menu" role="menu">
            <button type="button" role="menuitem" onClick={() => {
              setManualTab({ file, tab: activeTab === 'original' ? 'digitized' : 'original' })
              setMenuOpen(false)
            }}>{activeTab === 'original' ? 'Xem văn bản số hóa' : 'Xem văn bản gốc'}</button>
            <button type="button" role="menuitem" disabled={downloading} onClick={() => void downloadContent()}>
              {downloading ? 'Đang tạo file ZIP…' : 'Tải xuống nội dung'}
            </button>
            {downloadError && <p className="document-options-error" role="alert">{downloadError}</p>}
          </div>}
        </div>
      </div>
      <div className="document-toolbar">
        {showViewTabs && <div className="document-tabs" role="tablist" aria-label="Loại văn bản">
          {tabs.map((tab) => <button key={tab.id} role="tab" aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? 'document-tab active' : 'document-tab'} onClick={() => setManualTab({ file, tab: tab.id })}>
            <span aria-hidden="true">{tab.icon}</span>{tab.label}
          </button>)}
        </div>}
        <div className="viewer-tools"><span>{pages.length ? `${pages.length} trang` : '— trang'}</span>{storedDocument && pages.some(page => (page as OcrPage & { llm_changes?: MarkdownChange[]; manual_changes?: MarkdownChange[] }).llm_changes?.length || (page as OcrPage & { manual_changes?: MarkdownChange[] }).manual_changes?.length) && <button type="button" className={`highlight-toggle ${showHighlights ? 'is-on' : 'is-off'}`} aria-pressed={showHighlights} onClick={() => setShowHighlights(value => !value)}>{showHighlights ? 'Tắt highlight' : 'Bật highlight'}</button>}<span className="toolbar-divider" /><button aria-label="Toàn màn hình" disabled>⛶</button></div>
      </div>
      <div className={`document-canvas ${pages.length && activeTab === 'digitized' ? 'has-pages' : ''}${storedDocument ? ' stored-document-canvas' : ''}`}>
        {activeTab === 'original' && previewUrl ? (
          isPdf ? <iframe className="source-preview" src={previewUrl} title={`Bản gốc ${storedDocument?.name ?? file?.name}`} />
            : <div className="image-preview-wrap"><img className="source-image-preview" src={previewUrl} alt={`Bản gốc ${storedDocument?.name ?? file?.name}`} /></div>
        ) : activeTab === 'digitized' && pages.length ? (
          <div className="markdown-document">
            {status === 'failed' && <div className="partial-warning" role="status">OCR hoàn tất {pages.length}/{totalPages ?? '—'} trang trước khi dừng. {error}</div>}
            {pages.map((page) => {
              const marked = page as OcrPage & { llm_changes?: MarkdownChange[]; manual_changes?: MarkdownChange[] }
              return <article className="markdown-page" data-page-number={page.page_number} key={page.page_number}>
                <div className="markdown-page-label">TRANG {page.page_number}</div>
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeSanitize, ...(showHighlights && storedDocument ? [rehypeHighlights(marked.llm_changes ?? [], marked.manual_changes ?? [])] : []), rehypeKatex]} urlTransform={resolveMarkdownUrl}>{page.markdown}</ReactMarkdown>
              </article>
            })}
          </div>
        ) : isBusy ? (
          <div className="viewer-message"><span className="viewer-spinner" /><h2>Đang nhận dạng tài liệu</h2><p>Các trang đã hoàn tất sẽ xuất hiện tại đây khi OCR xong.</p></div>
        ) : status === 'failed' ? (
          <div className="viewer-message error"><div className="viewer-error-icon">!</div><h2>Chưa thể đọc tài liệu</h2><p>{error}</p></div>
        ) : (
          <div className="empty-document">
            <div className="document-illustration" aria-hidden="true"><div className="paper-shadow" /><div className="paper-sheet"><span /><span /><span /><i /><span /></div><div className="magnifier"><b /></div></div>
            <h2>Chưa có tài liệu được chọn</h2>
            <p>Chọn một tài liệu để xem {activeTab === 'original' ? 'bản gốc' : 'nội dung đã số hóa'} tại đây.</p>
            <span className="canvas-hint">Tài liệu của bạn sẽ hiển thị tại đây</span>
          </div>
        )}
        {activeTab === 'original' && !file && !storedDocument && <div className="page-indicator"><span className="page-dot" />Trang — / —</div>}
      </div>
    </section>
  )
}
