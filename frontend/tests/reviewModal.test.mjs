import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { createServer } from 'vite'

test('completed LLM review renders the comparison dialog with corrected content', async () => {
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  })
  try {
    const { ReviewModal } = await server.ssrLoadModule('/src/components/ReviewModal.tsx')
    const review = {
      review_id: 'review-render-regression', document_name: 'example', page_count: 1,
      provider: 'qwen', model: 'qwen3:8b', status: 'pending_review',
      metadata: { label_code: '0', label_name: 'Unclassified', sender: null,
        recipient: null, date_time: null, document_type: 'unclassified' },
      pages: [{ page_id: 'page_001', raw_text: 'Original text', corrected_text: 'Corrected text' }],
      markdown_pages: [{ page_id: 'page_001', ocr_markdown: 'Original text',
        llm_markdown: '**Corrected text**', llm_changes: [] }],
    }
    const html = renderToString(createElement(ReviewModal, {
      open: true, review, documentName: review.document_name, isSaving: false,
      externalError: null, onCancel() {}, onFinalize() {},
    }))
    assert.match(html, /role="dialog"/)
    assert.match(html, /display:flex/)
    assert.match(html, /<strong>Corrected text<\/strong>/)
    assert.match(html, /review-original-image/)
    assert.match(html, />Save<\/button>/)
    assert.match(html, />Edit<\/button>/)
  } finally {
    await server.close()
  }
})
