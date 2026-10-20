export type SystemStatus = {
  cpu_percent: number
  gpu_percent: number | null
  ram_percent: number
  ram_used_gb: number
  ram_total_gb: number
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export async function getSystemStatus(): Promise<SystemStatus> {
  const response = await fetch(`${apiBaseUrl}/api/system/status`)
  if (!response.ok) throw new Error(`System status request failed (${response.status})`)
  return response.json() as Promise<SystemStatus>
}
