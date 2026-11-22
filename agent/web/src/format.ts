/** 93784 -> "1d 2h 3m"; under a minute, seconds. */
export function duration(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${seconds % 60}s`
  return `${seconds}s`
}

export function megabytes(bytes: number): string {
  return `${Math.round(bytes / 1048576)} MB`
}

/** "2026-11-22" -> the reader's own date format, without shifting the day. */
export function day(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number)
  return new Date(y!, m! - 1, d!).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
