import { useEffect, useLayoutEffect, useRef } from 'react'
import { bandColumns, layerHeight, snapColumns } from './bandColumns'

interface Props {
  bands: number[] // the live, normalised value of each band, 0–1
  max?: number[] // each band's own decaying maximum, drawn faint behind the live column
  min?: number[] // each band's own floor, drawn brightest
  peaks?: number[]
  weights?: number[] // strobo trigger weight per band, drawn as a dotted mark
  height?: number | string
  tip?: string
}

const rootZoom = () => parseFloat(getComputedStyle(document.documentElement).zoom) || 1

/**
 * The audio bands as plain columns, one per band, no horizontal segments, as the vvvv patch's audio visualizer (items
 * 75, 81): per band, back to front, its own decaying maximum (faint), the live normalised value, and its own minimum
 * (the brightest core). A peaking band glows. No easing: the columns are redrawn with every engine frame
 * (``useAudioFrame``). Every band display uses this one component.
 *
 * Drawn on a canvas in device pixels (item 81): CSS grid rounds every ``1fr`` column edge by itself, so at fractional
 * zoom or devicePixelRatio the 1 px gaps came out 1 or 2 px wide, or vanished. Here all columns and all gaps are whole
 * and equal (``snapColumns``), the leftover pixels go to the two sides.
 */
export function BandMeter({ bands, max, min, peaks, weights, height = 80, tip }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const sized = useRef(false) // the backing store has the wrapper's device-pixel size
  const paint = useRef<() => void>(() => {})
  const columns = bandColumns(bands, max, min, peaks, weights)

  // the latest props' drawing, run with every render (the observers below call it as well)
  const draw = () => {
    const el = canvas.current
    const ctx = el?.getContext('2d')
    if (!el || !ctx || !sized.current) return
    const style = getComputedStyle(el)
    const ink = style.getPropertyValue('--ink-rgb').trim().split(/\s+/).join(',') || '216,217,212'
    const dim = style.getPropertyValue('--color-dim').trim() || '#8a8c87'
    const scale = rootZoom() * window.devicePixelRatio
    const px = Math.max(1, Math.round(scale)) // 1 CSS px in device px
    const { width: w, height: h } = el
    const { col, gap, offset } = snapColumns(w, columns.length || 1, px)
    const x = (i: number) => offset + i * (col + gap)
    const layer = (i: number, percent: number, alpha: number) => {
      ctx.fillStyle = `rgba(${ink},${alpha})`
      const lh = layerHeight(percent, h)
      ctx.fillRect(x(i), h - lh, col, lh)
    }

    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = `rgba(${ink},0.06)`
    for (let i = 0; i < (columns.length || 1); i++) ctx.fillRect(x(i), 0, col, h)
    columns.forEach((c, i) => {
      if (c.max > 0) layer(i, c.max, 0.16)
      if (!c.peak) layer(i, c.live, 0.45)
      if (c.min > 0) layer(i, c.min, 0.85)
    })
    // a peaking band glows: drawn after all other columns' layers, over its min (as the z-index did), then the marks
    ctx.shadowBlur = 8 * scale
    ctx.shadowColor = `rgba(${ink},0.45)`
    columns.forEach((c, i) => {
      if (c.peak) layer(i, c.live, 1)
    })
    ctx.shadowBlur = 0
    ctx.fillStyle = dim
    columns.forEach((c, i) => {
      if (c.weight === null) return
      const y = Math.max(0, h - layerHeight(c.weight, h) - px)
      for (let dx = 0; dx < col; dx += 2 * px) ctx.fillRect(x(i) + dx, y, Math.min(px, col - dx), px) // 1 px dots, 1 px apart
    })
  }
  useLayoutEffect(() => {
    paint.current = draw
    draw()
  })

  useEffect(() => {
    const box = wrap.current
    const el = canvas.current
    if (!box || !el) return
    const size = (w: number, h: number) => {
      w = Math.max(1, Math.round(w))
      h = Math.max(1, Math.round(h))
      if (el.width !== w) el.width = w
      if (el.height !== h) el.height = h
      sized.current = true
      paint.current()
    }
    // exact device pixels where supported (Chromium, WebView2); otherwise CSS size × zoom × devicePixelRatio. contentRect
    // is in the element's own, unzoomed px, also under the root's CSS zoom, so the zoom is multiplied in. The device-pixel
    // box is only trusted when it agrees with that estimate (an emulated devicePixelRatio is not in it).
    const ro = new ResizeObserver((entries) => {
      const e = entries[entries.length - 1]
      const k = rootZoom() * window.devicePixelRatio
      const w = e.contentRect.width * k
      const h = e.contentRect.height * k
      const d = e.devicePixelContentBoxSize?.[0]
      if (d && Math.abs(d.inlineSize - w) <= 2 && Math.abs(d.blockSize - h) <= 2) size(d.inlineSize, d.blockSize)
      else size(w, h)
    })
    try {
      ro.observe(box, { box: 'device-pixel-content-box' })
    } catch {
      ro.observe(box) // WebKit: no device-pixel box
    }
    // the devicePixelRatio changed (window moved to another display, browser zoom): redraw, and resize in the fallback
    let mq: MediaQueryList | undefined
    const onDpr = () => {
      ro.unobserve(box)
      try {
        ro.observe(box, { box: 'device-pixel-content-box' })
      } catch {
        ro.observe(box)
      }
      watch()
    }
    const watch = () => {
      mq?.removeEventListener('change', onDpr)
      mq = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`)
      mq.addEventListener('change', onDpr)
    }
    watch()
    // a changed ink colour or UI scale (both are style properties of the root)
    const mo = new MutationObserver(() => paint.current())
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] })
    return () => {
      ro.disconnect()
      mq?.removeEventListener('change', onDpr)
      mo.disconnect()
    }
  }, [])

  return (
    <div ref={wrap} className="relative w-full" data-hint="info" data-tip={tip} style={{ height }}>
      <canvas ref={canvas} className="absolute inset-0 block h-full w-full" />
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
