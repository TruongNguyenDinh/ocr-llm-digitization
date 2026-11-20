import type { MarkdownChange } from './llmApi'

type TreeNode = {
  type: string
  tagName?: string
  value?: string
  children?: TreeNode[]
  position?: { start?: { offset?: number }; end?: { offset?: number } }
  properties?: Record<string, unknown>
}

export function rehypeHighlights(changes: MarkdownChange[], manualChanges: MarkdownChange[] = []) {
  return () => (tree: TreeNode) => {
    function visit(node: TreeNode) {
      const mathNode = node.tagName === 'pre' ? node.children?.[0] : node
      const classes = mathNode?.properties?.className
      if (Array.isArray(classes) && classes.some((name) => name === 'language-math' || name === 'math-inline' || name === 'math-display')) {
        const start = node.position?.start?.offset
        const end = node.position?.end?.offset
        if (start !== undefined && end !== undefined && manualChanges.some((change) => change.end > start && change.start < end)) {
          const original = { ...node }
          Object.assign(node, { type: 'element', tagName: node.tagName === 'pre' ? 'div' : 'span', properties: { className: ['review-manual-highlight'], title: manualChanges.find(change => change.end > start && change.start < end)?.title }, children: [original] })
        }
        return
      }
      if (node.type === 'text' && typeof node.value === 'string') {
        const nodeStart = node.position?.start?.offset
        const nodeEnd = node.position?.end?.offset
        if (nodeStart === undefined || nodeEnd === undefined) return
        const marks = [
          ...changes.map((change) => ({ ...change, kind: 'llm' as const })),
          ...manualChanges.map((change) => ({ ...change, kind: 'manual' as const })),
        ].filter((change) => change.end > nodeStart && change.start < nodeEnd)
        if (!marks.length) return
        const pieces: TreeNode[] = []
        let offset = 0
        const sorted = marks.sort((a, b) => a.start - b.start || (a.kind === 'manual' ? -1 : 1))
        for (const mark of sorted) {
          const from = Math.max(0, mark.start - nodeStart)
          const to = Math.min(node.value.length, mark.end - nodeStart)
          if (to <= offset || from >= node.value.length) continue
          if (from > offset) pieces.push({ type: 'text', value: node.value.slice(offset, from) })
          const markStart = Math.max(from, offset)
          pieces.push({
            type: 'element',
            tagName: 'mark',
            properties: { className: [mark.kind === 'manual' ? 'review-manual-highlight' : 'review-llm-highlight'], title: mark.title },
            children: [{ type: 'text', value: node.value.slice(markStart, to) }],
          })
          offset = to
        }
        if (offset < node.value.length) pieces.push({ type: 'text', value: node.value.slice(offset) })
        Object.assign(node, { type: 'element', tagName: 'span', properties: {}, children: pieces })
        delete node.value
        return
      }
      node.children?.forEach(visit)
    }
    visit(tree)
  }
}
