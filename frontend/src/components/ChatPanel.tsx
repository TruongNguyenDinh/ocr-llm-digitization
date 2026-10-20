import { useState } from 'react'

const models = ['qwen3:8b', 'qwen3:4b']

export function ChatPanel() {
  const [model, setModel] = useState(models[0])

  return (
    <section className="chat-panel panel">
      <div className="chat-heading">
        <div><span className="eyebrow">TRỢ LÝ TÀI LIỆU</span><h2>Trò chuyện với AI</h2></div>
        <span className="assistant-orb" aria-hidden="true">✳</span>
      </div>
      <div className="chat-empty">
        <div className="chat-empty-icon" aria-hidden="true">✳</div>
        <h3>Bạn muốn tìm hiểu điều gì?</h3>
        <p>Chọn tài liệu để bắt đầu hỏi đáp với trợ lý AI.</p>
        <div className="suggestion">Tóm tắt nội dung tài liệu <span>↗</span></div>
        <div className="suggestion">Tìm thông tin quan trọng <span>↗</span></div>
      </div>
      <div className="chat-composer">
        <textarea aria-label="Tin nhắn cho AI" placeholder="Hỏi về tài liệu..." rows={2} />
        <div className="composer-footer">
          <label className="model-picker"><span className="model-indicator" />
            <select value={model} onChange={(event) => setModel(event.target.value)} aria-label="Chọn model AI">
              {models.map((item) => <option key={item} value={item}>{item}</option>)}
            </select><span className="select-chevron">⌄</span>
          </label>
          <button className="send-button" aria-label="Gửi tin nhắn" disabled>↑</button>
        </div>
        <p className="chat-note">AI có thể mắc lỗi. Vui lòng kiểm tra lại thông tin.</p>
      </div>
    </section>
  )
}
