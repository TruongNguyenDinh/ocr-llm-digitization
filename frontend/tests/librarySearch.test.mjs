import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasAICommand, parseAICommand, suggestsAICommand } from '../src/services/searchCommands.ts'

test('suggests AI for a command prefix but not emails or ordinary text', () => {
  for (const value of ['@', '@a', '@AI', '  @']) assert.equal(suggestsAICommand(value), true)
  for (const value of ['', 'name@example.com', 'hỏi @', '@AI: nội dung', '@other']) {
    assert.equal(suggestsAICommand(value), false)
  }
})

test('recognizes @AI: queries case-insensitively and trims the question', () => {
  assert.equal(parseAICommand(' @AI:  Ông A được bổ nhiệm năm nào? '), 'Ông A được bổ nhiệm năm nào?')
  assert.equal(parseAICommand('@ai : tìm công văn'), 'tìm công văn')
  assert.equal(hasAICommand('@AI:'), true)
})

test('does not route ordinary text, slash syntax, or an empty @AI: command to global AI search', () => {
  assert.equal(parseAICommand('tìm công văn bổ nhiệm'), null)
  assert.equal(parseAICommand('/AI: tìm công văn'), null)
  assert.equal(parseAICommand('@AI:'), null)
  assert.equal(parseAICommand('@AI:   '), null)
  assert.equal(hasAICommand('tìm @AI: công văn'), false)
})

test('search results render document links without source excerpts', async () => {
  const { createServer } = await import('vite')
  const { createElement } = await import('react')
  const { renderToString } = await import('react-dom/server')
  const { fileURLToPath } = await import('node:url')
  const server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
  })
  try {
    const { ChatPanel } = await server.ssrLoadModule('/src/components/ChatPanel.tsx')
    const html = renderToString(createElement(ChatPanel, {
      document: null,
      globalMessages: [{ role: 'assistant', content: '', results: [{
        document_id: 'doc-1', document_name: 'Quyết định 81', page_number: 8,
        snippet: 'PRIVATE_SOURCE_EXCERPT', score: 1,
      }] }],
    }))
    assert.match(html, /href="\?document=doc-1"/)
    assert.match(html, /Quyết định 81/)
    assert.doesNotMatch(html, /PRIVATE_SOURCE_EXCERPT|trang 8|đoạn phù hợp/)
  } finally {
    await server.close()
  }
})
