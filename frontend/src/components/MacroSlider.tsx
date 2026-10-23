import { useRef, useState, type PointerEvent } from 'react'
import type { MacroDef } from '../api'
import { macroHint, macroTip } from '../hints'
import { SegmentBar } from './BandMeter'
import { formatValue } from './MacroControl'

/**
 * A macro as a horizontal fader, one row (Mask Curve under the scene view): the label, a segmented bar with a tick at the
 * middle, the value. The whole row is the control, as with the vertical faders: drag sideways (relative, no jump on a
 * click), Shift for fine control, double-click to reset; the arrow keys go through the General page's navigation.
 */
export function MacroSlider({ def, value, setMacro, selected, onSelect }: { def: MacroDef; value: number; setMacro: (name: string, value: number) => void; selected?: boolean; onSelect?: () => void }) {
  const [dragValue, setDragValue] = useState<number | null>(null)
  const drag = useRef<{ startX: number; startValue: number; last: number; width: number; fine: boolean; frame: number; pending: number | null } | null>(null)
  const current = dragValue ?? value

  const send = () => {
    const d = drag.current
    if (!d) return
    d.frame = 0
    if (d.pending !== null) setMacro(def.name, d.pending)
    d.pending = null
  }

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    onSelect?.()
    e.currentTarget.setPointerCapture(e.pointerId)
    const width = Math.max(e.currentTarget.querySelector('[data-bar]')?.getBoundingClientRect().width ?? 0, 40)
    drag.current = { startX: e.clientX, startValue: value, last: value, width, fine: e.shiftKey, frame: 0, pending: null }
    setDragValue(value)
  }

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    if (e.shiftKey !== d.fine) {
      // re-anchor when Shift is pressed or released so the value does not jump
      d.fine = e.shiftKey
      d.startX = e.clientX
      d.startValue = d.last
    }
    const next = Math.min(1, Math.max(0, d.startValue + ((e.clientX - d.startX) / d.width) * (d.fine ? 0.1 : 1)))
    d.last = next
    d.pending = next
    setDragValue(next)
    if (!d.frame) d.frame = requestAnimationFrame(send)
  }

  const onPointerUp = () => {
    const d = drag.current
    if (d?.frame) cancelAnimationFrame(d.frame)
    send()
    drag.current = null
    setDragValue(null)
  }

  return (
    <div
      role="slider"
      aria-label={def.label}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={current}
      className={`mt-2.5 flex cursor-ew-resize touch-none items-center gap-2.5 px-1 py-1.5 text-[11px] select-none ${selected ? 'glow-sel' : 'glow-hover'}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={() => setMacro(def.name, def.default)}
      data-hint={macroHint(def)}
      data-tip={macroTip(def)}
    >
      <span className="lbl w-[5.25rem] flex-none whitespace-nowrap">{def.label}</span>
      <div data-bar className="relative flex flex-1">
        <SegmentBar value={current} />
        <span className="pointer-events-none absolute -bottom-1.5 left-1/2 h-1.5 w-px bg-ink opacity-60" />
      </div>
      <span className="w-10 text-right font-mono text-[13px]">{formatValue(def, current)}</span>
    </div>
  )
}
