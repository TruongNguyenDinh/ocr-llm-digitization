import { useState } from 'react'

const models = ['qwen3:8b', 'qwen3:4b']

export function CorrectionControls() {
  const [model, setModel] = useState(models[0])

  return (
    <section className="correction-controls panel" aria-label="Hiệu đính bằng AI">
      <div className="correction-heading"><span className="assistant-orb" aria-hidden="true">✳</span>
        <div><span className="eyebrow">BƯỚC TIẾP THEO</span><h2>Hiệu đính OCR</h2></div>
      </div>
      <label className="correction-model-label" htmlFor="correction-model">MODEL LOCAL</label>
      <div className="correction-action-row">
        <select id="correction-model" value={model} onChange={(event) => setModel(event.target.value)}>
          {models.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <button className="correction-button" type="button" disabled title="Chức năng sẽ được kết nối sau">✳ <span>AI correction</span></button>
      </div>
      <p className="correction-note">Chọn model trước; chức năng hiệu đính sẽ được kết nối sau.</p>
    </section>
  )
}
