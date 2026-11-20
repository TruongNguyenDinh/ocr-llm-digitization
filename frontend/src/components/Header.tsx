import { useEffect, useState } from 'react'
import { getSystemStatus, type SystemStatus } from '../services/systemApi'

type HeaderProps = {
  activePage: 'dashboard' | 'upload' | 'library'
  onNavigate: (page: 'dashboard' | 'upload' | 'library') => void
}

function BrandMark() {
  return <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
}

export function Header({ activePage, onNavigate }: HeaderProps) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function refreshStatus() {
      try {
        const status = await getSystemStatus()
        if (cancelled) return
        setSystemStatus(status)
        setConnected(true)
      } catch {
        if (cancelled) return
        setConnected(false)
      } finally {
        if (!cancelled) timer = window.setTimeout(refreshStatus, 2000)
      }
    }

    void refreshStatus()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [])

  return (
    <header className="topbar">
      <a className="brand" href="#dashboard" onClick={() => onNavigate('dashboard')}>
        <BrandMark /><span className="brand-name">Văn<span>Thư</span></span>
      </a>
      <nav className="main-nav" aria-label="Điều hướng chính">
        <button className={activePage === 'dashboard' ? 'nav-link active' : 'nav-link'} onClick={() => onNavigate('dashboard')}>
          <span className="nav-dot" />Dashboard
        </button>
        <button className={activePage === 'library' ? 'nav-link active' : 'nav-link'} onClick={() => onNavigate('library')}>
          <span className="library-nav-icon" aria-hidden="true">▤</span>Library
        </button>
        <button className={activePage === 'upload' ? 'nav-link active' : 'nav-link'} onClick={() => onNavigate('upload')}>
          <span className="upload-symbol">↑</span>Upload
        </button>
      </nav>
      <section className="system-status" aria-label="Thông tin tài nguyên máy">
        <span className="system-label"><span className={`status-light ${connected ? 'connected' : ''}`} />MÁY CỦA BẠN</span>
        <div className="resource-list">
          <Resource label="CPU" value={formatPercent(systemStatus?.cpu_percent)} title="Mức sử dụng CPU" />
          <Resource label="GPU" value={formatPercent(systemStatus?.gpu_percent)} title="Mức sử dụng GPU NVIDIA" />
          <Resource label="RAM" value={formatPercent(systemStatus?.ram_percent)} title={systemStatus ? `${systemStatus.ram_used_gb} / ${systemStatus.ram_total_gb} GB` : 'Mức sử dụng RAM'} />
        </div>
        <span className="system-connection">{connected ? 'Đang hoạt động' : 'Chưa kết nối'}</span>
      </section>
      <button className="avatar" aria-label="Tài khoản người dùng">J</button>
    </header>
  )
}

function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? '--' : `${Math.round(value)}%`
}

function Resource({ label, value, title }: { label: string; value: string; title: string }) {
  return <div className="resource" title={title}><span>{label}</span><strong>{value}</strong></div>
}
