// The pixel block of a channel mode (item 103): a preset (I, RGB, GRB, RGBW) or a list of channel sources, one per channel of
// a pixel. The names and the presets are the same as in the backend (config/models.py: PIXEL_SOURCES, PIXEL_PRESETS); the
// rules are plain functions so that the tests can check them.

import type { ChannelMode, PixelFormat } from './api'

export const PIXEL_SOURCES = [
  'RGB.red',
  'RGB.green',
  'RGB.blue',
  'RGBW.red',
  'RGBW.green',
  'RGBW.blue',
  'RGBW.white',
  'HSB.hue',
  'HSB.saturation',
  'HSB.brightness',
] as const
export type PixelSource = (typeof PIXEL_SOURCES)[number]

export const PIXEL_PRESETS: Record<PixelFormat, PixelSource[]> = {
  I: ['HSB.brightness'],
  RGB: ['RGB.red', 'RGB.green', 'RGB.blue'],
  GRB: ['RGB.green', 'RGB.red', 'RGB.blue'],
  RGBW: ['RGBW.red', 'RGBW.green', 'RGBW.blue', 'RGBW.white'],
}
export const PRESET_NAMES = Object.keys(PIXEL_PRESETS) as PixelFormat[]
export const PIXEL_CHANNEL_COUNTS = [1, 3, 4] as const

/** A pixel block as the file keeps it. */
export type Pixels = PixelFormat | string[]

/** The channel sources of a pixel block. */
export const pixelSources = (p: Pixels): string[] => (typeof p === 'string' ? (PIXEL_PRESETS[p as PixelFormat] ?? PIXEL_PRESETS.RGB) : p)

/** A list of sources as the file keeps it: the preset's name when it spells one (as the backend saves it), else the list. */
export function normalisePixels(sources: string[]): Pixels {
  const preset = PRESET_NAMES.find((name) => PIXEL_PRESETS[name].join() === sources.join())
  return preset ?? sources
}

/** The preset a pixel block is, or null for a custom order. */
export const presetOf = (p: Pixels): PixelFormat | null => (typeof p === 'string' ? p : (PRESET_NAMES.find((name) => PIXEL_PRESETS[name].join() === p.join()) ?? null))

/** The default sources of a pixel with this many channels: 1 HSB.brightness, 3 RGB, 4 RGBW. */
export const defaultPixels = (count: number): Pixels => (count === 1 ? 'I' : count === 4 ? 'RGBW' : 'RGB')

/** The same pixel block with source ``name`` in channel ``index``. */
export function withSource(p: Pixels, index: number, name: string): Pixels {
  const next = [...pixelSources(p)]
  next[index] = name
  return normalisePixels(next)
}

const LETTER: Record<string, string> = { red: 'R', green: 'G', blue: 'B', white: 'W' }
const WORD: Record<string, string> = { hue: 'hue', saturation: 'sat', brightness: 'bri' }

/** A short name of one channel source: R G B W for the colours, hue / sat / bri for HSB. */
export function sourceLabel(source: string): string {
  const [kind, part] = source.split('.')
  return kind === 'HSB' ? (WORD[part] ?? part) : (LETTER[part] ?? part)
}

/** A pixel block in a few characters: its preset name, or the order of its channels (BGR, WRGB, hue sat bri). */
export function pixelLabel(p: Pixels): string {
  if (typeof p === 'string') return p
  const parts = p.map(sourceLabel)
  return parts.every((x) => x.length === 1) ? parts.join('') : parts.join(' ')
}

/** What the monitor calls each DMX channel of a mode: "pixel 2 · RGB.green", the name of a constant, and so on. */
export function channelLabels(mode: ChannelMode): string[] {
  const out: string[] = []
  for (const s of mode.channels) {
    if (s.pixels) {
      const sources = pixelSources(s.pixels)
      for (let px = 1; px <= mode.pixels; px++) for (const src of sources) out.push(mode.pixels > 1 ? `pixel ${px} · ${src}` : src)
    } else if (s.value != null) out.push(s.name ? `${s.name} (constant ${s.value})` : `constant ${s.value}`)
    else if (s.macro) out.push(s.name ? `${s.name} (${s.macro})` : s.macro)
    else out.push(s.name ? `${s.name} (shutter)` : 'shutter')
  }
  return out
}

/** The colour that tells a pixel channel's source apart in the output monitor. */
export function sourceColour(label: string): string | null {
  const part = label.split('.')[1]
  if (!part) return null
  return { red: '#e5484d', green: '#30a46c', blue: '#3e63dd', white: '#e8e8e8', hue: '#ab4aba', saturation: '#d6409f', brightness: '#8d8d8d' }[part] ?? null
}
