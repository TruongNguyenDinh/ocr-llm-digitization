import { ChatPanel } from '../components/ChatPanel'
import { DocumentViewer } from '../components/DocumentViewer'

export function DashboardPage() {
  return (
    <main className="dashboard-layout">
      <aside className="left-column">
        <section className="search-section">
          <label className="search-box"><span className="search-icon" aria-hidden="true" />
            <input type="search" placeholder="Tìm kiếm tài liệu..." aria-label="Tìm kiếm tài liệu" /><kbd>⌘ K</kbd>
          </label>
          <div className="search-caption"><span>KHÔNG GIAN LÀM VIỆC</span><span className="library-count">0 tài liệu</span></div>
        </section>
        <ChatPanel />
      </aside>
      <DocumentViewer file={null} status="idle" pages={[]} totalPages={null} documentName={null} error={null} />
    </main>
  )
}
