import { useEffect, useRef } from 'react'
import type { EngineState } from '../api'
import { currentInk } from '../theme'
import { PREVIEW_SIZE } from '../useEngine'

interface Props {
  preview: Uint8Array | null
  state: EngineState | null
  showFixtures?: boolean
  highlight?: string | string[] | null // fixture name(s) to outline
  className?: string
}

const MASK_LEVEL = 0.65 // the mask is drawn darker than full white: less light from the screen

/**
 * The square 2D scene: the mask in plain greyscale (no dithering: it shows the real output) and
 * every fixture pixel as a square in the colour it is sending. The first pixel of a multi-pixel
 * fixture has an ink ring, drawn after all pixels so nothing covers it, so its direction is visible.
 */
export function Preview({ preview, state, showFixtures = true, highlight, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const offscreen = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const size = canvas.width
    const unit = size / 382 // sizes below are in CSS px at the design size
    const ink = currentInk().split(' ').join(',')

    ctx.fillStyle = '#0b0c0c'
    ctx.fillRect(0, 0, size, size)
    if (preview && preview.length === PREVIEW_SIZE * PREVIEW_SIZE) {
      if (!offscreen.current) {
        offscreen.current = document.createElement('canvas')
        offscreen.current.width = PREVIEW_SIZE
        offscreen.current.height = PREVIEW_SIZE
      }
      const octx = offscreen.current.getContext('2d')!
      const img = octx.createImageData(PREVIEW_SIZE, PREVIEW_SIZE)
      for (let i = 0; i < preview.length; i++) {
        const v = 11 + preview[i] * MASK_LEVEL
        img.data[i * 4] = v
        img.data[i * 4 + 1] = v + 1
        img.data[i * 4 + 2] = v + 1
        img.data[i * 4 + 3] = 255
      }
      octx.putImageData(img, 0, 0)
      ctx.imageSmoothingEnabled = true
      ctx.drawImage(offscreen.current, 0, 0, size, size)
    }

    if (showFixtures && state) {
      const pixelSize = (n: number) => (n > 1 ? (n > 20 ? 6 : 5) : 10) * unit
      // pass 1: every pixel of every fixture. The marks come after all of them (pass 2), so a pixel
      // drawn later, on a short strip or in the next fixture, can't cover a mark.
      for (const fx of state.fixtures) {
        const px = pixelSize(fx.uv.length)
        fx.uv.forEach(([u, v], i) => {
          const [r, g, b] = fx.rgb[i] ?? [0, 0, 0]
          const x = u * size - px / 2
          const y = v * size - px / 2
          const bright = Math.max(r, g, b) / 255
          // halation: bright pixels bloom in their own colour
          ctx.shadowColor = `rgba(${r},${g},${b},${0.9 * bright})`
          ctx.shadowBlur = bright > 0.3 ? 10 * unit * bright : 0
          ctx.fillStyle = `rgb(${r},${g},${b})`
          ctx.fillRect(x, y, px, px)
          ctx.shadowBlur = 0
          ctx.lineWidth = unit
          ctx.strokeStyle = '#0b0c0c'
          ctx.strokeRect(x, y, px, px)
        })
      }
      // pass 2: a selected fixture has a thin ring round each pixel; the first pixel of a strip has a
      // stronger mark (a double ring, further out than the pixel's neighbours reach), selected or not
      ctx.strokeStyle = `rgb(${ink})`
      const ring = (x: number, y: number, px: number, out: number, width: number) => {
        ctx.lineWidth = width * unit
        ctx.strokeRect(x - out * unit, y - out * unit, px + 2 * out * unit, px + 2 * out * unit)
      }
      for (const fx of state.fixtures) {
        const focused = Array.isArray(highlight) ? highlight.includes(fx.name) : highlight === fx.name
        const multi = fx.uv.length > 1
        const px = pixelSize(fx.uv.length)
        fx.uv.forEach(([u, v], i) => {
          const x = u * size - px / 2
          const y = v * size - px / 2
          if (focused) ring(x, y, px, 1, multi ? 1 : 1.5)
          if (multi && i === 0) {
            ring(x, y, px, 3, 1.5)
            if (focused) ring(x, y, px, 1, 1.5)
          }
        })
      }
    }
  }, [preview, state, showFixtures, highlight])

  const corner = 'pointer-events-none absolute size-3.5 border-ink'
  return (
    // never wider than half the window, so it doesn't take over a single-column page
    <div
      data-hint="info"
      data-tip="The scene: the mask in grey with every fixture pixel in the colour it sends. A fixture's first pixel has a wider ring round it; a selected fixture has a ring round each pixel"
      className={`relative mx-auto aspect-square w-full max-w-[calc(var(--win-w,100vw)*0.5)] ${className ?? ''}`}
    >
      <canvas ref={canvasRef} width={764} height={764} className="block size-full bg-ground" />
      <div className={`${corner} top-2 left-2 border-t border-l`} />
      <div className={`${corner} top-2 right-2 border-t border-r`} />
      <div className={`${corner} bottom-2 left-2 border-b border-l`} />
      <div className={`${corner} right-2 bottom-2 border-r border-b`} />
    </div>
  )
}
