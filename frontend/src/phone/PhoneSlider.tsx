import { useRef, useState, type PointerEvent } from 'react'
import type { MacroDef } from '../api'
import { SEGMENTS, formatValue, segmentStyle, type ColorTrack } from '../components/MacroControl'
import { cellBox, spreadWithin } from '../components/deviceSnap'
import { useDeviceSnap } from '../components/useDeviceSnap'

// a drag only starts after the finger moved this far sideways: a vertical swipe scrolls the page instead
const SLOP_PX = 8

/**
 * A fader of the phone layout: a full-width row with a horizontal segment bar. Drag sideways anywhere on the
 * row; the change is relative to where the finger started (no jump on touch), the whole row width is the full
 * range. A vertical swipe scrolls the page (touch-action: pan-y). Hue and saturation go out on release.
 */
export function PhoneSlider({
  def,
  value,
  applied,
  setMacro,
  colorTrack,
  pending,
  index,
  disabled,
}: {
  def: MacroDef
  value: number
  applied?: number
  setMacro: (name: string, value: number) => void
  colorTrack?: ColorTrack
  pending?: boolean
  index?: number
  disabled?: boolean
}) {
  const [dragValue, setDragValue] = useState<number | null>(null)
  const drag = useRef<{ id: number; x: number; y: number; startValue: number; width: number; active: boolean; frame: number; out: number | null } | null>(null)
  const current = dragValue ?? value
  const track = useRef<HTMLDivElement>(null)
  // the segments and the colour scale in whole device pixels, the leftover split at the two ends (item 81); null until measured
  const snap = useDeviceSnap(track, SEGMENTS, 'x', 1, { leftover: 'split' })
  const engineValue = applied ?? value
  const notApplied = Boolean(pending) || (def.deferred && dragValue !== null && Math.abs(dragValue - engineValue) > 1e-6)

  const send = () => {
    const d = drag.current
    if (!d) return
    d.frame = 0
    if (d.out !== null) setMacro(def.name, d.out)
    d.out = null
  }

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (disabled || (e.pointerType === 'mouse' && e.button !== 0)) return
    const rect = e.currentTarget.getBoundingClientRect()
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, startValue: value, width: Math.max(rect.width - 24, 120), active: false, frame: 0, out: null }
  }
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    const dx = e.clientX - d.x
    if (!d.active) {
      if (Math.abs(dx) < SLOP_PX) return
      if (Math.abs(e.clientY - d.y) > Math.abs(dx)) {
        drag.current = null // more up / down than sideways: the page scrolls
        return
      }
      d.active = true
      d.x = e.clientX
      e.currentTarget.setPointerCapture(e.pointerId)
      setDragValue(d.startValue)
      return
    }
    const next = Math.min(1, Math.max(0, d.startValue + dx / d.width))
    setDragValue(next)
    d.out = next
    if (!def.deferred && !d.frame) d.frame = requestAnimationFrame(send)
  }
  const onPointerUp = () => {
    const d = drag.current
    if (d?.frame) cancelAnimationFrame(d.frame)
    if (d?.active) send()
    drag.current = null
    setDragValue(null)
  }
  // the browser took the gesture (a scroll): nothing more is sent, what was sent stays
  const onPointerCancel = () => {
    const d = drag.current
    if (d?.frame) cancelAnimationFrame(d.frame)
    drag.current = null
    setDragValue(null)
  }

  const level = current * SEGMENTS
  const top = Math.ceil(level) - 1
  const appliedLevel = engineValue * SEGMENTS
  const lo = Math.floor(Math.min(level, appliedLevel))
  const hi = Math.ceil(Math.max(level, appliedLevel))
  const active = dragValue !== null
  const hue = snap && colorTrack ? spreadWithin(snap, colorTrack.steps.length, 0) : null

  return (
    <div
      role="slider"
      aria-label={def.label}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={current}
      aria-disabled={disabled || undefined}
      className={`flex flex-col gap-2 bg-panel px-3 pt-2.5 pb-3 select-none [touch-action:pan-y] ${active ? 'glow-sel' : ''} ${
        notApplied ? 'outline outline-1 outline-offset-[-4px] outline-dashed outline-ink' : ''
      }`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="flex items-baseline gap-2">
        {index !== undefined && <span className={`font-mono text-[13px] opacity-60 ${disabled ? 'text-dim' : ''}`}>{String(index).padStart(2, '0')}</span>}
        <span className={`lbl min-w-0 flex-1 truncate text-[13px] ${disabled ? 'text-dim' : ''}`}>{def.label}</span>
        {colorTrack && !disabled && (
          <span className="size-3 flex-none self-center" style={{ background: colorTrack.colorAt(current), boxShadow: `0 0 0 1px #0f1011, 0 0 8px ${colorTrack.colorAt(current)}` }} />
        )}
        {disabled ? (
          <span className="lbl text-[12px] text-dim">no fixtures</span>
        ) : (
          <span className="text-glow w-[4.5rem] text-right font-mono text-[20px] leading-none tabular-nums">{formatValue(def, current)}</span>
        )}
      </div>
      <div ref={track} className={`h-5 ${snap ? 'relative' : 'flex'} ${disabled ? 'hatch opacity-60' : ''}`}>
        {!disabled &&
          Array.from({ length: SEGMENTS }, (_, s) => {
            // the segments run left to right; the seam is on the left edge instead of the top
            const st = segmentStyle(Math.max(0, Math.min(1, level - s)), s === top || active, notApplied && s >= lo && s < hi, snap?.seam, 'x')
            return <div key={s} className={snap ? undefined : 'flex-1'} style={snap ? { ...st, ...cellBox(snap, s, 'x') } : st} />
          })}
      </div>
      {colorTrack && !disabled && (
        // the colour scale is always shown on a phone (there is no hover); under the segments, filling exactly their extent
        <div className={`h-1 ${hue ? 'relative' : 'flex'}`}>
          {colorTrack.steps.map((c, i) => (
            <div key={i} className={hue ? undefined : 'flex-1'} style={{ background: c, ...(hue && cellBox(hue, i, 'x')) }} />
          ))}
        </div>
      )}
    </div>
  )
}
