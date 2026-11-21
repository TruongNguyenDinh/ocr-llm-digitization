import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'katex/dist/katex.min.css'
import type { LibrarySearchHit } from '../services/llmApi'
import { hasAICommand, parseAICommand } from '../services/searchCommands'

type Message = { role: 'user' | 'assistant'; content: string }
type GlobalMessage = Message & { results?: LibrarySearchHit[]; total?: number; page?: number; pageSize?: number; question?: string }
const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const defaultContextLimit = 24000

function byteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

function formatBytes(value: number): string {
  return `${Math.max(0, value).toLocaleString('vi-VN')} byte`
}

export function ChatPanel({ document, globalMessages = [], globalBusy = false, globalError, onGlobalSearch, onGlobalPage, onOpenCitation }: {
  document: { id: string; name: string } | null
  globalMessages?: GlobalMessage[]
  globalBusy?: boolean
  globalError?: string | null
  onGlobalSearch?: (question: string) => void | Promise<void>
  onGlobalPage?: (question: string, page: number) => void | Promise<void>
  onOpenCitation?: (hit: LibrarySearchHit) => void
}) {
  const [enabled, setEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [greeting, setGreeting] = useState('')
  const [hasAsked, setHasAsked] = useState(false)
  const [contextLimit, setContextLimit] = useState(defaultContextLimit)
  const [lastContextBytes, setLastContextBytes] = useState(0)
  const request = useRef<AbortController | null>(null)
  const messagesContainer = useRef<HTMLDivElement>(null)
  const documentId = document?.id
  const contextUsed = lastContextBytes + byteLength(draft)
  const contextRemaining = Math.max(0, contextLimit - contextUsed)
  const contextPercent = Math.min(100, contextUsed / contextLimit * 100)
  const contextStatus = contextUsed > contextLimit ? 'exhausted' : contextRemaining < contextLimit * 0.15 ? 'near' : 'ok'
  const aiCommandActive = hasAICommand(draft)
  const composerText = aiCommandActive ? draft.replace(/^@ai\s*:\s*/i, '') : draft

  useEffect(() => {
    setEnabled(false)
    setMessages([])
    setGreeting('')
    setError(null)
    setDraft('')
    setHasAsked(false)
    setContextLimit(defaultContextLimit)
    setLastContextBytes(0)
    setBusy(false)
    return () => { request.current?.abort() }
  }, [documentId])
  useEffect(() => {
    const container = messagesContainer.current
    if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
  }, [messages, greeting, busy])

  async function send(text?: string) {
    const input = text?.trim()
    if (!input) return
    const globalQuery = parseAICommand(input)
    if (globalQuery) {
      if (!globalBusy) { setDraft(''); onGlobalSearch?.(globalQuery) }
      return
    }
    if (!document || busy || !enabled) return
    const history: Message[] = [...messages, { role: 'user' as const, content: input }].slice(-40)
    if (input) setHasAsked(true)
    if (input) {
      setMessages(history)
      setDraft('')
    }
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(`${base}/api/library/${encodeURIComponent(document.id)}/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }), signal: controller.signal,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Không gọi được trợ lý AI.')
      if (controller.signal.aborted) return
      if (typeof data.context_limit_bytes === 'number') setContextLimit(data.context_limit_bytes)
      if (typeof data.context_used_bytes === 'number') setLastContextBytes(data.context_used_bytes)
      setEnabled(true)
      if (input) setMessages([...history, { role: 'assistant', content: data.answer }])
      else setGreeting(data.answer)
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Không kết nối được AI.')
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }

  function startNewConversation() {
    setEnabled(false)
    setMessages([])
    setGreeting('')
    setError(null)
    setDraft('')
    setHasAsked(false)
    setLastContextBytes(0)
  }

  function enableConversation() {
    setEnabled(true)
    setGreeting('Tôi đã sẵn sàng trả lời về tài liệu này.')
  }

  return <section className="chat-panel panel">
    {document && <div className="chat-document-row">
      <span className="chat-document">{document.name}</span>
      {enabled && <button type="button" className="chat-new" disabled={busy} onClick={startNewConversation}>Cuộc trò chuyện mới</button>}
    </div>}
    {document && <div className={`chat-context ${contextStatus}`} aria-live="polite" title="Context của prompt gần nhất; tài liệu được tìm đoạn phù hợp theo từng câu hỏi">
      <div className="chat-context-label"><span>Context còn {formatBytes(contextRemaining)}</span>
        <strong>{contextStatus === 'exhausted' ? 'Đã đầy' : contextStatus === 'near' ? 'Sắp đầy' : 'Còn đủ'}</strong></div>
      <div className="chat-context-track"><span style={{ width: `${contextPercent}%` }} /></div>
    </div>}
    {!enabled && <button className="chat-enable" type="button" disabled={!document || busy} onClick={enableConversation}>
      Bật trò chuyện
    </button>}
    <div className="chat-messages" ref={messagesContainer} role="log" aria-live="polite">
      {greeting && <article className="chat-message chat-assistant"><strong>Trợ Lý</strong><ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{greeting}</ReactMarkdown></article>}
      {globalMessages.map((message, index) => <article key={`global-${index}`} className={`chat-message chat-${message.role}`}>
        <strong>{message.role === 'user' ? 'Bạn' : 'Trợ Lý'}</strong>
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{message.content}</ReactMarkdown>
        {message.results?.length ? <div className="global-search-results" aria-label="Tài liệu tìm được">
          {message.results.map((hit, hitIndex) => <button key={`${hit.document_id}-${hit.page_number}-${hitIndex}`} type="button" className="global-search-hit" onClick={() => onOpenCitation?.(hit)}>
            <strong>{hit.document_name} · trang {hit.page_number}</strong><span>{hit.snippet}</span>
          </button>)}
          {message.total !== undefined && <small>{message.total} đoạn phù hợp</small>}
          {message.pageSize && message.total && message.total > message.pageSize && message.question && <div className="global-search-pages">
            <span>{(message.page ?? 0) + 1}/{Math.ceil(message.total / message.pageSize)}</span>
            <button type="button" disabled={globalBusy || (message.page ?? 0) === 0} onClick={() => onGlobalPage?.(message.question!, (message.page ?? 0) - 1)}>Trước</button>
            <button type="button" disabled={globalBusy || ((message.page ?? 0) + 1) * message.pageSize >= message.total} onClick={() => onGlobalPage?.(message.question!, (message.page ?? 0) + 1)}>Tiếp</button>
          </div>}
        </div> : null}
      </article>)}
      {messages.map((message, index) => <article key={index} className={`chat-message chat-${message.role}`}>
        <strong>{message.role === 'user' ? 'Bạn' : 'Trợ Lý'}</strong>
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{message.content}</ReactMarkdown>
      </article>)}
      {(busy && enabled || globalBusy) && <article className="chat-message chat-assistant chat-typing" role="status"><strong>Trợ Lý</strong><span>Đang tìm trong thư viện…</span></article>}
    </div>
    {(error || globalError) && <p role="alert" className="chat-error">{error || globalError}</p>}
    {document && !hasAsked && <div className="chat-suggestions" aria-label="Gợi ý câu hỏi">
      {['Tóm tắt nội dung tài liệu', 'Tìm thông tin quan trọng'].map(text =>
        <button type="button" className="suggestion" key={text} disabled={!document || !enabled || busy} onClick={() => void send(text)}>{text} <span aria-hidden="true">↗</span></button>)}
    </div>}
    <form className="chat-composer" onSubmit={event => { event.preventDefault(); void send(draft) }}>
      <div className="chat-input-row">
        {aiCommandActive && <span className="ai-command-chip" aria-label="Tìm toàn thư viện bằng AI">@AI</span>}
        <textarea aria-label="Tin nhắn cho trợ lý" placeholder={document ? 'Hỏi về tài liệu… hoặc nhập @AI: để tìm toàn thư viện' : 'Nhập @AI: để tìm trong thư viện…'} rows={2} value={composerText}
          disabled={busy || globalBusy} onChange={event => setDraft(aiCommandActive ? (event.target.value ? `@AI: ${event.target.value}` : '@AI:') : event.target.value)}
          onKeyDown={event => {
            if (aiCommandActive && !composerText && event.key === 'Backspace') { event.preventDefault(); setDraft(''); return }
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft) }
          }} />
      </div>
      <div className="composer-footer"><span>Trợ Lý</span>
        <button type="submit" className="send-button" aria-label="Gửi tin nhắn" disabled={busy || globalBusy || !draft.trim() || (!parseAICommand(draft) && (!document || !enabled || contextUsed > contextLimit))}>↑</button>
      </div>
      <p className="chat-note">AI có thể mắc lỗi. Vui lòng kiểm tra lại thông tin.</p>
    </form>
  </section>
}
