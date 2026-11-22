/** What GET /api/status returns. Raw values; null where the board cannot tell. */
export interface DeviceStatus {
  /** The tag the image was built from, or dev-<short sha>. */
  version: string
  clients: number
  frameFlow: boolean
  /** The board's clock, RFC 3339. */
  time: string
  uptimeSeconds: number
  agentUptimeSeconds: number
  memTotalBytes: number
  memAvailableBytes: number
  /** Over the time since the previous request. */
  cpuUsagePercent: number | null
  /** null on a board without an NPU. */
  npuUsagePercent: number | null
  socTempCelsius: number | null
  /** YYYY-MM-DD */
  lastRecordingDate: string | null
}

export async function fetchStatus(): Promise<DeviceStatus> {
  const res = await fetch('/api/status')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
