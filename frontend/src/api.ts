// Types and helpers for the PitchControl backend API.

import type { LiveInputStatus } from './liveInput'
import type { MidiNotice, MidiRoutesStatus, RouteOverlap, RouteState } from './routes'

export type MacroKind = 'fader' | 'toggle' | 'button' | 'momentary' | 'radio'

export interface MacroDef {
  name: string
  label: string
  min: number
  max: number
  steps: number
  kind: MacroKind
  page: 'general' | 'dimmers' | 'scenes' | 'system'
  default: number
  display_name: string
  radio_group: string | null
  deferred: boolean // applied on release / when the MIDI knob rests (hue, saturation)
  display_scale: number // shown value = value in range × display_scale
  unit: string
  decimals: number
}

export interface FixtureState {
  name: string
  type: string
  group: 'A' | 'B'
  transport: 'dmx' | 'pitchpls_v2'
  universe: number
  address: number
  uv: [number, number][]
  rgb: [number, number, number][]
  output: number[]
}

export interface MidiEvent {
  t: number
  seq: number // counts every message since the port was opened
  text: string
  kind: 'cc' | 'note' | null
  number: number
  channel: number // 1-based
  value: number
  macro: string | null
  note: string
  shift: boolean // a shift button was held when it arrived
  release: boolean // a button let go
  shift_button: boolean // a message from a shift button
  learnable: boolean // what Learn may pick: neither a release nor a shift button
}

/** The control a Learn captured. */
export interface LearnedControl {
  id: number
  kind: 'cc' | 'note'
  number: number
  channel: number // 1-based
  shift: boolean // a shift button was held: the 'with shift' variant
}

export type MidiMode = 'absolute' | 'relative' | 'toggle' | 'momentary' | 'trigger' | 'shift'

/** One MIDI control of a controller file, as the API sends it (optional fields are left out when unset). */
export interface MidiMappingEntry {
  type: 'cc' | 'note'
  number: number
  macro?: string | null
  mode: MidiMode
  channel?: number | null // none = the controller's channel
  page?: 'general' | 'dimmers' | null // none = on every page
  shift?: 'on' | 'off' | null // none = either way
  invert: boolean
  encoder: 'twos_complement' | 'sign_bit' | 'offset_64'
  sensitivity: number
  note: string
}

export interface ControllerFile {
  name: string
  author: string
  description: string
  contact: string
  modified: string // when the app last wrote it
  app_version?: string | null // the version that wrote it
  port_match: string
  channel: number
  mappings: MidiMappingEntry[]
}

/** The OSC output: the socket's state plus what the file said (see io/osc.py). */
export interface OscStatus extends IoStatus {
  messages: number // how many messages the file makes
  ignored: string[] // entries of the file that are ignored, and why
  file_error: string | null // the file is missing or can't be read
}

export interface IoStatus {
  connected?: boolean
  running?: boolean
  error: string | null
  frames?: number
  level?: number
  error_kind?: 'not_found' | 'open_failed' | null // MIDI input: what failed
  port_wanted?: string | null // MIDI input: the match string that found nothing, or the port that wouldn't open
  warning?: string | null // audio input: it runs, but not as set up (fallback channel, system default instead of the device)
  device_missing?: boolean // audio input: the set device wasn't found, the system default is used
  device?: string | null // audio input: the device that was opened
  device_inputs?: number // audio input: its number of inputs
  channels?: number[] // audio input: the channels listened to
  // audio input: when it dropped and came back by itself (epoch seconds; lost null = missing since the start), with the
  // devices it was on; null before any drop (item 30)
  reconnect?: { lost: number | null; back: number | null; lost_device?: string | null; back_device?: string | null } | null
  kind?: 'pro' | 'open' // USB DMX interface: the type the app uses for it
  port?: string | null
  port_override?: string | null // the MIDI port set in Settings, which wins over the controller file's
  wanted?: string // the MIDI port name looked for, as saved (the Settings port, else the controller file's)
  controller?: string | null
  channel?: number | null
  received?: number
  recent?: MidiEvent[]
  shift?: boolean // a shift button of the controller is held
  learning?: boolean // Learn is waiting for a control
  learn_id?: number | null // the Learn that was started last
  learned?: LearnedControl | null // what that Learn captured: the engine takes the first control itself
  learn_seconds?: number // how long Learn waits
}

export interface EngineState {
  frame: number
  fps: number
  tick_ms: number
  macros: Record<string, number>
  pending: Record<string, number> // deferred macro values waiting for the knob to rest
  phase: number
  strobo: number
  idle: number
  peaks_total: number
  trigger: number
  bands: number[]
  band_peaks: number[]
  peaks_map: number[]
  preset: string
  colors: { A: number[]; B: number[] }
  colors_hsb: { A: number[]; B: number[] }
  fixtures: FixtureState[]
  fog: Record<string, boolean>
  overrides?: Record<string, Record<string, number>> // Control Desk: universe → channel (1–512) → value
  routes?: RouteState[] // Control Desk: live input copied onto output channels (item 58)
  route_overlaps?: RouteOverlap[] // output channels that two routes cover
  route_midi_notices?: MidiNotice[] // controls of MIDI routes that the app's MIDI mapping uses too
  io: {
    outputs: { enttec: (IoStatus | null)[]; artnet: IoStatus | null; pitchpls_v2: IoStatus | null; osc: OscStatus | null }
    audio: IoStatus | null
    midi: IoStatus | null
    live_input?: LiveInputStatus // Art-Net and DMX input (item 57)
    midi_routes?: MidiRoutesStatus // the devices of MIDI routes and a Learn that waits (item 59)
  }
}

export interface HSB {
  h: number
  s: number
  b: number
}

export interface DeviceRef {
  serial_number?: string | null
  vid?: number | null
  pid?: number | null
  description?: string | null
  port?: string | null
}

export interface SerialDevice {
  port: string
  description: string | null
  manufacturer: string | null
  serial_number: string | null
  vid: number | null
  pid: number | null
  label: string
  dmx_type?: 'pro' | 'open' | null // what the USB descriptor looks like, for a USB DMX interface
}

export interface AudioDevice {
  index: number
  name: string
  hostapi: string
  label: string
  channels: number
  default?: boolean // the device a stream opens when none is chosen
}

export interface FogMachine {
  name: string
  enabled: boolean
  universe: number
  channel: number
  on_value: number
  off_value: number
  interval_s: number
  duration_s: number
  manual_macro: string | null
}

export interface Settings {
  fps: number
  preview_fps: number
  active_rig: string
  active_controller: string | null
  midi_input: string | null
  audio: {
    device: string | null
    channels: number[]
    gain: number
    sample_rate: number
    [key: string]: unknown
  }
  outputs: {
    // up to 4 USB DMX interfaces (the key is from before there were several types)
    enttec: { enabled: boolean; device: DeviceRef; universe: number; type: 'auto' | 'pro' | 'open'; break_method: 'break' | 'baud'; log_timing: boolean }[]
    artnet: { enabled: boolean; targets: { universe: number; ip: string; artnet_universe?: number | null }[] }
    pitchpls_v2: { enabled: boolean; device: DeviceRef; baudrate: number; mode: number; strips: number; pixels_per_strip: number }
    osc: { enabled: boolean; host: string; port: number; file: string } // file: a name in the osc folder, '' = none
  }
  masks: { line_falloff: number; transition_s: number }
  auto_colors: HSB[]
  ui: { ink: 'grey' | 'amber' | 'phosphor'; key_hints: boolean; start_fullscreen: boolean; scale: number }
  [key: string]: unknown
}

export interface FixtureInstance {
  name: string
  type: string
  mode?: string | null // id of a channel mode of the type; missing = the type's default mode (not in scenes)
  enabled: boolean
  group: 'A' | 'B'
  universe: number
  address: number
  position: [number, number]
  rotation: number
  length: number
  pixel_positions?: [number, number][] | null
  // overrides of fixture-type values; switched off, the type's value applies but the value is kept
  gamma?: Override<number> | null
  strobo_color?: Override<HSB> | null
  channel_values: Record<string, Override<number>> // constant channels by name
  react_to_strobo: boolean // flash on strobo peaks (a rig setting)
  real_strobo: boolean // use the type's shutter channel on peaks
  dimmer_macro?: string | null
  hue_source: 'group' | 'A' | 'B' | 'const'
  hue: number
  saturation_source: 'group' | 'A' | 'B' | 'const'
  saturation: number
  brightness_source: 'pipeline' | 'const'
  brightness: number
  idle_mask_range: { min: number; max: number; curve: number; macro?: string | null }
  [key: string]: unknown
}

export interface Rig {
  name: string
  description: string
  mask_curve?: number // curve of the mask for all fixtures at once (default 0)
  fixtures: FixtureInstance[]
  dimmer_names?: Record<string, string> // "Dimmer 03" → "D Pinspots"
}

export interface Override<T> {
  enabled: boolean
  value: T
}

export type PixelFormat = 'I' | 'RGB' | 'RGBW'

/** One slot of a fixture profile: exactly one of value / pixels / macro / shutter. */
export interface ChannelSlot {
  name?: string | null
  value?: number | null // constant 0–255
  pixels?: PixelFormat | null // the pixel block
  macro?: string | null // a macro's value scaled to 0–255
  shutter?: { open: number; strobo: number } | null
}

/** One DMX channel mode of a fixture type: what a rig fixture picks. `id` is stored in the rig, so renaming never breaks it. */
export interface ChannelMode {
  id: string
  name: string
  description: string
  pixels: number // pixels the light has in this mode (a bar can have 1 or 8, depending on the mode)
  channels: ChannelSlot[]
  ofl_mode?: string // the name of the Open Fixture Library mode this one was imported from (item 53)
}

/** Where an imported type came from (the shape is documented in backend ofl/importer.py); the Fixtures page shows some of it. */
export interface TypeSource {
  format?: string // 'ofl'
  fixture?: string // 'manufacturer-key/fixture-key'
  file?: string
  commit?: string
  [key: string]: unknown
}

export interface FixtureType {
  name: string
  description: string
  transport: 'dmx' | 'pitchpls_v2'
  modes: ChannelMode[] // at least one
  default_mode: string // a mode's id: new rig fixtures start in it
  gamma: number // device curve per channel; 1 = values sent unchanged
  strobo_color: HSB
  // kept data of an import (item 53): carried through every edit and save, not used by the engine
  source?: TypeSource
  links?: Record<string, string[]> // manual, productPage, video
  [key: string]: unknown
}

export const slotKind = (s: ChannelSlot): 'value' | 'pixels' | 'macro' | 'shutter' =>
  s.value != null ? 'value' : s.pixels ? 'pixels' : s.macro ? 'macro' : 'shutter'

/** The mode with this id; none or an unknown id gives the type's default mode (as the engine does). */
export const modeOf = (t: FixtureType, id?: string | null): ChannelMode =>
  t.modes.find((m) => m.id === id) ?? t.modes.find((m) => m.id === t.default_mode) ?? t.modes[0]

/** Number of DMX channels of a mode (the pixel block counts pixels × format length). */
export const modeChannelCount = (m: ChannelMode) =>
  m.channels.reduce((n, s) => n + (s.pixels ? m.pixels * s.pixels.length : 1), 0)

/** Number of DMX channels a fixture takes in a mode (none: the type's default mode). */
export const channelCount = (t: FixtureType, modeId?: string | null) => modeChannelCount(modeOf(t, modeId))

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    let detail: unknown
    try {
      detail = JSON.parse(text).detail
    } catch {
      detail = undefined
    }
    // FastAPI errors carry a readable "detail"; show that alone
    throw new Error(typeof detail === 'string' ? detail : `${method} ${url}: ${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  put: <T>(url: string, body: unknown) => request<T>('PUT', url, body),
  patch: <T>(url: string, body: unknown) => request<T>('PATCH', url, body),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  delete: <T>(url: string) => request<T>('DELETE', url),
}

export function rgbCss(rgb: number[], scale = 255): string {
  const [r, g, b] = rgb.map((x) => Math.round((x * 255) / scale))
  return `rgb(${r}, ${g}, ${b})`
}

/** Alphabetical, ignoring case, with numbers in order ("Light 2" before "Light 10"): the order of every list of names. */
export const byName = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
