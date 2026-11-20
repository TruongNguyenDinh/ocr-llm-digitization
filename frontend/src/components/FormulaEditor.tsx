import { useMemo, useState } from 'react'
import { renderFormula, type Formula } from '../services/formulas'

type Props = {
  formula: Formula
  label: string
  disabled: boolean
  changed: boolean
  onPending: (pending: boolean, commit?: () => boolean) => void
  onApply: (body: string) => boolean
}

export function FormulaEditor({ formula, label, disabled, changed, onPending, onApply }: Props) {
  const [draft, setDraft] = useState(formula.body)
  const dirty = draft !== formula.body
  const preview = useMemo(() => renderFormula(draft, formula.delimiter === '$$'), [draft, formula.delimiter])
  return <section className={`formula-editor${changed ? ' formula-manual-change' : ''}`} aria-label={label}>
    <div className="formula-editor-heading">{label} · {formula.delimiter === '$$' ? 'Dạng khối' : 'Trong dòng'}</div>
    <label>
      Nội dung LaTeX
      <textarea aria-label={`${label} LaTeX`} value={draft} disabled={disabled}
        rows={Math.max(2, draft.split('\n').length)} spellCheck={false}
        onChange={(event) => { const body = event.target.value; setDraft(body); onPending(body !== formula.body, () => onApply(body)) }} />
    </label>
    {preview.error ? <p className="formula-error" role="alert">{preview.error}</p>
      : <div className="formula-preview" aria-label={`${label} xem trước`} dangerouslySetInnerHTML={{ __html: preview.html }} />}
    <div className="formula-actions">
      <button type="button" disabled={disabled || !dirty || Boolean(preview.error)}
        onClick={() => { if (onApply(draft)) onPending(false) }}>Áp dụng công thức</button>
      <button type="button" disabled={disabled || !dirty}
        onClick={() => { setDraft(formula.body); onPending(false) }}>Hủy sửa công thức</button>
    </div>
  </section>
}
