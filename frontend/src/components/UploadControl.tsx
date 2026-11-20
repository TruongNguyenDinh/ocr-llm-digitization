import type { ChangeEvent } from 'react'

export type UploadStatus = 'idle' | 'submitting' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

type UploadControlProps = {
  status: UploadStatus
  filename: string | null
  completedPages: number
  totalPages: number | null
  error: string | null
  stageMessage: string
  stageStartedAt: string | null
  lastActivityAt: string | null
  currentPage: number | null
  diagnostics: string[]
  onSelectFile: (file: File) => void
  onCancel: () => void
  isCancelling: boolean
}

const acceptedFiles = '.pdf,.jpg,.jpeg,.png,.bmp,.tiff,.webp'

export function UploadControl({ status, filename, completedPages, totalPages, error, stageMessage, stageStartedAt, lastActivityAt, currentPage, diagnostics, onSelectFile, onCancel, isCancelling }: UploadControlProps) {
  const isBusy = status === 'submitting' || status === 'queued' || status === 'running'
  const isProcessing = status === 'queued' || status === 'running'
  const lastActivityAge = lastActivityAt ? Math.floor((Date.now() - Date.parse(lastActivityAt)) / 1000) : 0

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0]
    if (file) onSelectFile(file)
    event.currentTarget.value = ''
  }

  return (
    <section className="upload-card panel" aria-label="Tải tài liệu lên để số hóa">
      <div className="upload-card-heading">
        <div className="upload-icon" aria-hidden="true">↑</div>
        <div><span className="eyebrow">SỐ HÓA TÀI LIỆU</span><h2>Tải tài liệu lên</h2></div>
      </div>
      <label className={isBusy ? 'upload-button disabled' : 'upload-button'}>
        <input type="file" accept={acceptedFiles} onChange={handleChange} disabled={isBusy} />
        <span className="upload-button-icon" aria-hidden="true">↑</span>
        {isBusy ? 'Đang xử lý...' : 'Chọn tài liệu'}
      </label>
      <p className="upload-hint">PDF hoặc ảnh · Tối đa 100 MB</p>

      {filename && (
        <div className={`upload-progress ${status}`} aria-live="polite">
          <div className="upload-file-row">
            <span className="file-type-icon">{filename.toLowerCase().endsWith('.pdf') ? 'PDF' : 'IMG'}</span>
            <span className="upload-filename" title={filename}>{filename}</span>
            <span className={`job-status-dot ${status}`} />
          </div>
          {isBusy && <>
            <div className="progress-caption"><span>{statusLabel(status)}</span><strong>{totalPages ? `${completedPages}/${totalPages} trang` : 'Đang chuẩn bị'}</strong></div>
            <div className="progress-track"><span style={{ width: `${totalPages ? Math.min(100, (completedPages / totalPages) * 100) : 5}%` }} /></div>
            {status === 'running' && <div className="ocr-stage-status">
              <p>{stageMessage}</p>
              <span>
                {currentPage ? `Trang ${currentPage}` : 'Giai đoạn chuẩn bị'}
                {stageStartedAt ? ` · bước này ${formatDurationSince(stageStartedAt)}` : ''}
              </span>
              {lastActivityAt && <span>Cập nhật worker gần nhất: {formatDurationSince(lastActivityAt)} trước</span>}
              {lastActivityAge >= 60 && <strong className="ocr-stall-warning">Worker chưa phát thêm log trong hơn một phút; có thể đang tính toán bên trong model hoặc bị treo.</strong>}
            </div>}
          </>}
          {isProcessing && <>
            <p className="upload-result">Vui lòng giữ cửa sổ trong quá trình xử lý. Không chuyển sang trang khác của web.</p>
            {error && <p className="upload-error">{error}</p>}
            <button className="upload-cancel-button" type="button" onClick={onCancel} disabled={isCancelling}>
              {isCancelling ? 'Đang dừng...' : 'Dừng OCR'}
            </button>
          </>}
          {diagnostics.length > 0 && <details className="ocr-diagnostics">
            <summary>Chi tiết kỹ thuật ({diagnostics.length} dòng gần nhất)</summary>
            <pre>{diagnostics.join('\n')}</pre>
          </details>}
          {status === 'completed' && <p className="upload-result">Đã nhận dạng {totalPages ?? completedPages} trang.</p>}
          {status === 'failed' && <>
            {totalPages !== null && <p className="upload-result">Đã hoàn tất {completedPages}/{totalPages} trang trước khi xảy ra lỗi.</p>}
            <p className="upload-error">{error ?? 'Không thể xử lý tài liệu.'}</p>
          </>}
          {status === 'cancelled' && <p className="upload-result">Đã dừng OCR theo yêu cầu.</p>}
        </div>
      )}
      {!filename && <p className="upload-format-hint">JPG, PNG, WEBP, TIFF, BMP</p>}
    </section>
  )
}

function formatDurationSince(timestamp: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 1000))
  if (seconds < 60) return `${seconds} giây`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return `${minutes} phút ${remainingSeconds} giây`
  return `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`
}

function statusLabel(status: UploadStatus): string {
  if (status === 'submitting') return 'Đang tải lên'
  if (status === 'queued') return 'Đang chờ PaddleOCR-VL'
  return 'PaddleOCR-VL đang đọc'
}
