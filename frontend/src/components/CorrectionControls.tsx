import type { LlmProvider } from '../services/llmApi'

type CorrectionControlsProps = {
  provider: LlmProvider
  canStart: boolean
  hasReview: boolean
  isFinalized: boolean
  isLoading: boolean
  error: string | null
  onProviderChange: (provider: LlmProvider) => void
  onStartOrOpen: () => void
}

export function CorrectionControls({
  provider,
  canStart,
  hasReview,
  isFinalized,
  isLoading,
  error,
  onProviderChange,
  onStartOrOpen,
}: CorrectionControlsProps) {
  return (
    <section className="correction-controls panel" aria-label="Hiệu đính bằng AI">
      <div className="correction-heading">
        <span className="assistant-orb" aria-hidden="true">✳</span>
        <div><span className="eyebrow">BƯỚC TIẾP THEO</span><h2>Hiệu đính OCR</h2></div>
      </div>
      <label className="correction-model-label" htmlFor="correction-model">MODEL</label>
      <div className="correction-action-row">
        <select id="correction-model" value={provider}
          onChange={(event) => onProviderChange(event.target.value as LlmProvider)}
          disabled={isLoading || hasReview || isFinalized}>
          <option value="qwen">Qwen3:8B · Ollama · mặc định</option>
        </select>
        <button className="correction-button" type="button"
          disabled={(!canStart && !hasReview) || isLoading || isFinalized} onClick={onStartOrOpen}>
          ✳ <span>{isLoading ? 'Đang xử lý…' : isFinalized ? 'Đã lưu cuối' : hasReview ? 'Mở lại đối chiếu' : 'So sánh và sửa'}</span>
        </button>
      </div>
      {error && <p className="correction-error" role="alert">{error}</p>}
      <p className="correction-note">Kiểm tra hai bản cuối trước khi lưu tài liệu vào kho.</p>
    </section>
  )
}
