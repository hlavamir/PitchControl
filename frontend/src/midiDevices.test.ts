import { describe, expect, it } from 'vitest'
import type { MidiDevice } from './api'
import { deviceState, midiDot, midiNotice } from './midiDevices'

const dev = (over: Partial<MidiDevice>): MidiDevice => ({
  key: 'f1',
  name: 'Traktor Kontrol F1',
  input: true,
  output: false,
  state: 'connected',
  error: null,
  received: 0,
  age: null,
  reconnect: null,
  ...over,
})

describe('deviceState', () => {
  it('says what each state is, and greys only the device that is not plugged in', () => {
    expect(deviceState(dev({}))).toEqual({ text: 'connected', ok: true, greyed: false })
    expect(deviceState(dev({ state: 'off', input: false }))).toEqual({ text: 'off', ok: null, greyed: false })
    expect(deviceState(dev({ state: 'missing' }))).toEqual({ text: 'not plugged in', ok: null, greyed: true })
    expect(deviceState(dev({ state: 'error', error: 'in use by another program?' }))).toEqual({ text: 'error: in use by another program?', ok: false, greyed: false })
  })
})

describe('midiDot', () => {
  it('is filled when at least one enabled device is connected', () => {
    expect(midiDot({ devices: [dev({}), dev({ key: 'x', state: 'missing' })], connected_devices: 1 })).toEqual({ ok: true, error: null })
  })
  it('is hollow with nothing connected, and crossed when a device that is on will not open', () => {
    expect(midiDot({ devices: [dev({ state: 'missing' })], connected_devices: 0 })).toEqual({ ok: null, error: null })
    expect(midiDot({ devices: [dev({ state: 'error', error: 'busy' })], connected_devices: 0 })).toEqual({ ok: false, error: 'Traktor Kontrol F1: busy' })
    expect(midiDot(null)).toEqual({ ok: null, error: null })
  })
})

describe('midiNotice', () => {
  it('has nothing to say while a device is open', () => {
    expect(midiNotice({ devices: [dev({})], connected_devices: 1 })).toBeNull()
  })
  it('names the device that will not open', () => {
    const n = midiNotice({ devices: [dev({ state: 'error', error: 'busy' })], connected_devices: 0 })
    expect(n?.level).toBe('error')
    expect(n?.text).toContain("'Traktor Kontrol F1' could not be opened (busy)")
  })
  it('tells a controller that is not plugged in from one that is switched off', () => {
    expect(midiNotice({ devices: [dev({ state: 'missing' })], connected_devices: 0 })?.text).toMatch(/No MIDI device is connected/)
    expect(midiNotice({ devices: [dev({ state: 'off', input: false })], connected_devices: 0 })?.text).toMatch(/switched off/)
    expect(midiNotice(null)?.level).toBe('warning')
  })
})
