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
export function reconnectLine(status: Pick<IoStatus, 'reconnect'> | null | undefined): string | null {
  const r = status?.reconnect
  if (!r || r.back == null) return null
  if (r.lost == null) return `not found at start · connected ${clock(r.back)}`
  if (r.lost_device && r.back_device && r.lost_device !== r.back_device) {
    return `lost '${r.lost_device}' ${clock(r.lost)} · now '${r.back_device}' ${clock(r.back)}`
  }
  return `lost ${clock(r.lost)} · back ${clock(r.back)}`
}

/** Look again in Connections → Audio: searching now, or what the last press found (``at``: epoch seconds, ``found``: listed). */
export type LookAgain = 'searching' | { found: boolean; at: number } | null

/**
 * The dim line about the saved audio device that isn't running (item 100): the watchdog is still looking for it, or
 * it has stopped after a minute and Look again is the way on (``stoppedLooking``: show the button). After a press it
 * says it is searching, or what the look found: still not found, or listed but it won't open. Nothing while the
 * device runs, or with no device saved.
 */
export function lookingLine(
  status: Pick<IoStatus, 'looking' | 'stopped_looking' | 'device_missing'> | null | undefined,
  device: string | null | undefined,
  look: LookAgain = null,
): { text: string; stoppedLooking: boolean } | null {
  if (!device) return null
  // missing: not in the device list; otherwise listed but its stream died or won't open
  const gone = status?.device_missing ? 'not found' : "isn't running"
  if (status?.looking) return { text: `'${device}' ${gone} · looking for it…`, stoppedLooking: false }
  if (!status?.stopped_looking) return null
  if (look === 'searching') return { text: `'${device}' ${gone} · searching…`, stoppedLooking: true }
  if (look) {
    const what = look.found ? "found, but it won't open" : 'still not found'
    return { text: `'${device}' ${what} · looked ${clock(look.at)}`, stoppedLooking: true }
  }
  return { text: `'${device}' ${gone} · stopped looking after a minute`, stoppedLooking: true }
}
