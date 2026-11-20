import assert from 'node:assert/strict'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSanitize from 'rehype-sanitize'
import rehypeRaw from 'rehype-raw'

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
try {
  const { findFormulas, mirrorFormulaEdit, renderFormula } = await server.ssrLoadModule('/src/services/formulas.ts')
  const { rehypeHighlights } = await server.ssrLoadModule('/src/services/reviewHighlights.ts')
  const { FormulaEditor } = await server.ssrLoadModule('/src/components/FormulaEditor.tsx')
  assert.equal(findFormulas('`$x$` [link]($x$) $x=1$ and $$y=2$$').length, 2)
  const source = 'One $x=1$ two $x=1$'
  const target = 'First $x=1$ second $x=1$'
  const edited = mirrorFormulaEdit(source, target, 1, 'x=\\frac{2}{3}')
  assert.equal(edited.source, 'One $x=1$ two $x=\\frac{2}{3}$')
  assert.equal(edited.target, 'First $x=1$ second $x=\\frac{2}{3}$')
  assert.equal(mirrorFormulaEdit(target, source, 0, 'x=4').target, 'One $x=4$ two $x=1$')
  assert.ok(renderFormula('\\frac{', false).error)
  assert.ok(renderFormula('x$y', false).error)
  assert.equal(renderFormula('\\begin{aligned}x&=1\\\\y&=2\\end{aligned}', true).error, null)
  assert.throws(() => mirrorFormulaEdit(source, 'Only $x=1$', 0, 'x=2'))
  for (const markdown of ['Value $x=2$', 'Value\n\n$$\nx=2\n$$']) {
    const formula = findFormulas(markdown)[0]
    const change = { start: formula.start, end: formula.end, before: '', after: formula.text }
    const html = renderToStaticMarkup(React.createElement(ReactMarkdown, {
      remarkPlugins: [remarkMath], rehypePlugins: [rehypeRaw, rehypeSanitize, rehypeHighlights([], [change]), rehypeKatex], children: markdown,
    }))
    assert.match(html, /review-manual-highlight/)
    assert.match(html, /katex/)
    assert.doesNotMatch(html, /review-llm-highlight/)
  }
  const editor = renderToStaticMarkup(React.createElement(FormulaEditor, {
    formula: findFormulas('$x=1$')[0], label: 'Formula', disabled: false, changed: true,
    onPending() {}, onApply() { return true },
  }))
  assert.match(editor, /textarea/)
  assert.match(editor, /katex/)
  assert.match(editor, /formula-manual-change/)
  console.log('PASS: formula parsing, bidirectional duplicate mapping, invalid LaTeX, inline/display highlights and editor rendering.')
} finally { await server.close() }
