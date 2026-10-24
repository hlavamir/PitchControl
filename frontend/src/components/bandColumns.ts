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
