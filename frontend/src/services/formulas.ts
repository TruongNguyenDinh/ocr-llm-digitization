import katex from 'katex'

export type Formula = { start: number; end: number; body: string; delimiter: string; text: string }

export function findFormulas(text: string): Formula[] {
  const protectedRanges = [...text.matchAll(/!?\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)|```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`|<[^>]+>/g)]
    .map((match) => ({ start: match.index, end: match.index + match[0].length }))
  return [...text.matchAll(/(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<![\\$])\$(?!\$)(?:\\.|[^$\n\\])+(?<!\\)\$(?!\$)/g)]
    .filter((match) => !protectedRanges.some((range) => match.index < range.end && match.index + match[0].length > range.start))
    .map((match) => {
      const delimiter = match[0].startsWith('$$') ? '$$' : '$'
      return { start: match.index, end: match.index + match[0].length,
        body: match[0].slice(delimiter.length, -delimiter.length), delimiter, text: match[0] }
    })
}

export function renderFormula(body: string, displayMode: boolean): { html: string; error: string | null } {
  try {
    if (!body.trim()) throw new Error('Công thức không được để trống.')
    if (/(?<!\\)\$/.test(body)) throw new Error('Chỉ nhập nội dung LaTeX, không thêm dấu $ bao quanh.')
    if (!displayMode && /[\r\n]/.test(body)) throw new Error('Công thức trong dòng không được xuống dòng.')
    return { html: katex.renderToString(body, { displayMode, throwOnError: true, trust: false, maxExpand: 1000 }), error: null }
  } catch (error) {
    return { html: '', error: error instanceof Error ? error.message : 'Công thức LaTeX chưa hợp lệ.' }
  }
}

export function mirrorFormulaEdit(source: string, target: string, index: number, body: string) {
  const originals = findFormulas(source)
  const mirrors = findFormulas(target)
  const original = originals[index]
  const mirror = mirrors[index]
  if (!original || !mirror || originals.length !== mirrors.length || original.text !== mirror.text) {
    throw new Error('Công thức hai bên chưa khớp; không thể đồng bộ an toàn.')
  }
  const validation = renderFormula(body, original.delimiter === '$$')
  if (validation.error) throw new Error(validation.error)
  const inserted = original.delimiter + body + original.delimiter
  return {
    source: source.slice(0, original.start) + inserted + source.slice(original.end),
    target: target.slice(0, mirror.start) + inserted + target.slice(mirror.end),
    edit: { start: original.start, end: original.end, inserted },
    mirrorRange: { start: mirror.start, end: mirror.end },
  }
}
