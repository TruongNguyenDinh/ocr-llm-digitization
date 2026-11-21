/** Whether the input starts with the global AI-search token, including an empty query. */
export function hasAICommand(value: string): boolean {
  return /^@ai\s*:/i.test(value.trimStart())
}

/** Return the user query when the composer contains the global-search command. */
export function parseAICommand(value: string): string | null {
  if (!hasAICommand(value)) return null
  const match = value.trim().match(/^@ai\s*:\s*(.+)$/is)
  return match?.[1]?.trim() || null
}
