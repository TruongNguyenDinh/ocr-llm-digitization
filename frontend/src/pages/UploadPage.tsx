import { useEffect, useState } from 'react'
import { CorrectionControls } from '../components/CorrectionControls'
import { DocumentViewer } from '../components/DocumentViewer'
import { UploadControl, type UploadStatus } from '../components/UploadControl'
import { createOcrJob, getOcrJob, type OcrPage } from '../services/ocrApi'

export function UploadPage() {
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [completedPages, setCompletedPages] = useState(0)
  const [totalPages, setTotalPages] = useState<number | null>(null)
  const [pages, setPages] = useState<OcrPage[]>([])
  const [documentName, setDocumentName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSelectFile(file: File) {
    setSelectedFile(file)
    setStatus('submitting')
    setCompletedPages(0)
    setTotalPages(null)
    setPages([])
    setDocumentName(null)
    setError(null)
    setJobId(null)

    try {
      const newJobId = await createOcrJob(file)
      setJobId(newJobId)
      setStatus('queued')
    } catch (uploadError) {
      setStatus('failed')
      setError(uploadError instanceof Error ? uploadError.message : 'Không thể tải tài liệu lên.')
    }
  }

  useEffect(() => {
    if (!jobId) return
    const activeJobId = jobId
    let cancelled = false
    let timer: number | undefined

    async function pollJob() {
      try {
        const job = await getOcrJob(activeJobId)
        if (cancelled) return
        setStatus(job.status)
        setCompletedPages(job.completed_pages)
        setTotalPages(job.total_pages)
        setPages(job.pages ?? [])
        setDocumentName(job.document_name)
        setError(job.error)
        if (job.status === 'queued' || job.status === 'running') {
          timer = window.setTimeout(pollJob, 1000)
        }
      } catch (pollError) {
        if (cancelled) return
        setStatus('failed')
        setError(pollError instanceof Error ? pollError.message : 'Không thể nhận trạng thái OCR.')
      }
    }

    void pollJob()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [jobId])

  return (
    <main className="dashboard-layout upload-layout">
      <aside className="left-column upload-sidebar">
        <span className="eyebrow upload-page-eyebrow">SỐ HÓA TÀI LIỆU</span>
        <h1 className="upload-page-title">Upload tài liệu</h1>
        <p className="upload-page-intro">Tải lên bản gốc để nhận dạng nội dung theo từng trang.</p>
        <UploadControl status={status} filename={selectedFile?.name ?? null} completedPages={completedPages}
          totalPages={totalPages} error={error} onSelectFile={handleSelectFile} />
        {status === 'completed' && <CorrectionControls />}
      </aside>
      <DocumentViewer file={selectedFile} status={status} pages={pages} totalPages={totalPages} documentName={documentName} error={error} />
    </main>
  )
}
