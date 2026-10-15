import { describe, expect, it } from 'vitest'
import type { IoStatus } from './api'
import { midiNotice } from './midiNotice'

const status = (s: Partial<IoStatus>): IoStatus => ({ error: null, ...s })

describe('midiNotice', () => {
  it('says nothing while the input runs, or when there is no MIDI status', () => {
    expect(midiNotice(null)).toBeNull()
    expect(midiNotice(status({ port: 'LCXL3 1' }))).toBeNull()
  })

  it('a port that is not there is a warning that leads with the controller', () => {
    const n = midiNotice(
      status({ error: "no MIDI port matches 'lcxl3'", error_kind: 'not_found', port_wanted: 'lcxl3', controller: 'Novation Launch Control XL 3' }),
    )
    expect(n?.level).toBe('warning')
    expect(n?.text).toBe(
      "'Novation Launch Control XL 3' isn't connected: no MIDI port name contains 'lcxl3'. Plug it in, then press Rescan devices. If it is plugged in, pick its port under MIDI port.",
    )
  })

  it('a port picked in the MIDI port row is named as the port', () => {
    const n = midiNotice(status({ error: 'x', error_kind: 'not_found', port_wanted: 'Foo', port_override: 'Foo' }))
    expect(n?.level).toBe('warning')
    expect(n?.text).toBe("MIDI port 'Foo' isn't there. Plug the controller in, then press Rescan devices, or pick another port under MIDI port.")
  })

  it('a port that is there but cannot be opened is an error with the reason', () => {
    const n = midiNotice(status({ error: 'MIDI port is in use', error_kind: 'open_failed', port_wanted: 'Launch Control XL 3' }))
    expect(n?.level).toBe('error')
    expect(n?.text).toBe(
      "MIDI input stopped: port 'Launch Control XL 3' could not be opened (MIDI port is in use). Another program may be using it: close that program, then press Rescan devices.",
    )
  })
})
