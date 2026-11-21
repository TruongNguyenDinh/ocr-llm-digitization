import { useState } from 'react'
import { DashboardPage } from './pages/DashboardPage'
import { UploadPage } from './pages/UploadPage'
import { LibraryPage } from './pages/LibraryPage'
import { Header } from './components/Header'
import './App.css'

function App() {
  const [activePage, setActivePage] = useState<'dashboard' | 'upload' | 'library'>('dashboard')
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get('document'))

  return (
    <div className="app-shell">
      <Header activePage={activePage} onNavigate={setActivePage} />
      <div className="page-container" hidden={activePage !== 'dashboard'}>
        <DashboardPage active={activePage === 'dashboard'} selectedDocumentId={selectedDocumentId}
          onDocumentOpened={setSelectedDocumentId} />
      </div>
      <div className="page-container" hidden={activePage !== 'upload'}>
        <UploadPage />
      </div>
      <div className="page-container" hidden={activePage !== 'library'}>
        <LibraryPage active={activePage === 'library'} onSelectDocument={documentId => {
          setSelectedDocumentId(documentId)
          setActivePage('dashboard')
        }} />
      </div>
    </div>
  )
}

export default App
