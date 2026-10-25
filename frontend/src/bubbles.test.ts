import { describe, expect, it } from 'vitest'
import type { EngineState, MidiEvent } from './api'
import { Activity, IoTracker, Rates, addPerf, midiRow, perfColumns, perfScale, perfSummary, type PerfBatch, type PerfFrame } from './bubbles'

const batch = (frame: number, rows: [number, number][], fps = 40): PerfBatch => ({ type: 'perf', frame, fps, rows })
const steady = (n: number, interval = 25, tick = 2): [number, number][] => Array.from({ length: n }, () => [interval, tick])
const frames = (intervals: number[], tick = 2): PerfFrame[] => intervals.map((interval, i) => ({ frame: i + 1, interval, tick }))

describe('the perf meter: frames from the stream', () => {
  it('numbers the rows so they end at the batch frame', () => {
    const f = addPerf([], batch(12, [[25, 1], [26, 2], [27, 3]]))
    expect(f.map((x) => x.frame)).toEqual([10, 11, 12])
    expect(f[2]).toEqual({ frame: 12, interval: 27, tick: 3 })
  })

  it('adds what is new and nothing twice', () => {
    let f = addPerf([], batch(3, steady(3)))
    f = addPerf(f, batch(5, steady(3))) // frames 3 to 5: 3 is known
    expect(f.map((x) => x.frame)).toEqual([1, 2, 3, 4, 5])
  })

  it('keeps the last ten seconds', () => {
    const f = addPerf([], batch(1000, steady(1000))) // 25 s at 40 fps
    expect(f.length).toBe(400)
    expect(f[f.length - 1].frame).toBe(1000)
  })

  it('starts over when the engine restarted (its frame number went back)', () => {
    let f = addPerf([], batch(500, steady(10)))
    f = addPerf(f, batch(4, steady(4)))
    expect(f.map((x) => x.frame)).toEqual([1, 2, 3, 4])
  })
})

describe('the perf meter: the numbers', () => {
  it('a steady engine: the target rate, no drops, the compute share', () => {
    const p = perfSummary(frames(Array(400).fill(25), 5), 40)
    expect(p.fps).toBeCloseTo(40, 5)
    expect(p.drops).toBe(0)
    expect(p.worst).toBe(25)
    expect(p.tick).toBe(5)
    expect(p.load).toBeCloseTo(0.2, 5)
    expect(p.seconds).toBeCloseTo(10, 5)
  })

  it('a drop is a frame over 1.5 × the target time', () => {
    const p = perfSummary(frames([25, 37.5, 37.6, 25, 90, 25]), 40)
    expect(p.drops).toBe(2)
    expect(p.worst).toBe(90)
  })

  it('the rate is the last second', () => {
    // 5 s at 20 fps, then a second at 40 fps
    const p = perfSummary(frames([...Array(100).fill(50), ...Array(40).fill(25)]), 40)
    expect(p.fps).toBeCloseTo(40, 5)
  })

  it('no frames yet: zeros', () => {
    expect(perfSummary([], 40)).toMatchObject({ fps: 0, drops: 0, worst: 0, tick: 0, seconds: 0 })
  })
})

describe('the perf meter: the graph', () => {
  it('a column shows the longest frame in it, newest on the right', () => {
    // 10 columns of 1 s; the newest second holds a 90 ms spike
    const cols = perfColumns(frames([...Array(36).fill(25), 90, 25]), 10)
    expect(cols[9]?.interval).toBe(90)
    expect(cols[8]).toBeNull() // under a second of frames: the older columns are empty
  })

  it('a column keeps the largest compute time too', () => {
    const f: PerfFrame[] = [
      { frame: 1, interval: 25, tick: 9 },
      { frame: 2, interval: 40, tick: 1 },
    ]
    expect(perfColumns(f, 1)[0]).toEqual({ interval: 40, tick: 9 })
  })

  it('frames older than the window fall off the left', () => {
    const cols = perfColumns(frames(Array(800).fill(25)), 100)
    expect(cols.length).toBe(100)
    expect(cols.every((c) => c !== null)).toBe(true)
  })

  it('the scale: twice the target time, more for a spike, in 25 ms steps', () => {
    expect(perfScale(frames([25, 30]), 40)).toBe(50)
    expect(perfScale(frames([25, 61]), 40)).toBe(75)
    expect(perfScale(frames([25, 125]), 40)).toBe(125)
    expect(perfScale([], 20)).toBe(100)
  })
})

describe('rates and lights', () => {
  it('a rate needs a second of readings', () => {
    const r = new Rates()
    expect(r.update('a', 0, 0)).toBeNull()
    expect(r.update('a', 20, 500)).toBeNull()
    expect(r.update('a', 40, 1000)).toBe(40)
    expect(r.update('a', 50, 1500)).toBe(40) // kept until the next second
    expect(r.update('a', 80, 2000)).toBe(40)
  })

  it('a counter that went back (a restarted output) starts over', () => {
    const r = new Rates()
    r.update('a', 100, 0)
    r.update('a', 140, 1000)
    expect(r.update('a', 3, 1100)).toBeNull()
  })

  it('no counter: no rate', () => {
    expect(new Rates().update('a', undefined, 0)).toBeNull()
  })

  it('a light flashes when its counter moves, not for what was counted before', () => {
    const a = new Activity(150)
    expect(a.update('midi', 7, 0)).toBe(false)
    expect(a.update('midi', 7, 100)).toBe(false)
    expect(a.update('midi', 8, 200)).toBe(true)
    expect(a.update('midi', 8, 300)).toBe(true)
    expect(a.update('midi', 8, 351)).toBe(false)
  })

  it('the tracker follows the outputs and the MIDI inputs', () => {
    const io = (n: number) =>
      ({
        outputs: { enttec: [{ connected: true, error: null, frames: n }, null], artnet: { connected: true, error: null, frames: n }, pitchpls_v2: null, osc: null },
        audio: null,
        midi: { error: null, received: n, devices: [{ key: 'nano', name: 'Nano', input: true, output: false, state: 'connected', error: null, received: 3, age: 0, reconnect: null }], connected_devices: 1 },
      }) as unknown as EngineState['io']
    const t = new IoTracker()
    t.update(io(0), 0)
    const live = t.update(io(40), 1000)
    expect(live.rates).toEqual({ enttec0: 40, enttec1: null, artnet: 40, v2: null })
    expect(live.active).toEqual({ midi: true, 'device:nano': false })
    expect(t.update(undefined, 2000)).toEqual({ rates: {}, active: {} })
  })
})

describe('MIDI messages', () => {
  const ev = (over: Partial<MidiEvent>): MidiEvent => ({
    t: 0,
    seq: 1,
    device: 'Nano',
    text: 'control_change channel=0 control=13 value=64',
    kind: 'cc',
    number: 13,
    channel: 1,
    value: 64,
    macro: null,
    note: '',
    shift: false,
    release: false,
    shift_button: false,
    learnable: true,
    ...over,
  })
  it('a CC: type, channel, number, value, the macro it moved', () => {
    expect(midiRow(ev({ macro: 'Strobo Brightness' }))).toEqual({ type: 'CC', channel: 'ch 1', number: '13', value: '64', macro: 'Strobo Brightness' })
  })
  it('a note and its release', () => {
    expect(midiRow(ev({ kind: 'note', number: 41, value: 127 })).type).toBe('Note')
    expect(midiRow(ev({ kind: 'note', number: 41, value: 0 })).type).toBe('Note off')
  })
  it('another message: its type from the text, no number or value', () => {
    expect(midiRow(ev({ kind: null, text: 'pitchwheel channel=0 pitch=0' }))).toMatchObject({ type: 'pitchwheel', number: '', value: '' })
  })
})
