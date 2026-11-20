import { useEffect, useMemo, useState } from 'react'

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const libraryUrl = `${apiBase}/api/library`

type LibraryItem = {
  document_id: string
  name: string
  label_name: string
  page_count: number
  created_at: string
}

type Category = { value: string; label: string }

const categoryNames: Record<string, string> = {
  letter: 'Thư', document: 'Tài liệu', official_letter: 'Công văn',
  meeting_minutes: 'Biên bản', book: 'Sách',
}
const allowedCategories = ['letter', 'document', 'official_letter', 'meeting_minutes', 'book']
const legacyCategory: Record<string, string> = {
  email: 'letter', invitation: 'letter',
  notice: 'official_letter', announcement: 'official_letter', memo: 'official_letter',
  textbook: 'book', newspaper: 'book', magazine: 'book',
}

function readableCategory(value: string): string {
  const category = categoryNames[value] ? value : legacyCategory[value] ?? 'document'
  return categoryNames[category]
}

const categories: Category[] = allowedCategories.map(value => ({ value, label: readableCategory(value) }))

function CategoryIcon({ category }: { category: string }) {
  const isLetter = ['letter', 'email', 'invitation', 'official_letter'].includes(category)
  const isReport = ['report', 'research_paper', 'thesis', 'essay'].includes(category)
  return <svg className="library-category-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    {isLetter ? <>
      <rect x="3.5" y="5" width="17" height="14" rx="3" />
      <path d="m5 7 7 5 7-5" />
    </> : isReport ? <>
      <path d="M6 3.75h8l4 4v12.5H6a2 2 0 0 1-2-2v-12.5a2 2 0 0 1 2-2Z" />
      <path d="M14 4v4h4M8 12h7M8 15.5h7" />
    </> : <>
      <path d="M3.5 7.5h7l2 2h8v8.75a2.25 2.25 0 0 1-2.25 2.25h-12.5a2.25 2.25 0 0 1-2.25-2.25Z" />
      <path d="M3.5 8V5.75A2.25 2.25 0 0 1 5.75 3.5h4L12 5.75h4" />
    </>}
  </svg>
}

export function LibraryPage({ active = true, onSelectDocument }: {
  active?: boolean
  onSelectDocument: (documentId: string) => void
}) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [categoryOpen, setCategoryOpen] = useState(false)
  const [items, setItems] = useState<LibraryItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    const timer = window.setTimeout(async () => {
      const params = new URLSearchParams({ q: query, offset: String(offset), limit: '20' })
      if (category) params.set('label_name', category)
      try {
        const response = await fetch(`${libraryUrl}?${params}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Không tải được danh sách tài liệu.')
        const data = await response.json() as { items: LibraryItem[]; total: number }
        if (!controller.signal.aborted) {
          setItems(data.items)
          setTotal(data.total)
        }
      } catch (requestError) {
        if (!controller.signal.aborted) setError(requestError instanceof Error ? requestError.message : 'Đã xảy ra lỗi.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, 220)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, category, offset, refresh, active])

  const selectedCategory = useMemo(() => categories.find(item => item.value === category), [categories, category])

  function chooseCategory(value: string) {
    setCategory(value)
    setOffset(0)
    setCategoryOpen(false)
  }

  return <main className="library-page">
    <div className="library-page-heading">
      <div>
        <span className="eyebrow">KHO LƯU TRỮ</span>
        <h1>Library</h1>
        <p>Tất cả tài liệu đã được lưu trong hệ thống.</p>
      </div>
      <div className="library-total"><strong>{total}</strong><span>tài liệu</span></div>
    </div>

    <section className="library-browser" aria-label="Thư viện tài liệu">
      <div className="library-browser-toolbar">
        <label className="library-page-search">
          <span className="search-icon" aria-hidden="true" />
          <input type="search" value={query} placeholder="Tìm theo tên hoặc nội dung…" aria-label="Tìm tài liệu trong Library"
            onChange={event => { setQuery(event.target.value); setOffset(0) }} />
        </label>
        <div className="library-category-picker">
          <button type="button" className={`library-category-trigger${categoryOpen ? ' open' : ''}`}
            aria-haspopup="listbox" aria-expanded={categoryOpen} onClick={() => setCategoryOpen(open => !open)}>
            <CategoryIcon category={category || 'all'} />
            <span>{selectedCategory?.label ?? 'Tất cả danh mục'}</span>
            <span className="category-chevron" aria-hidden="true">⌄</span>
          </button>
          {categoryOpen && <div className="library-category-menu" role="listbox" aria-label="Chọn danh mục">
            <button type="button" role="option" aria-selected={!category} className={!category ? 'selected' : ''} onClick={() => chooseCategory('')}>
              <CategoryIcon category="all" /><span>Tất cả danh mục</span>
            </button>
            {categories.map(item => <button type="button" role="option" aria-selected={category === item.value}
              className={category === item.value ? 'selected' : ''} key={item.value} onClick={() => chooseCategory(item.value)}>
              <CategoryIcon category={item.value} /><span>{item.label}</span>
            </button>)}
          </div>}
        </div>
        <button type="button" className="library-page-refresh" onClick={() => setRefresh(value => value + 1)}>
          <span aria-hidden="true">↻</span> Làm mới
        </button>
      </div>

      {loading ? <div className="library-page-state" role="status"><span className="viewer-spinner" />Đang tải tài liệu…</div>
        : error ? <div className="library-page-state library-page-error" role="alert"><p>{error}</p>
          <button type="button" onClick={() => setRefresh(value => value + 1)}>Thử lại</button></div>
          : !items.length ? <div className="library-page-state library-page-empty">
            <div className="library-empty-icon"><CategoryIcon category={category || 'all'} /></div>
            <h2>{category ? `Chưa có tài liệu thuộc “${selectedCategory?.label ?? readableCategory(category)}”` : 'Chưa có tài liệu đã lưu'}</h2>
            <p>{query ? 'Thử từ khóa khác hoặc chọn danh mục khác.' : 'Tài liệu đã hoàn tất duyệt sẽ xuất hiện tại đây.'}</p>
          </div>
          : <>
            <div className="library-card-grid">{items.map(item => <button type="button" className="library-document-card" key={item.document_id}
              onClick={() => onSelectDocument(item.document_id)}>
              <span className="library-card-icon"><CategoryIcon category={item.label_name} /></span>
              <span className="library-card-label">{readableCategory(item.label_name)}</span>
              <strong>{item.name}</strong>
              <span className="library-card-meta">{item.page_count} trang <span aria-hidden="true">·</span> {new Date(item.created_at).toLocaleDateString('vi-VN')}</span>
              <span className="library-card-open">Mở trên Dashboard <span aria-hidden="true">↗</span></span>
            </button>)}</div>
            {total > 20 && <nav className="library-page-pagination" aria-label="Phân trang tài liệu">
              <button type="button" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Trước</button>
              <span>{offset + 1}–{Math.min(offset + items.length, total)} / {total}</span>
              <button type="button" disabled={offset + 20 >= total} onClick={() => setOffset(value => value + 20)}>Sau</button>
            </nav>}
          </>}
    </section>
  </main>
}
