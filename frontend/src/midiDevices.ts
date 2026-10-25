import type { IoStatus, MidiDevice } from './api'

/** How a device of Connections → MIDI says what it is doing, and whether its row is greyed (item 89). */
export function deviceState(d: MidiDevice): { text: string; ok: boolean | null; greyed: boolean } {
  if (d.state === 'connected') return { text: 'connected', ok: true, greyed: false }
  if (d.state === 'off') return { text: 'off', ok: null, greyed: false }
  if (d.state === 'error') return { text: `error: ${d.error ?? 'could not be opened'}`, ok: false, greyed: false }
  return { text: 'not plugged in', ok: null, greyed: true }
}

/** The header's MIDI dot: filled when at least one device that is switched on is open, crossed when one that is on
 * could not be opened and none is, hollow otherwise (nothing plugged in, or every In off). */
export function midiDot(midi: Pick<IoStatus, 'devices' | 'connected_devices'> | null | undefined): { ok: boolean | null; error: string | null } {
  if (!midi) return { ok: null, error: null }
  if ((midi.connected_devices ?? 0) > 0) return { ok: true, error: null }
  const failed = (midi.devices ?? []).find((d) => d.state === 'error')
  return failed ? { ok: false, error: `${failed.name}: ${failed.error ?? 'could not be opened'}` } : { ok: null, error: null }
}

/** Why Learn can't hear anything, in words (the same for the mapping editor and Connections): no device that is on is open. */
export function midiNotice(midi: Pick<IoStatus, 'devices' | 'connected_devices'> | null | undefined): { level: 'warning' | 'error'; text: string } | null {
  if ((midi?.connected_devices ?? 0) > 0) return null
  const devices = midi?.devices ?? []
  const failed = devices.find((d) => d.state === 'error')
  if (failed) {
    return { level: 'error', text: `MIDI device '${failed.name}' could not be opened (${failed.error}). Another program may be using it: close that program and it connects by itself.` }
  }
  if (devices.some((d) => d.state === 'off' && d.input === false) && !devices.some((d) => d.input)) {
    return { level: 'warning', text: 'Every MIDI device is switched off: switch In on for the controller under Connections → MIDI.' }
  }
  return { level: 'warning', text: 'No MIDI device is connected. It connects by itself when plugged in (Connections → MIDI lists the devices).' }
}
