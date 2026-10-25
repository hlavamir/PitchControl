import { useLayoutEffect, useMemo, useState, type RefObject } from 'react'
import { cssCells, snapCells, type CssCells } from './deviceSnap'

export const rootZoom = () => parseFloat(getComputedStyle(document.documentElement).zoom) || 1

// One watcher for every observed element: the UI scale (CSS zoom, a root style property) or the devicePixelRatio
// (window moved to another display, browser zoom) changed.
const scaleListeners = new Set<() => void>()
let styleWatch: MutationObserver | undefined
let dprQuery: MediaQueryList | undefined
const notifyScale = () => scaleListeners.forEach((f) => f())
const onDprChange = () => {
  watchDpr()
  notifyScale()
}
const watchDpr = () => {
  dprQuery?.removeEventListener('change', onDprChange)
  dprQuery = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`)
  dprQuery.addEventListener('change', onDprChange)
}
function onScaleChange(listener: () => void) {
  if (!scaleListeners.size) {
    styleWatch = new MutationObserver(notifyScale)
    styleWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] })
    watchDpr()
  }
  scaleListeners.add(listener)
  return () => {
    scaleListeners.delete(listener)
    if (scaleListeners.size) return
    styleWatch?.disconnect()
    dprQuery?.removeEventListener('change', onDprChange)
  }
}

/**
 * Reports the content box of ``el`` in device pixels, with the scale (zoom × devicePixelRatio) it was measured at (item 81).
 * Exact device pixels where supported (Chromium, WebView2); otherwise CSS size × zoom × devicePixelRatio. contentRect is
 * in the element's own, unzoomed px, also under the root's CSS zoom, so the zoom is multiplied in. The device-pixel box
 * is only trusted when it agrees with that estimate (an emulated devicePixelRatio is not in it). Re-measures when the
 * UI scale or the devicePixelRatio changes. Returns the stop function.
 */
export function observeDevicePixels(el: Element, report: (width: number, height: number, scale: number) => void): () => void {
  let seen = rootZoom() * window.devicePixelRatio
  const ro = new ResizeObserver((entries) => {
    const e = entries[entries.length - 1]
    const scale = rootZoom() * window.devicePixelRatio
    seen = scale
    const w = e.contentRect.width * scale
    const h = e.contentRect.height * scale
    const d = e.devicePixelContentBoxSize?.[0]
    if (d && Math.abs(d.inlineSize - w) <= 2 && Math.abs(d.blockSize - h) <= 2) report(d.inlineSize, d.blockSize, scale)
    else report(w, h, scale)
  })
  const observe = () => {
    try {
      ro.observe(el, { box: 'device-pixel-content-box' })
    } catch {
      ro.observe(el) // WebKit: no device-pixel box
    }
  }
  observe()
  // a new observation reports again; only a changed scale needs it (other root style changes are many: --win-w on every resize)
  const stop = onScaleChange(() => {
    if (rootZoom() * window.devicePixelRatio === seen) return
    ro.unobserve(el)
    observe()
  })
  return () => {
    ro.disconnect()
    stop()
  }
}

/**
 * The cells of a segmented control in whole device pixels (item 81), in CSS px, for the track element ``ref`` (its
 * length along ``axis`` is measured); null until the first measurement, so the caller keeps its flex / grid layout
 * until then. ``seamCss`` is the seam or gap at UI scale 1; ``gap`` makes it a real gap between the cells instead of
 * an inset shadow inside them. The track must not size itself from the cells (they are positioned absolutely).
 */
export function useDeviceSnap(
  ref: RefObject<HTMLElement | null>,
  n: number,
  axis: 'x' | 'y',
  seamCss: number,
  opts: { gap?: boolean; leftover?: 'end' | 'split' | 'spread' } = {},
): CssCells | null {
  const [box, setBox] = useState<{ length: number; scale: number } | null>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    return observeDevicePixels(el, (w, h, scale) => {
      const length = Math.floor((axis === 'x' ? w : h) + 1e-6)
      setBox((b) => (b && b.length === length && b.scale === scale ? b : { length, scale }))
    })
  }, [ref, axis])
  const { gap, leftover } = opts
  return useMemo(() => (box ? cssCells(snapCells(box.length, n, seamCss, box.scale, { gap, leftover }), box.scale) : null), [box, n, seamCss, gap, leftover])
}
