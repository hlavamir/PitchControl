import type { IoStatus } from './api'

/**
 * Why the MIDI input isn't running, in words, for the Inputs page and the mapping editor's Learn notice (the same
 * words for the same case). A port that isn't there is a warning: the shipped settings name a controller that most
 * users don't own, and nothing is broken. A port that is there but can't be opened is an error.
 */
export function midiNotice(midi: IoStatus | null | undefined): { level: 'warning' | 'error'; text: string } | null {
  if (!midi?.error) return null
  if (midi.error_kind === 'not_found') {
    return {
      level: 'warning',
      text: midi.port_override
        ? `MIDI port '${midi.port_wanted}' isn't there. It connects by itself when the controller is plugged in, or pick another port under MIDI port.`
        : `'${midi.controller ?? 'The MIDI controller'}' isn't connected: no MIDI port name contains '${midi.port_wanted}'. It connects by itself when plugged in. If it is plugged in, pick its port under MIDI port.`,
    }
  }
  if (midi.error_kind === 'open_failed') {
    return {
      level: 'error',
      text: `MIDI input stopped: port '${midi.port_wanted}' could not be opened (${midi.error}). Another program may be using it: close that program and it reconnects by itself.`,
    }
  }
  return { level: 'error', text: `MIDI input stopped: ${midi.error}` }
}
