/** What GET /api/status returns. */
export interface DeviceStatus {
  clients: number
  systemUptime: string
  appUptime: string
  totalram: number
  freeram: number
  workLoad: number
  cpuTemp: string
  frameFlow: boolean
  lastRecord: string
}

export async function fetchStatus(): Promise<DeviceStatus> {
  const res = await fetch('/api/status')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
