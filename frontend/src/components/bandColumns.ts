/** What one band column of the band meters draws (item 75): heights in percent of the column, all clamped to 0–100. */
export interface BandColumn {
  live: number // the brighter column in front: the band's live value
  norm: number // the dimmer column behind: the slowly decaying maximum the analysis divides by (0 = none shown)
  weight: number | null // the strobo trigger weight, a dotted mark; null when not shown
  peak: boolean
}

const pct = (v: number | undefined) => Math.round(Math.max(0, Math.min(1, Number.isFinite(v) ? (v as number) : 0)) * 1000) / 10

/**
 * The columns of a band meter. ``norm`` is one value for all bands (the analysis divides every band by one shared
 * maximum) or one per band; ``live`` is in the same 0–1 scale, so the live column reaches the normalisation column
 * only when its band is the loudest one.
 */
export function bandColumns(live: number[], norm?: number | number[], peaks?: number[], weights?: number[]): BandColumn[] {
  return live.map((v, i) => ({
    live: pct(v),
    norm: norm === undefined ? 0 : pct(Array.isArray(norm) ? norm[i] : norm),
    weight: weights ? pct(weights[i]) : null,
    peak: Boolean(peaks?.[i]),
  }))
}
