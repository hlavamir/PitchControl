import { snapColumns } from './bandColumns'

/** A row of equal cells laid out in whole device pixels (item 81). Everything is in device px; ``starts`` run from the track's origin end (the bottom of a vertical fader, the left of a horizontal one). */
export interface DeviceCells {
  starts: number[]
  sizes: number[]
  seam: number // the seam (inset shadow inside each cell) or the gap between the cells, in whole device px
  origin: number // start of the first cell
  extent: number // from the first cell's start to the last cell's end
}

/** A seam's or gap's thickness in whole device px: ``css`` px at UI scale 1, times the zoom and devicePixelRatio (``scale``), at least 1. */
export const seamThickness = (css: number, scale: number) => Math.max(1, Math.round(css * scale))

/**
 * Cells in whole device pixels. CSS flex / grid fractions round every cell edge by itself, so at a fractional zoom or
 * devicePixelRatio the cells came out 1 px taller or wider here and there and the 1 px seams blurred into 2 px bands.
 * ``gap`` false: the seam is drawn inside each cell, the cells touch. ``leftover`` is where the pixels go that do not
 * divide into the cells: ``end`` at the far end of the track, ``split`` half at each end, ``spread`` into the cells
 * (they differ by at most 1 px, the seams stay equal and the cells fill the track exactly).
 */
export function snapCells(deviceLength: number, n: number, seamCss: number, scale: number, opts: { gap?: boolean; leftover?: 'end' | 'split' | 'spread' } = {}): DeviceCells {
  const { gap = false, leftover = 'end' } = opts
  const length = Math.max(0, Math.floor(deviceLength))
  const count = Math.max(1, Math.floor(n))
  const thickness = seamThickness(seamCss, scale)
  const starts: number[] = []
  const sizes: number[] = []
  let between = 0
  if (leftover === 'spread') {
    between = gap && length - (count - 1) * thickness >= count ? thickness : 0
    const total = length - (count - 1) * between
    const edge = (i: number) => Math.round((i * total) / count)
    for (let i = 0; i < count; i++) {
      starts.push(edge(i) + i * between)
      sizes.push(edge(i + 1) - edge(i))
    }
  } else {
    const { col, gap: g, offset } = snapColumns(length, count, gap ? thickness : 0)
    between = g
    const from = leftover === 'split' ? offset : 0
    for (let i = 0; i < count; i++) {
      starts.push(from + i * (col + g))
      sizes.push(col)
    }
  }
  const smallest = Math.min(...sizes)
  const seam = gap ? between : Math.min(thickness, Math.max(0, smallest - 1))
  const last = count - 1
  return { starts, sizes, seam, origin: starts[0], extent: starts[last] + sizes[last] - starts[0] }
}

/** Cells in CSS px (at the UI scale in effect), the numbers the layout takes; ``device`` keeps the whole-pixel values. */
export interface CssCells {
  starts: number[]
  sizes: number[]
  seam: number
  origin: number
  extent: number
  device: DeviceCells
  scale: number
}

// Chromium and WebKit truncate a length to 1/64 px, and k / scale * scale can land just under the whole number k: a
// hair of extra keeps every edge on the whole device pixel it was computed for.
const HAIR = 1 / 256

export function cssCells(device: DeviceCells, scale: number): CssCells {
  const css = (d: number) => (d + HAIR) / scale
  return {
    starts: device.starts.map(css),
    sizes: device.sizes.map(css),
    seam: device.seam / scale,
    origin: css(device.origin),
    extent: css(device.extent),
    device,
    scale,
  }
}

/** A second row of ``n`` cells (the colour scale next to a fader) filling exactly the extent of an already snapped row. */
export function spreadWithin(cells: CssCells, n: number, seamCss: number): CssCells {
  const inner = snapCells(cells.device.extent, n, seamCss, cells.scale, { leftover: 'spread' })
  const shifted = { ...inner, starts: inner.starts.map((s) => s + cells.device.origin), origin: cells.device.origin }
  return cssCells(shifted, cells.scale)
}

/** The absolute box of cell ``i`` along ``axis``: ``y`` stacks upward from the bottom edge, ``x`` runs from the left edge. */
export function cellBox(cells: CssCells, i: number, axis: 'x' | 'y') {
  return axis === 'y'
    ? { position: 'absolute' as const, left: 0, right: 0, bottom: cells.starts[i], height: cells.sizes[i] }
    : { position: 'absolute' as const, top: 0, bottom: 0, left: cells.starts[i], width: cells.sizes[i] }
}
