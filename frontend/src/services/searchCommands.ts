/** Return the user query when the composer contains the global-search command. */
export function parseAICommand(value: string): string | null {
  const match = value.trim().match(/^\/ai\s*:\s*(.+)$/is)
  return match?.[1]?.trim() || null
}
