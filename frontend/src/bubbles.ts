// The header indicators' detail bubbles (item 66): the numbers behind them, kept apart from the drawing so they can be tested.

import type { EngineState, MidiEvent } from './api'

/** The engine's frame times as the websocket sends them (server/app.py _push_perf): ``rows`` end at frame ``frame``. */
export interface PerfBatch {
  type: 'perf'
  frame: number
  fps: number // the target frame rate (Settings → Engine)
  rows: [number, number][] // per frame: ms since the frame before, ms the engine computed
}

/** One frame of the perf meter. */
export interface PerfFrame {
  frame: number
  interval: number // ms since the frame before: what the lights see
  tick: number // ms the engine computed
}

export const PERF_WINDOW_MS = 10_000 // the perf meter shows the last 10 s
/** A frame that took this many times the target frame time is a drop (a 40 fps engine: over 37.5 ms). */
export const DROP_FACTOR = 1.5

/** The frames of a batch added to the ones known, cut to the last ``windowMs``. A batch that starts over (the engine
 * restarted: its frame number went back) replaces them; frames already known are not added twice. */
export function addPerf(frames: PerfFrame[], batch: PerfBatch, windowMs = PERF_WINDOW_MS): PerfFrame[] {
  const first = batch.frame - batch.rows.length + 1
  const last = frames.length ? frames[frames.length - 1].frame : -1
  const kept = batch.frame < last ? [] : frames
  const known = kept.length ? kept[kept.length - 1].frame : -1
  const added = batch.rows.map(([interval, tick], i) => ({ frame: first + i, interval, tick })).filter((f) => f.frame > known)
  const all = kept.concat(added)
  // from the newest back, until the window is full
  let t = 0
  let start = all.length
  while (start > 0 && t < windowMs) t += all[--start].interval
  return start ? all.slice(start) : all
}

export interface PerfSummary {
  fps: number // frames per second over the last second
  target: number
  drops: number // frames in the window that took over DROP_FACTOR × the target frame time
  worst: number // ms, the longest frame in the window
  tick: number // ms, the engine's average compute time over the last second
  load: number // tick as a share of the target frame time (0..1+)
  seconds: number // how much time the frames cover (under 10 s just after opening)
}

export function perfSummary(frames: PerfFrame[], target: number): PerfSummary {
  const period = 1000 / Math.max(target, 1)
  let covered = 0
  let drops = 0
  let worst = 0
  for (const f of frames) {
    covered += f.interval
    if (f.interval > DROP_FACTOR * period) drops++
    worst = Math.max(worst, f.interval)
  }
  // the last second: its frame count and compute time
  let t = 0
  let n = 0
  let tick = 0
  for (let i = frames.length - 1; i >= 0 && t < 1000; i--) {
    t += frames[i].interval
    tick += frames[i].tick
    n++
  }
  return {
    fps: t > 0 ? (n * 1000) / t : 0,
    target,
    drops,
    worst,
    tick: n ? tick / n : 0,
    load: n ? tick / n / period : 0,
    seconds: covered / 1000,
  }
}

/** The perf meter's columns, newest on the right: each column is ``windowMs / columns`` of time and shows the longest
 * frame in it (a short spike never falls between two columns) and its compute time. Empty columns: null. */
export function perfColumns(frames: PerfFrame[], columns: number, windowMs = PERF_WINDOW_MS): ({ interval: number; tick: number } | null)[] {
  const out: ({ interval: number; tick: number } | null)[] = new Array(columns).fill(null)
  const width = windowMs / columns
  let t = 0 // ms before the newest frame
  for (let i = frames.length - 1; i >= 0; i--) {
    const col = columns - 1 - Math.floor(t / width)
    if (col < 0) break
    const f = frames[i]
    const c = out[col]
    if (!c || f.interval > c.interval) out[col] = { interval: f.interval, tick: Math.max(f.tick, c?.tick ?? 0) }
    else c.tick = Math.max(c.tick, f.tick)
    t += f.interval
  }
  return out
}

/** The graph's top in ms: twice the target frame time, more when a frame took longer (rounded up to 25 ms steps), so
 * the target line sits at half height until a spike needs the room. */
export function perfScale(frames: PerfFrame[], target: number): number {
  const period = 1000 / Math.max(target, 1)
  const worst = frames.reduce((m, f) => Math.max(m, f.interval), 0)
  return worst <= 2 * period ? 2 * period : Math.ceil(worst / 25) * 25
}

/** Rates from counters the engine sends (frames sent, packets): the change over the last second or more, per key. */
export class Rates {
  private seen = new Map<string, { count: number; t: number; rate: number }>()
  private readonly windowMs: number

  constructor(windowMs = 1000) {
    this.windowMs = windowMs
  }

  /** The rate of ``key`` (per second) after a new reading of its counter at ``now`` (ms). */
  update(key: string, count: number | undefined, now: number): number | null {
    if (count === undefined) return null
    const s = this.seen.get(key)
    if (!s || count < s.count) {
      this.seen.set(key, { count, t: now, rate: NaN }) // new or restarted: no rate before the window has passed
      return null
    }
    if (now - s.t >= this.windowMs) {
      s.rate = ((count - s.count) * 1000) / (now - s.t)
      s.count = count
      s.t = now
    }
    return Number.isNaN(s.rate) ? null : s.rate
  }
}

/** One MIDI message as a bubble row: type, channel, number, value and the macro it moved. */
export function midiRow(e: MidiEvent): { type: string; channel: string; number: string; value: string; macro: string } {
  const type = e.kind === 'cc' ? 'CC' : e.kind === 'note' ? (e.value === 0 ? 'Note off' : 'Note') : e.text.split(' ')[0] || 'other'
  return {
    type,
    channel: `ch ${e.channel}`,
    number: e.kind === null ? '' : String(e.number),
    value: e.kind === null ? '' : String(e.value),
    macro: e.macro ?? '',
  }
}

/** A light that flashes when a counter moves: on for ``holdMs`` after the last change. */
export class Activity {
  private last = new Map<string, { count: number; t: number }>()
  private readonly holdMs: number

  constructor(holdMs = 150) {
    this.holdMs = holdMs
  }

  update(key: string, count: number | undefined, now: number): boolean {
    if (count === undefined) return false
    const s = this.last.get(key)
    if (!s) {
      this.last.set(key, { count, t: -Infinity }) // what was counted before the bubble opened is no activity
      return false
    }
    if (count !== s.count) {
      s.count = count
      s.t = now
    }
    return now - s.t < this.holdMs
  }
}

/** What the bubbles show that needs the readings before: the rates of the outputs and the MIDI lights. */
export interface IoLive {
  rates: Record<string, number | null> // enttec0, enttec1 …, artnet, v2: frames per second
  active: Record<string, boolean> // midi, route:<device>: a message came in just now
}

/** Follows the engine state for the header's whole life, so a bubble that opens shows the rates and lights at once. */
export class IoTracker {
  private rates = new Rates()
  private activity = new Activity()

  update(io: EngineState['io'] | undefined, now: number): IoLive {
    const live: IoLive = { rates: {}, active: {} }
    if (!io) return live
    const out = io.outputs
    out.enttec.forEach((e, i) => (live.rates[`enttec${i}`] = this.rates.update(`enttec${i}`, e?.frames, now)))
    live.rates.artnet = this.rates.update('artnet', out.artnet?.frames, now)
    live.rates.v2 = this.rates.update('v2', out.pitchpls_v2?.frames, now)
    live.active.midi = this.activity.update('midi', io.midi?.received, now)
    for (const d of io.midi_routes?.devices ?? []) live.active[`route:${d.device}`] = this.activity.update(`route:${d.device}`, d.received, now)
    return live
  }
}
