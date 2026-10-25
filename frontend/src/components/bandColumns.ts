/** What one band column of the band meters draws (items 75, 81): heights in percent of the column, all clamped to 0–100. */
export interface BandColumn {
  max: number // faint, behind: the band's own decaying maximum (0 = none shown)
  live: number // the band's live, normalised value
  min: number // brightest core: the band's own floor, the minimum it has settled to (0 = none shown)
  weight: number | null // the strobo trigger weight, a dotted mark; null when not shown
  peak: boolean
}

const pct = (v: number | undefined) => Math.round(Math.max(0, Math.min(1, Number.isFinite(v) ? (v as number) : 0)) * 1000) / 10

/** The columns of a band meter. ``max`` and ``min`` are per band, in the same 0–1 scale as ``live``; absent, they are 0. */
export function bandColumns(live: number[], max?: number[], min?: number[], peaks?: number[], weights?: number[]): BandColumn[] {
  return live.map((v, i) => ({
    max: pct(max?.[i]),
    live: pct(v),
    min: pct(min?.[i]),
    weight: weights ? pct(weights[i]) : null,
    peak: Boolean(peaks?.[i]),
  }))
}

/**
 * The columns of a band meter in whole device pixels (item 81): every column ``col`` wide, every gap ``gap`` wide,
 * the leftover split at the two sides (``offset``). CSS grid ``1fr`` columns round each edge by itself, which makes
 * uneven gaps at fractional scales. If the gaps leave less than 1 px per column, they shrink to 0.
 */
export function snapColumns(deviceWidth: number, n: number, gap: number): { col: number; gap: number; offset: number } {
  const w = Math.max(0, Math.floor(deviceWidth))
  const count = Math.max(1, Math.floor(n))
  let g = Math.max(0, Math.floor(gap))
  let col = Math.floor((w - (count - 1) * g) / count)
  if (col < 1) {
    g = 0
    col = Math.max(1, Math.floor(w / count))
  }
  return { col, gap: g, offset: Math.max(0, Math.floor((w - (count * col + (count - 1) * g)) / 2)) }
}

/** A layer's height in device pixels from its percent of the meter (drawn from the bottom). */
export const layerHeight = (percent: number, deviceHeight: number) => Math.round((Math.max(0, Math.min(100, percent)) / 100) * deviceHeight)
