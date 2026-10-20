import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getOcrAssetUrl, type OcrPage } from '../services/ocrApi'
import type { UploadStatus } from './UploadControl'

const tabs = [
  { id: 'original', label: 'Văn bản gốc', icon: '▧' },
  { id: 'digitized', label: 'Văn bản số hóa', icon: '≡' },
] as const

type DocumentViewerProps = {
  file: File | null
  status: UploadStatus
  pages: OcrPage[]
  totalPages: number | null
  documentName: string | null
  error: string | null
}

export function DocumentViewer({ file, status, pages, totalPages, documentName, error }: DocumentViewerProps) {
  const [manualTab, setManualTab] = useState<{ file: File | null; tab: (typeof tabs)[number]['id'] } | null>(null)
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null)
  const hasDigitizedPages = pages.length > 0 && (status === 'completed' || status === 'failed')
  const activeTab = manualTab?.file === file ? manualTab.tab : hasDigitizedPages ? 'digitized' : 'original'
  const previewUrl = file && preview?.file === file ? preview.url : null

  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file)
    const frame = window.requestAnimationFrame(() => setPreview({ file, url }))
    return () => {
      window.cancelAnimationFrame(frame)
      URL.revokeObjectURL(url)
    }
  }, [file])

  function resolveMarkdownUrl(url: string): string {
    if (/^(https?:|data:|blob:|mailto:)/i.test(url) || !documentName) return url
    return getOcrAssetUrl(documentName, url.replace(/^\.\//, ''))
  }

  const isBusy = status === 'submitting' || status === 'queued' || status === 'running'
  const isPdf = Boolean(file && (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')))

  return (
    <section className="document-panel panel">
      <div className="document-topline">
        <div className="document-heading"><span className="eyebrow">THƯ VIỆN TÀI LIỆU</span><h1>{file?.name ?? 'Nội dung tài liệu'}</h1></div>
        <button className="more-button" aria-label="Tùy chọn tài liệu" disabled>···</button>
      </div>
      <div className="document-toolbar">
        <div className="document-tabs" role="tablist" aria-label="Loại văn bản">
          {tabs.map((tab) => <button key={tab.id} role="tab" aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? 'document-tab active' : 'document-tab'} onClick={() => setManualTab({ file, tab: tab.id })}>
            <span aria-hidden="true">{tab.icon}</span>{tab.label}
          </button>)}
        </div>
        <div className="viewer-tools"><span>{pages.length ? `${pages.length} trang` : '— trang'}</span><span className="toolbar-divider" /><button aria-label="Toàn màn hình" disabled>⛶</button></div>
      </div>
      <div className={`document-canvas ${pages.length && activeTab === 'digitized' ? 'has-pages' : ''}`}>
        {activeTab === 'original' && file && previewUrl ? (
          isPdf ? <iframe className="source-preview" src={previewUrl} title={`Bản gốc ${file.name}`} />
            : <div className="image-preview-wrap"><img className="source-image-preview" src={previewUrl} alt={`Bản gốc ${file.name}`} /></div>
        ) : activeTab === 'digitized' && pages.length ? (
          <div className="markdown-document">
            {status === 'failed' && <div className="partial-warning" role="status">OCR hoàn tất {pages.length}/{totalPages ?? '—'} trang trước khi dừng. {error}</div>}
            {pages.map((page) => <article className="markdown-page" key={page.page_number}>
              <div className="markdown-page-label">TRANG {page.page_number}</div>
              <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={resolveMarkdownUrl}>{page.markdown}</ReactMarkdown>
            </article>)}
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
        {activeTab === 'original' && !file && <div className="page-indicator"><span className="page-dot" />Trang — / —</div>}
      </div>
    </section>
  )
}
