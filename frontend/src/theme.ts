// Appearance: ink colour and UI scale (Settings → Appearance).

export type InkName = 'grey' | 'amber' | 'phosphor'

export interface UiSettings {
  ink: InkName
  key_hints: boolean
  start_fullscreen: boolean // desktop app: open in full screen
  scale: number // UI zoom 0.6..1.5; 1 = the design size
}

export const DEFAULT_UI: UiSettings = { ink: 'grey', key_hints: true, start_fullscreen: false, scale: 1 }

// The layout is designed for a 1512 × 915 px window (14" MacBook) at scale 1.
export const DESIGN_SIZE = { width: 1512, height: 915 }
export const SCALE_MIN = 0.6
export const SCALE_MAX = 1.5
// The page layouts switch to columns from this width (in scaled px), see the "wide" variant in index.css.
const WIDE_FROM = 1280

export const clampScale = (s: number) => Math.round(Math.min(SCALE_MAX, Math.max(SCALE_MIN, s)) * 100) / 100

/** The largest scale at which the design size fits the current window (rounded down to 1 %). */
export function fitScale(): number {
  const s = Math.min(window.innerWidth / DESIGN_SIZE.width, window.innerHeight / DESIGN_SIZE.height)
  return clampScale(Math.floor(s * 100) / 100)
}

/**
 * Scale the whole UI with CSS zoom (like the OS display scaling: layout, text and pointer input all
 * follow). Media and container queries don't see the zoom consistently in WebKit and Chromium, so
 * the page layouts switch on a [data-wide] flag computed here from the scaled window width.
 */
export function applyScale(scale: number): void {
  const root = document.documentElement
  const s = clampScale(scale)
  root.style.zoom = s === 1 ? '' : String(s)
  root.style.setProperty('--ui-scale', String(s))
  // the window width in scaled px (vw units don't follow CSS zoom the same way in every engine)
  root.style.setProperty('--win-w', `${window.innerWidth / s}px`)
  root.toggleAttribute('data-wide', window.innerWidth / s >= WIDE_FROM)
}

export const INKS: Record<InkName, string> = {
  grey: '#d8d9d4',
  amber: '#e9c46a',
  phosphor: '#a8e6b5',
}

/** The Control Desk's colour for routed channels, one per ink so it stands apart from each (item 87, chosen by Miro). */
export const ROUTE_COLORS: Record<InkName, string> = {
  grey: '#e28f6a', // coral
  amber: '#5fc7c0', // teal
  phosphor: '#c9a6f2', // lavender
}

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

export function applyTheme(ui: UiSettings): void {
  document.documentElement.style.setProperty('--ink-rgb', hexToRgb(INKS[ui.ink] ?? INKS.grey).join(' '))
  document.documentElement.style.setProperty('--color-route', ROUTE_COLORS[ui.ink] ?? ROUTE_COLORS.grey)
}

/** The current ink as "r g b", for canvas drawing. */
export function currentInk(): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--ink-rgb').trim() || '216 217 212'
}
