import type { CSSProperties } from 'react'
import { bandColumns } from './bandColumns'

interface Props {
  bands: number[] // the live, normalised value of each band, 0–1
  max?: number[] // each band's own decaying maximum, drawn faint behind the live column
  min?: number[] // each band's own floor, drawn brightest
  peaks?: number[]
  weights?: number[] // strobo trigger weight per band, drawn as a dotted mark
  height?: number | string
  tip?: string
}

/**
 * The audio bands as plain columns, one per band, no horizontal segments, as the vvvv patch's audio visualizer (items
 * 75, 81): per band, back to front, its own decaying maximum (faint), the live normalised value, and its own minimum
 * (the brightest core). A peaking band glows. No easing: the columns are redrawn with every engine frame
 * (``useAudioFrame``). Every band display uses this one component.
 */
export function BandMeter({ bands, max, min, peaks, weights, height = 80, tip }: Props) {
  const columns = bandColumns(bands, max, min, peaks, weights)
  const layer = (h: number, alpha: number, extra?: CSSProperties) => (
    <div className="absolute inset-x-0 bottom-0" style={{ height: `${h}%`, background: `rgb(var(--ink-rgb) / ${alpha})`, ...extra }} />
  )
  return (
    <div className="grid w-full gap-px" data-hint="info" data-tip={tip} style={{ height, gridTemplateColumns: `repeat(${bands.length || 1}, minmax(0, 1fr))` }}>
      {columns.map((c, i) => (
        <div key={i} className="relative" style={{ background: 'rgb(var(--ink-rgb) / 0.06)' }}>
          {c.max > 0 && layer(c.max, 0.16)}
          {layer(c.live, c.peak ? 1 : 0.45, c.peak ? { boxShadow: '0 0 8px rgb(var(--ink-rgb) / 0.45)', zIndex: 1 } : undefined)}
          {c.min > 0 && layer(c.min, 0.85)}
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
