import type { ChangeEvent } from 'react'

export type UploadStatus = 'idle' | 'submitting' | 'queued' | 'running' | 'completed' | 'failed'

type UploadControlProps = {
  status: UploadStatus
  filename: string | null
  completedPages: number
  totalPages: number | null
  error: string | null
  onSelectFile: (file: File) => void
}

const acceptedFiles = '.pdf,.jpg,.jpeg,.png,.bmp,.tiff,.webp'

export function UploadControl({ status, filename, completedPages, totalPages, error, onSelectFile }: UploadControlProps) {
  const isBusy = status === 'submitting' || status === 'queued' || status === 'running'

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
          </>}
          {status === 'completed' && <p className="upload-result">Đã nhận dạng {totalPages ?? completedPages} trang.</p>}
          {status === 'failed' && <>
            {totalPages !== null && <p className="upload-result">Đã hoàn tất {completedPages}/{totalPages} trang trước khi xảy ra lỗi.</p>}
            <p className="upload-error">{error ?? 'Không thể xử lý tài liệu.'}</p>
          </>}
        </div>
      )}
      {!filename && <p className="upload-format-hint">JPG, PNG, WEBP, TIFF, BMP</p>}
    </section>
  )
}

function statusLabel(status: UploadStatus): string {
  if (status === 'submitting') return 'Đang tải lên'
  if (status === 'queued') return 'Đang chờ PaddleOCR-VL'
  return 'PaddleOCR-VL đang đọc'
}
