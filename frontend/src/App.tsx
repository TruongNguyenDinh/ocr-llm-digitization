import { useState } from 'react'
import { DashboardPage } from './pages/DashboardPage'
import { UploadPage } from './pages/UploadPage'
import { Header } from './components/Header'
import './App.css'

function App() {
  const [activePage, setActivePage] = useState<'dashboard' | 'upload'>('dashboard')

  return (
    <div className="app-shell">
      <Header activePage={activePage} onNavigate={setActivePage} />
      <div className="page-container" hidden={activePage !== 'dashboard'}>
        <DashboardPage />
      </div>
      <div className="page-container" hidden={activePage !== 'upload'}>
        <UploadPage />
      </div>
    </div>
  )
}

export default App
