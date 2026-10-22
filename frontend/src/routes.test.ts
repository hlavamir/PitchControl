import { describe, expect, it } from 'vitest'
import { learnHint, midiInputText, newMidiRoute, newRoute, overlapText, routeLabel, routedChannels, routedCount, sourceState, type MidiChannelState, type RouteState } from './routes'

const route = (over: Partial<RouteState> = {}): RouteState => ({
  ...(newRoute(0) as Omit<RouteState, 'id' | 'seen' | 'age' | 'pps'>),
  midi_device: '',
  midi_channel: 1,
  channels: [],
  id: 'r1',
  seen: true,
  age: 0.1,
  pps: 40,
  count: 1,
  ...over,
})

describe('routedChannels', () => {
  it('maps the channels of the shown universe to the route that decides them', () => {
    const a = route({ id: 'a', first_output: 10, count: 4 })
    const b = route({ id: 'b', first_output: 12, count: 4 })
    const other = route({ id: 'c', universe: 1, first_output: 1, count: 512 })
    const off = route({ id: 'd', enabled: false, first_output: 100, count: 5 })
    const map = routedChannels([a, b, other, off], 0)
    expect([...map.keys()]).toEqual([10, 11, 12, 13, 14, 15])
    expect(map.get(11)?.id).toBe('a')
    expect(map.get(12)?.id).toBe('b') // the later route wins
    expect(map.has(100)).toBe(false)
  })
  it('counts every routed channel once, in every universe', () => {
    const routes = [route({ first_output: 1, count: 4 }), route({ first_output: 3, count: 4 }), route({ universe: 2, count: 512, first_output: 1 }), route({ enabled: false, count: 50 })]
    expect(routedCount(routes)).toBe(6 + 512)
  })
})

describe('sourceState', () => {
  it('tells never, receiving and holding apart', () => {
    expect(sourceState({ kind: 'artnet', seen: false, age: null, pps: 0 })).toEqual({ text: 'no data yet', level: 'none' })
    expect(sourceState({ kind: 'artnet', seen: true, age: 0.2, pps: 39.6 })).toEqual({ text: 'receiving, 40 packets/s', level: 'live' })
    expect(sourceState({ kind: 'artnet', seen: true, age: 130, pps: 0 })).toEqual({ text: 'quiet for 2 min: holding the last values', level: 'holding' })
  })
})

describe('labels', () => {
  it('names a route by its name, else by its source and target', () => {
    expect(routeLabel(route({ name: 'Console' }))).toBe('Console')
    expect(routeLabel(route({ artnet_universe: 3, universe: 1, first_output: 33 }))).toBe('Art-Net 3 → 1:33')
    expect(routeLabel(route({ kind: 'dmx' }))).toBe('DMX input → 0:1')
  })
  it('describes an overlap with both names', () => {
    const rs = [route({ id: 'a', name: 'Console' }), route({ id: 'b', name: 'Back panel' })]
    expect(overlapText({ universe: 0, first: 21, last: 22, routes: ['a', 'b'] }, rs)).toBe('Output 0, channels 21–22: Console and Back panel; the last one wins')
    expect(overlapText({ universe: 1, first: 5, last: 5, routes: ['a', 'x'] }, rs)).toBe('Output 1, channel 5: Console and ?; the last one wins')
  })
})

const ch = (over: Partial<MidiChannelState>): MidiChannelState => ({ type: 'none', number: 0, value: 0, note_mode: 'velocity', ...over })

describe('MIDI routes', () => {
  it('describes the input of a channel', () => {
    expect([ch({}), ch({ type: 'cc', number: 21 }), ch({ type: 'cc14', number: 1 }), ch({ type: 'note', number: 40 }), ch({ type: 'note', number: 41, note_mode: 'onoff' }), ch({ type: 'const', value: 128 })].map(midiInputText)).toEqual([
      'no input',
      'CC 21',
      'CC 1 + 33 (14-bit)',
      'note 40 (velocity)',
      'note 41 (on / off)',
      '= 128',
    ])
  })
  it('draws only the channels that have an input as routed', () => {
    const midi = route({ kind: 'midi', first_output: 10, count: 3, channels: [ch({ type: 'cc', number: 1 }), ch({}), ch({ type: 'const', value: 5 })] })
    expect([...routedChannels([midi], 0).keys()]).toEqual([10, 12])
    expect(routedCount([midi])).toBe(2)
  })
  it('starts a MIDI route off, with a few channels', () => {
    expect(newMidiRoute(1, 'Pad 1')).toMatchObject({ kind: 'midi', enabled: false, count: 8, universe: 1, midi_device: 'Pad 1', midi_channel: 1 })
  })
  it('names a MIDI route by its device and channel', () => {
    expect(routeLabel(route({ kind: 'midi', midi_device: 'LCXL3', midi_channel: 13, universe: 0, first_output: 5 }))).toBe('MIDI LCXL3 ch 13 → 0:5')
  })
  it('says what a MIDI source is doing, a device problem first', () => {
    const base = { kind: 'midi' as const, seen: false, age: null, pps: 0 }
    expect(sourceState({ ...base, midi_open: false })).toEqual({ text: 'choose a MIDI device', level: 'problem' })
    expect(sourceState({ ...base, midi_open: false, midi_error: 'no MIDI port matches X' })).toEqual({ text: 'no MIDI port matches X', level: 'problem' })
    expect(sourceState({ ...base, midi_open: true })).toEqual({ text: 'no message yet', level: 'none' })
    expect(sourceState({ ...base, midi_open: true, seen: true, age: 0.5 })).toEqual({ text: 'receiving', level: 'live' })
    expect(sourceState({ ...base, midi_open: true, seen: true, age: 90 }).level).toBe('holding')
  })
  it('tells where a control was heard when Learn waits for another channel', () => {
    const learn = { id: 1, route: 'r1', index: 0, channel: 1, seconds: 12.2, heard: null }
    expect(learnHint(learn)).toBe('Move a knob or press a key on the device (MIDI channel 1) · 13 s')
    expect(learnHint({ ...learn, heard: { kind: 'cc', number: 21, channel: 5 } })).toContain('heard CC 21 on channel 5: this route listens on channel 1')
    expect(learnHint({ ...learn, heard: { kind: 'note', number: 40, channel: 1 } })).not.toContain('heard')
  })
})
