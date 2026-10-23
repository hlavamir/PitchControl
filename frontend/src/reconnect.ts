import type { IoStatus } from './api'

const clock = (epochSeconds: number) => {
  const d = new Date(epochSeconds * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/**
 * The dim line in Connections that stays after the audio input dropped and came back by itself, so that the
 * operator sees afterwards that it happened during the show (item 30, Danny's texts). Times are this browser's local
 * time. The device is named only when it changed (no device saved: after a pulled interface the system default
 * moves to another one). Nothing while the input hasn't dropped or hasn't come back yet.
 */
export function reconnectLine(status: IoStatus | null | undefined): string | null {
  const r = status?.reconnect
  if (!r || r.back == null) return null
  if (r.lost == null) return `not found at start · connected ${clock(r.back)}`
  if (r.lost_device && r.back_device && r.lost_device !== r.back_device) {
    return `lost '${r.lost_device}' ${clock(r.lost)} · now '${r.back_device}' ${clock(r.back)}`
  }
  return `lost ${clock(r.lost)} · back ${clock(r.back)}`
}
