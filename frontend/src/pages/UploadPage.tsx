import { useEffect, useRef, useState } from 'react'
import { CorrectionControls } from '../components/CorrectionControls'
import { DocumentViewer } from '../components/DocumentViewer'
import { ReviewModal } from '../components/ReviewModal'
import { UploadControl, type UploadStatus } from '../components/UploadControl'
import { createReview, finalizeReview as finalizeReviewRequest, type LlmProvider, type ReviewDraft, type ReviewEditLogEntry, type ReviewSource } from '../services/llmApi'
import { cancelOcrJob, createOcrJob, getOcrJob, type OcrPage } from '../services/ocrApi'

export function UploadPage() {
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [completedPages, setCompletedPages] = useState(0)
  const [totalPages, setTotalPages] = useState<number | null>(null)
  const [pages, setPages] = useState<OcrPage[]>([])
  const [documentName, setDocumentName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stageMessage, setStageMessage] = useState('Đang chờ worker OCR.')
  const [stageStartedAt, setStageStartedAt] = useState<string | null>(null)
  const [lastActivityAt, setLastActivityAt] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState<number | null>(null)
  const [diagnostics, setDiagnostics] = useState<string[]>([])
  const [isCancelling, setIsCancelling] = useState(false)
  const [provider, setProvider] = useState<LlmProvider>('qwen')
  const [review, setReview] = useState<ReviewDraft | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [isPreparingReview, setIsPreparingReview] = useState(false)
  const [isFinalizingReview, setIsFinalizingReview] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [finalizedDocumentId, setFinalizedDocumentId] = useState<string | null>(null)
  const statusRef = useRef(status)
  const stoppedJobsRef = useRef(new Set<string>())
  statusRef.current = status

  function applyJob(job: Awaited<ReturnType<typeof getOcrJob>>) {
    setStatus(job.status)
    setCompletedPages(job.completed_pages)
    setTotalPages(job.total_pages)
    setPages(job.pages ?? [])
    setDocumentName(job.document_name)
    setError(job.error)
    setStageMessage(job.stage_message)
    setStageStartedAt(job.stage_started_at)
    setLastActivityAt(job.last_activity_at)
    setCurrentPage(job.current_page)
    setDiagnostics(job.diagnostics ?? [])
  }

  async function requestCancellation(activeJobId: string, keepalive = false) {
    stoppedJobsRef.current.add(activeJobId)
    try {
      const job = await cancelOcrJob(activeJobId, keepalive)
      if (!keepalive) applyJob(job)
    } catch (cancelError) {
      stoppedJobsRef.current.delete(activeJobId)
      if (!keepalive) {
        setError(cancelError instanceof Error
          ? `Không gửi được yêu cầu dừng OCR: ${cancelError.message}`
          : 'Không gửi được yêu cầu dừng OCR.')
      }
    }
  }

  async function handleCancel() {
    if (!jobId || (status !== 'queued' && status !== 'running')) return
    setIsCancelling(true)
    await requestCancellation(jobId)
    setIsCancelling(false)
  }

  async function handleSelectFile(file: File) {
    setSelectedFile(file)
    setStatus('submitting')
    setCompletedPages(0)
    setTotalPages(null)
    setPages([])
    setDocumentName(null)
    setError(null)
    setStageMessage('Đang tải tài liệu lên API.')
    setStageStartedAt(null)
    setLastActivityAt(null)
    setCurrentPage(null)
    setDiagnostics([])
    setJobId(null)
    setProvider('qwen')
    setReview(null)
    setReviewOpen(false)
    setReviewError(null)
    setFinalizedDocumentId(null)

    try {
      const newJobId = await createOcrJob(file)
      setJobId(newJobId)
      setStatus('queued')
    } catch (uploadError) {
      setStatus('failed')
      setError(uploadError instanceof Error ? uploadError.message : 'Không thể tải tài liệu lên.')
    }
  }

  async function handleStartOrOpenReview() {
    if (review) {
      setReviewOpen(true)
      return
    }
    if (!documentName || status !== 'completed') return
    setIsPreparingReview(true)
    setReviewError(null)
    try {
      const draft = await createReview(documentName, provider)
      setReview(draft)
      setReviewOpen(true)
    } catch (reviewRequestError) {
      setReviewError(reviewRequestError instanceof Error
        ? reviewRequestError.message
        : 'Không thể tạo bản hiệu đính.')
    } finally {
      setIsPreparingReview(false)
    }
  }

  async function handleFinalizeReview(
    source: ReviewSource,
    approvedPages: Record<string, string>,
    editLog: ReviewEditLogEntry[],
    labelCode?: string,
    displayName?: string,
  ) {
    if (!review) return
    setIsFinalizingReview(true)
    setReviewError(null)
    try {
      const result = await finalizeReviewRequest(review.review_id, source, approvedPages, editLog, labelCode, displayName)
      setFinalizedDocumentId(result.document_id)
      setReviewOpen(false)
      setReview(null)
    } catch (finalizeError) {
      setReviewError(finalizeError instanceof Error
        ? finalizeError.message
        : 'Không thể lưu tài liệu cuối.')
    } finally {
      setIsFinalizingReview(false)
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
        if (cancelled || stoppedJobsRef.current.has(activeJobId)) return
        applyJob(job)
        if (job.status === 'queued' || job.status === 'running') {
          timer = window.setTimeout(pollJob, 1000)
        }
      } catch (pollError) {
        if (cancelled || stoppedJobsRef.current.has(activeJobId)) return
        setError(
          pollError instanceof Error
            ? `Mất kết nối tạm thời khi lấy trạng thái OCR: ${pollError.message}`
            : 'Mất kết nối tạm thời khi lấy trạng thái OCR.',
        )
        timer = window.setTimeout(pollJob, 3000)
      }
    }

    void pollJob()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    const activeJobId = jobId
    function handlePageHide() {
      if (statusRef.current === 'queued' || statusRef.current === 'running') {
        void requestCancellation(activeJobId, true)
      }
    }
    window.addEventListener('pagehide', handlePageHide)
    return () => {
      window.removeEventListener('pagehide', handlePageHide)
      if (statusRef.current === 'queued' || statusRef.current === 'running') {
        void requestCancellation(activeJobId, true)
      }
    }
  }, [jobId])

  return (
    <main className="dashboard-layout upload-layout">
      <aside className="left-column upload-sidebar">
        <span className="eyebrow upload-page-eyebrow">SỐ HÓA TÀI LIỆU</span>
        <h1 className="upload-page-title">Upload tài liệu</h1>
        <p className="upload-page-intro">Tải lên bản gốc để nhận dạng nội dung theo từng trang.</p>
        <UploadControl status={status} filename={selectedFile?.name ?? null} completedPages={completedPages}
          totalPages={totalPages} error={error} stageMessage={stageMessage}
          stageStartedAt={stageStartedAt} lastActivityAt={lastActivityAt} currentPage={currentPage}
          diagnostics={diagnostics} onSelectFile={handleSelectFile}
          onCancel={() => void handleCancel()} isCancelling={isCancelling} />
        {status === 'completed' && <CorrectionControls provider={provider} onProviderChange={setProvider}
          canStart={Boolean(documentName)} hasReview={Boolean(review)} isFinalized={Boolean(finalizedDocumentId)}
          isLoading={isPreparingReview} error={reviewError} onStartOrOpen={() => void handleStartOrOpenReview()} />}
        {finalizedDocumentId && <p className="review-success" role="status">Đã lưu tài liệu cuối: {finalizedDocumentId}</p>}
      </aside>
      <DocumentViewer file={selectedFile} status={status} pages={pages} totalPages={totalPages} documentName={documentName} error={error} />
      {review && <ReviewModal key={review.review_id} open={reviewOpen} review={review}
        documentName={review.document_name} isSaving={isFinalizingReview} externalError={reviewError}
        onCancel={() => setReviewOpen(false)}
        onFinalize={(source, approvedPages, editLog, labelCode, displayName) => void handleFinalizeReview(source, approvedPages, editLog, labelCode, displayName)} />}
    </main>
  )
}
