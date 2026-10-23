import { bandColumns } from './bandColumns'

interface Props {
  bands: number[] // the live value of each band, 0–1
  norm?: number | number[] // the slowly decaying normalisation value, drawn dimmer behind the live column
  peaks?: number[]
  weights?: number[] // strobo trigger weight per band, drawn as a dotted mark
  height?: number | string
  tip?: string
}

/**
 * The audio bands as plain columns, one per band, no horizontal segments (item 75, as in vvvv): the band's live value
 * in front, bright, and behind it, dimmer, the normalisation value (the slowly decaying maximum the analysis divides
 * by). A peaking band glows. Every band display uses this one component.
 */
export function BandMeter({ bands, norm, peaks, weights, height = 80, tip }: Props) {
  const columns = bandColumns(bands, norm, peaks, weights)
  return (
    <div className="grid w-full gap-px" data-hint="info" data-tip={tip} style={{ height, gridTemplateColumns: `repeat(${bands.length || 1}, minmax(0, 1fr))` }}>
      {columns.map((c, i) => (
        <div key={i} className="relative" style={{ background: 'rgb(var(--ink-rgb) / 0.06)' }}>
          {c.norm > 0 && <div className="absolute inset-x-0 bottom-0" style={{ height: `${c.norm}%`, background: 'rgb(var(--ink-rgb) / 0.2)' }} />}
          <div
            className="absolute inset-x-0 bottom-0"
            style={{
              height: `${c.live}%`,
              background: `rgb(var(--ink-rgb) / ${c.peak ? 1 : 0.7})`,
              boxShadow: c.peak ? '0 0 8px rgb(var(--ink-rgb) / 0.45)' : undefined,
              zIndex: c.peak ? 1 : undefined,
              transition: 'height 80ms linear',
            }}
          />
          {c.weight !== null && <div className="absolute inset-x-0" style={{ bottom: `${c.weight}%`, borderTop: '1px dotted var(--color-dim)', zIndex: 2 }} />}
        </div>
      ))}
    </div>
  )
}

/** One-row segmented bar (phase, settings sliders): cells fade in with the value. */
export function SegmentBar({ value, cells = 32, height = 8, gap = 2, tip }: { value: number; cells?: number; height?: number; gap?: number; tip?: string }) {
  const level = Math.max(0, Math.min(1, value)) * cells
  return (
    <div className="grid flex-1" data-hint="info" data-tip={tip} style={{ gridTemplateColumns: `repeat(${cells}, minmax(0, 1fr))`, gap, height }}>
      {Array.from({ length: cells }, (_, i) => {
        const fill = Math.max(0, Math.min(1, level - i))
        return <div key={i} style={{ background: `rgb(var(--ink-rgb) / ${(0.06 + 0.94 * fill).toFixed(3)})` }} />
      })}
    </div>
  )
}
