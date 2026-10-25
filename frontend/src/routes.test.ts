import { describe, expect, it } from 'vitest'
import { learnHint, midiInputText, newMidiRoute, newRoute, otherUniverses, overlapText, routeLabel, routedChannels, routedCount, sourceLabel, sourceState, type MidiChannelState, type RouteState } from './routes'

const route = (over: Partial<RouteState> = {}): RouteState => ({
  ...(newRoute(0) as Omit<RouteState, 'id' | 'seen' | 'age' | 'pps'>),
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

const ch = (over: Partial<MidiChannelState>): MidiChannelState => ({ channel: 1, type: 'none', number: 0, value: 0, note_mode: 'velocity', ...over })

describe('MIDI routes', () => {
  it('describes the input of a channel', () => {
    expect([ch({}), ch({ type: 'cc', number: 21 }), ch({ type: 'cc14', number: 1, channel: 5 }), ch({ type: 'note', number: 40 }), ch({ type: 'note', number: 41, note_mode: 'onoff', channel: 16 }), ch({ type: 'const', value: 128 })].map(midiInputText)).toEqual([
      'no input',
      'CC 21, ch 1',
      'CC 1 + 33 (14-bit), ch 5',
      'note 40 (velocity), ch 1',
      'note 41 (on / off), ch 16',
      '= 128',
    ])
  })
  it('draws only the channels that have an input as routed', () => {
    const midi = route({ kind: 'midi', first_output: 10, count: 3, channels: [ch({ type: 'cc', number: 1 }), ch({}), ch({ type: 'const', value: 5 })] })
    expect([...routedChannels([midi], 0).keys()]).toEqual([10, 12])
    expect(routedCount([midi])).toBe(2)
  })
  it('starts a MIDI route on, with a few channels that have no input yet (no device, no route-wide channel)', () => {
    const r = newMidiRoute(1)
    expect(r).toMatchObject({ kind: 'midi', enabled: true, count: 8, universe: 1 })
    expect(r).not.toHaveProperty('midi_device')
    expect(r).not.toHaveProperty('midi_channel')
  })
  it('names a MIDI route by its channels, not by a device', () => {
    expect(routeLabel(route({ kind: 'midi', count: 8, universe: 0, first_output: 5 }))).toBe('MIDI, 8 channels → 0:5')
    expect(sourceLabel({ kind: 'midi', artnet_universe: 0, count: 1 })).toBe('MIDI, 1 channel')
  })
  it('says what a MIDI source is doing, an input problem first', () => {
    const base = { kind: 'midi' as const, seen: false, age: null, pps: 0 }
    expect(sourceState({ ...base, midi_error: 'no MIDI input is on (Connections → MIDI)' })).toEqual({ text: 'no MIDI input is on (Connections → MIDI)', level: 'problem' })
    expect(sourceState(base)).toEqual({ text: 'no message yet', level: 'none' })
    expect(sourceState({ ...base, seen: true, age: 0.5 })).toEqual({ text: 'receiving', level: 'live' })
    expect(sourceState({ ...base, seen: true, age: 90 }).level).toBe('holding')
  })
  it('tells Learn waits for any device and channel, and for how long', () => {
    const learn = { id: 1, route: 'r1', index: 0, seconds: 12.2 }
    expect(learnHint(learn)).toBe("Move a knob or press a key on any MIDI device that is on: its channel is taken too · 13 s")
  })
})

describe('otherUniverses', () => {
  it('counts the routes of other universes and names the universes', () => {
    const routes = [route({ id: 'a' }), route({ id: 'b', universe: 2 }), route({ id: 'c', universe: 1 }), route({ id: 'd', universe: 2 })]
    expect(otherUniverses(routes, 0)).toEqual({ count: 3, universes: [1, 2] })
    expect(otherUniverses(routes, 2)).toEqual({ count: 2, universes: [0, 1] })
  })
  it('is empty when every route is in the shown universe', () => {
    expect(otherUniverses([route(), route({ id: 'b' })], 0)).toEqual({ count: 0, universes: [] })
    expect(otherUniverses([], 3)).toEqual({ count: 0, universes: [] })
  })
})
