/** What GET /api/status returns. Raw values; null where the board cannot tell. */
export interface DeviceStatus {
  clients: number
  frameFlow: boolean
  /** The board's clock, RFC 3339. */
  time: string
  uptimeSeconds: number
  agentUptimeSeconds: number
  memTotalBytes: number
  memAvailableBytes: number
  load1: number
  socTempCelsius: number | null
  /** YYYY-MM-DD */
  lastRecordingDate: string | null
}

export async function fetchStatus(): Promise<DeviceStatus> {
  const res = await fetch('/api/status')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
