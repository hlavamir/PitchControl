// Routes (Control Desk, items 58 and 59): live input copied onto output channels.

export type RouteKind = 'artnet' | 'dmx' | 'midi'

export type MidiInputType = 'none' | 'cc' | 'cc14' | 'note' | 'const'

/** The input of one output channel of a MIDI route. */
export interface MidiChannelState {
  type: MidiInputType // none: nothing yet; cc: 0..127 scaled to 0..255; cc14: a pair (number and number + 32); note; const: value
  number: number // the CC or note number (cc14: the first of the pair, 0 to 31)
  value: number // const: 0..255
  note_mode: 'velocity' | 'onoff'
}

/** A route as the API sends it: what is saved, and the state of its source. */
export interface RouteState {
  id: string
  name: string
  enabled: boolean
  kind: RouteKind
  artnet_universe: number // the raw Art-Net port address
  first_input: number // 1–512
  count: number // 1–512 (a MIDI route: 1–64)
  universe: number // the output universe
  first_output: number // 1–512
  midi_device: string // a MIDI route: the port
  midi_channel: number // 1–16
  channels: MidiChannelState[] // a MIDI route: one input per output channel
  midi_open?: boolean // a MIDI route: the device is open (here or by the controller's input)
  midi_error?: string | null
  seen: boolean // the source has sent something
  age: number | null // seconds since its last packet
  pps: number // packets per second
}

/** What goes to the server for a new route. */
export type RouteEdit = Partial<Omit<RouteState, 'seen' | 'age' | 'pps' | 'midi_open' | 'midi_error'>>

export interface RouteOverlap {
  universe: number
  first: number
  last: number
  routes: string[] // ids; the last one wins
}

/** A control of a MIDI route that the app's MIDI mapping uses too (a warning: both react). */
export interface MidiNotice {
  route: string
  index: number // the route's output channel, from 0
  kind: 'cc' | 'note'
  number: number
  macros: string[]
  text: string
}

/** The MIDI hub's state: the devices of the routes, and a Learn that waits. */
export interface MidiRoutesStatus {
  devices: { device: string; open: boolean; via: string | null; error: string | null; received: number; age: number | null }[]
  learn: { id: number; route: string; index: number; channel: number; seconds: number; heard: { kind: 'cc' | 'note'; number: number; channel: number } | null } | null
  learned: { id: number; route: string; index: number; type: 'cc' | 'note'; number: number } | null
  learn_seconds: number
}

/** A source that was quiet for this long is "holding" its last values. */
export const HOLDING_AFTER_S = 2

export const MAX_MIDI_COUNT = 64

export function newRoute(universe: number): RouteEdit {
  return { name: '', enabled: true, kind: 'artnet', artnet_universe: 0, first_input: 1, count: 512, universe, first_output: 1 }
}

export function newMidiRoute(universe: number, device: string): RouteEdit {
  return { name: '', enabled: false, kind: 'midi', midi_device: device, midi_channel: 1, first_input: 1, count: 8, universe, first_output: 1 }
}

export function sourceLabel(r: Pick<RouteState, 'kind' | 'artnet_universe' | 'midi_device' | 'midi_channel'>): string {
  if (r.kind === 'midi') return `MIDI ${r.midi_device || '?'} ch ${r.midi_channel}`
  return r.kind === 'dmx' ? 'DMX input' : `Art-Net ${r.artnet_universe}`
}

/** The name of a route: its own, else "source → universe:channel". */
export function routeLabel(r: RouteState): string {
  return r.name || `${sourceLabel(r)} → ${r.universe}:${r.first_output}`
}

/** The input of a route channel in a few words: "CC 21", "CC 1 + 33 (14-bit)", "note 40 (on / off)", "= 128", "no input". */
export function midiInputText(c: MidiChannelState): string {
  switch (c.type) {
    case 'cc':
      return `CC ${c.number}`
    case 'cc14':
      return `CC ${c.number} + ${c.number + 32} (14-bit)`
    case 'note':
      return `note ${c.number} (${c.note_mode === 'onoff' ? 'on / off' : 'velocity'})`
    case 'const':
      return `= ${c.value}`
    default:
      return 'no input'
  }
}

/** Whether a route writes this output channel: a MIDI route's channel without an input writes nothing. */
function drives(r: RouteState, ch: number): boolean {
  return r.kind !== 'midi' || (r.channels[ch - r.first_output]?.type ?? 'none') !== 'none'
}

/** The route that decides each channel of a universe (the last enabled one that covers it wins). */
export function routedChannels(routes: RouteState[], universe: number): Map<number, RouteState> {
  const out = new Map<number, RouteState>()
  for (const r of routes) {
    if (!r.enabled || r.universe !== universe) continue
    for (let ch = r.first_output; ch < r.first_output + r.count; ch++) if (drives(r, ch)) out.set(ch, r)
  }
  return out
}

/** How many output channels the enabled routes cover, in every universe (a channel two routes cover counts once). */
export function routedCount(routes: RouteState[]): number {
  const seen = new Set<string>()
  for (const r of routes) {
    if (!r.enabled) continue
    for (let ch = r.first_output; ch < r.first_output + r.count; ch++) if (drives(r, ch)) seen.add(`${r.universe}:${ch}`)
  }
  return seen.size
}

/** What a route's source is doing, in a few words: never sent, receiving, or quiet (the last values are held). */
export function sourceState(r: Pick<RouteState, 'kind' | 'seen' | 'age' | 'pps' | 'midi_open' | 'midi_error'>): { text: string; level: 'none' | 'live' | 'holding' | 'problem' } {
  if (r.kind === 'midi') {
    if (r.midi_error) return { text: r.midi_error, level: 'problem' }
    if (r.midi_open === false) return { text: 'choose a MIDI device', level: 'problem' }
    if (!r.seen || r.age == null) return { text: 'no message yet', level: 'none' }
    if (r.age > HOLDING_AFTER_S) return { text: `quiet for ${formatAge(r.age)}: holding the last values`, level: 'holding' }
    return { text: 'receiving', level: 'live' }
  }
  if (!r.seen || r.age == null) return { text: 'no data yet', level: 'none' }
  if (r.age > HOLDING_AFTER_S) return { text: `quiet for ${formatAge(r.age)}: holding the last values`, level: 'holding' }
  return { text: `receiving, ${r.pps.toFixed(0)} packets/s`, level: 'live' }
}

export function formatAge(age: number): string {
  if (age < 60) return `${Math.floor(age)} s`
  if (age < 3600) return `${Math.floor(age / 60)} min`
  return `${Math.floor(age / 3600)} h`
}

/** "Output 0, channels 21–22: Console and Back panel; the last one wins". */
export function overlapText(o: RouteOverlap, routes: RouteState[]): string {
  const names = o.routes.map((id) => routes.find((r) => r.id === id)).map((r) => (r ? routeLabel(r) : '?'))
  const chans = o.first === o.last ? `channel ${o.first}` : `channels ${o.first}–${o.last}`
  return `Output ${o.universe}, ${chans}: ${names.join(' and ')}; the last one wins`
}

/** What a Learn that waits says: move a control, and when it hears one on another MIDI channel, which. */
export function learnHint(learn: NonNullable<MidiRoutesStatus['learn']>): string {
  const base = `Move a knob or press a key on the device (MIDI channel ${learn.channel}) · ${Math.ceil(learn.seconds)} s`
  const h = learn.heard
  return h && h.channel !== learn.channel ? `${base} · heard ${h.kind === 'cc' ? 'CC' : 'note'} ${h.number} on channel ${h.channel}: this route listens on channel ${learn.channel}` : base
}

/** The routes that write to other universes than ``universe``: how many, and which universes (item 74: the Routes subpage lists one universe). */
export function otherUniverses(routes: RouteState[], universe: number): { count: number; universes: number[] } {
  const others = routes.filter((r) => r.universe !== universe)
  return { count: others.length, universes: [...new Set(others.map((r) => r.universe))].sort((a, b) => a - b) }
}
