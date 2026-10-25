import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type DeviceRef, type SerialDevice, type Settings } from '../api'
import type { HintKind } from '../hints'
import { createSaveQueue } from '../saveQueue'
import type { IconName } from '../icons'
import { Icon } from './Icon'

/**
 * A panel: square, 1px hairline border, a header strip with an optional number ("01 / Macros").
 * ``bodyClassName`` replaces the default padding (e.g. "p-0" for grids drawn with 1px gaps).
 */
export function Section({
  title,
  index,
  children,
  right,
  className = '',
  bodyClassName = 'p-3',
  tip,
  id,
  icon,
}: {
  title: string
  index?: string
  icon?: IconName // in front of the title: an input or an output (item 67)
  children: ReactNode
  right?: ReactNode
  className?: string // e.g. "flex-1" to let the panel (and its content) stretch
  bodyClassName?: string
  tip?: string // footer tip for everything in the panel that has none of its own
  id?: string // for scrolling to it (the menu bar's Help → Keyboard shortcuts)
}) {
  return (
    <section id={id} data-tip={tip} className={`@container flex min-w-0 flex-col border border-edge bg-panel ${className}`}>
      <div className="flex h-[26px] flex-none items-center justify-between gap-2 border-b border-edge px-2.5 text-[11px]">
        <h2 className="lbl flex min-w-0 items-center font-medium">
          {index && <span className="flex-none font-mono whitespace-pre opacity-55">{index} / </span>}
          {icon && <Icon name={icon} label className="mr-1.5" />}
          <span className="truncate">{title}</span>
        </h2>
        <div className="lbl flex items-center gap-2 text-dim">{right}</div>
      </div>
      <div className={`flex min-h-0 flex-1 flex-col ${bodyClassName}`}>{children}</div>
    </section>
  )
}

/** One labelled form row; ``hint`` is the footer tip for the label and the controls. ``plain`` renders a div instead of a <label>, so clicking the label text
 * doesn't activate the first control (override rows, whose first control is the checkbox). */
export function Row({ label, children, hint, plain }: { label: string; children: ReactNode; hint?: string; plain?: boolean }) {
  const Tag = plain ? 'div' : 'label'
  return (
    <Tag data-tip={hint} data-row className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-2 py-0.5 text-[13px]">
      <span className="lbl truncate text-[11px] text-dim">{label}</span>
      {/* inputs shrink instead of overflowing into the next column */}
      <span className="flex min-w-0 items-center gap-2 [&>*]:min-w-0 [&>select]:max-w-full">{children}</span>
    </Tag>
  )
}

/** The universes of the app (DMX universe numbers, one per USB interface); every universe field offers these. */
export const UNIVERSES = [0, 1, 2, 3]

/** Art-Net port-addresses offered on the wire: universes 0–15 of net 0, sub-net 0. */
export const ARTNET_UNIVERSES = Array.from({ length: 16 }, (_, i) => i)

/**
 * Universe dropdown. A value outside UNIVERSES (an older file) is kept and shown as "not offered"
 * until another one is chosen; ``null`` (multi-edit with different values) shows "multiple".
 */
export function UniverseSelect({
  value,
  onChange,
  className = 'w-20',
  tip,
  options = UNIVERSES,
}: {
  value: number | null
  onChange: (v: number) => void
  className?: string
  tip?: string
  options?: number[]
}) {
  return (
    <select className={className} value={value === null ? 'multiple' : String(value)} data-tip={tip} onChange={(e) => onChange(Number(e.target.value))}>
      {value === null && (
        <option value="multiple" disabled>
          multiple
        </option>
      )}
      {value !== null && !options.includes(value) && <option value={value}>{value} (not offered)</option>}
      {options.map((u) => (
        <option key={u} value={u}>
          {u}
        </option>
      ))}
    </select>
  )
}

/**
 * Text field that keeps what you type and applies it on Enter (the field keeps focus) or when it loses focus; Escape puts
 * the saved value back. Nothing happens on the keystrokes in between, so a half-typed IP address restarts no output
 * (item 88). ``onCommit`` runs only when the text changed; if the parent doesn't change ``value`` (it refused the text),
 * the field shows the saved value again.
 */
export function TextInput({
  value,
  onCommit,
  className = 'w-full',
  tip,
  placeholder,
  maxLength,
  inputMode,
}: {
  value: string
  onCommit: (v: string) => void
  className?: string
  tip?: string
  placeholder?: string
  maxLength?: number
  inputMode?: 'numeric' | 'decimal' | 'text'
}) {
  const [text, setText] = useState(value)
  const [dirty, setDirty] = useState(false) // typed text that is not applied yet
  useEffect(() => {
    if (!dirty) setText(value)
  }, [value, dirty])
  const commit = () => {
    if (!dirty) return
    setDirty(false)
    if (text !== value) onCommit(text)
  }
  return (
    <input
      type="text"
      className={className}
      value={text}
      placeholder={placeholder}
      maxLength={maxLength}
      inputMode={inputMode}
      data-tip={tip}
      onChange={(e) => {
        setText(e.target.value)
        setDirty(true)
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        if (e.key === 'Escape') {
          setDirty(false)
          setText(value)
        }
      }}
    />
  )
}

/** Parse what a person types: "0.5", ".5", "-.5", "0,5" (comma as decimal separator). */
export function parseNumber(text: string): number | null {
  const t = text.trim().replace(',', '.')
  if (t === '' || t === '-' || t === '.' || t === '-.') return null
  const v = Number(t.startsWith('.') ? `0${t}` : t.startsWith('-.') ? `-0${t.slice(1)}` : t)
  return Number.isFinite(v) ? v : null
}

/** Float noise off: 0.1 + 0.2 → 0.3. */
const tidy = (v: number) => Number(v.toFixed(6))

/** Vertical right-drag distance (px) for one step. */
const DRAG_PX = 6

/**
 * Number field that keeps exactly what you type and applies it on Enter (the field keeps focus,
 * so you can type the next value right away) or when the field loses focus. Escape reverts.
 *
 * ↑ / ↓ and a vertical right-mouse drag change the value by ``step`` (with Shift: ``fineStep``)
 * and apply each change immediately. Defaults: integers 1 / 1, floats 0.1 / 0.01. Without a value
 * (empty, or "multiple values" in multi-edit) only typing works.
 */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  integer = false,
  step,
  fineStep,
  className = 'w-24 shrink',
  placeholder,
  disabled,
  tip,
}: {
  value: number | null | undefined
  onChange: (v: number) => void
  min?: number
  max?: number
  integer?: boolean
  step?: number
  fineStep?: number
  className?: string
  placeholder?: string
  disabled?: boolean
  tip?: string // footer tip for this field; without one the row's / panel's tip applies
}) {
  const coarse = step ?? (integer ? 1 : 0.1)
  const fine = fineStep ?? (integer ? 1 : 0.01)
  const shown = value == null ? '' : String(value)
  const [text, setText] = useState(shown)
  // true while the field holds typed text that is not applied yet
  const [dirty, setDirty] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const drag = useRef<{ id: number; lastY: number; acc: number; v: number } | null>(null)

  useEffect(() => {
    if (!dirty) setText(shown)
  }, [shown, dirty])

  const limit = (v: number) => {
    let r = integer ? Math.round(v) : tidy(v)
    if (min !== undefined) r = Math.max(min, r)
    if (max !== undefined) r = Math.min(max, r)
    return r
  }

  const apply = (v: number) => {
    setDirty(false)
    setText(String(v))
    if (v !== value) onChange(v)
  }

  /** Apply typed text; invalid text reverts. */
  const commit = () => {
    if (!dirty) return
    const v = parseNumber(text)
    if (v === null) {
      setDirty(false)
      setText(shown)
      return
    }
    apply(limit(v))
  }

  /** One step up (+1) or down (-1); the keys step from the typed text if it is valid. */
  const nudge = (from: number, dir: number, fineMode: boolean) => limit(from + dir * (fineMode ? fine : coarse))

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode="decimal"
      data-hint="number"
      data-tip={tip}
      className={`${className} font-mono ${value != null && !disabled ? 'cursor-ns-resize focus:cursor-text' : ''}`}
      value={text}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => {
        setDirty(true)
        setText(e.target.value)
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          commit()
          e.currentTarget.select() // stays focused: type the next value and Enter again
        } else if (e.key === 'Escape') {
          setDirty(false)
          setText(shown)
          e.currentTarget.blur()
        } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          e.preventDefault()
          if (value == null) return // nothing to step from (empty, or different values in multi-edit)
          const typed = dirty ? parseNumber(text) : null
          apply(nudge(typed ?? value, e.key === 'ArrowUp' ? 1 : -1, e.shiftKey))
        }
      }}
      onContextMenu={(e) => e.preventDefault()}
      onPointerDown={(e) => {
        if (e.button !== 2 || value == null || disabled) return
        e.preventDefault()
        e.currentTarget.setPointerCapture(e.pointerId)
        drag.current = { id: e.pointerId, lastY: e.clientY, acc: 0, v: value }
        setDirty(false)
      }}
      onPointerMove={(e) => {
        const d = drag.current
        if (!d || d.id !== e.pointerId) return
        d.acc += d.lastY - e.clientY // up = more
        d.lastY = e.clientY
        let v = d.v
        while (Math.abs(d.acc) >= DRAG_PX) {
          const dir = Math.sign(d.acc)
          v = nudge(v, dir, e.shiftKey)
          d.acc -= dir * DRAG_PX
        }
        if (v !== d.v) {
          d.v = v
          apply(v)
        }
      }}
      onPointerUp={(e) => {
        if (drag.current?.id === e.pointerId) drag.current = null
      }}
      onPointerCancel={() => (drag.current = null)}
    />
  )
}

/**
 * On/off switch (the one rounded element of the UI). Off: outlined track, dim knob on the left.
 * On: ink track with glow, dark knob on the right. ``mixed`` (multi-edit with different values)
 * puts the knob in the middle; clicking it switches on. Inside a <label> (e.g. Row) a click on the
 * label text toggles it too.
 */
export function Toggle({
  checked,
  onChange,
  label,
  mixed,
  disabled,
  tip,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
  mixed?: boolean
  disabled?: boolean
  tip?: string // footer tip for this switch; without one the row's / panel's tip applies
}) {
  const on = checked && !mixed
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        role="switch"
        data-hint="switch"
        data-tip={tip}
        aria-checked={mixed ? 'mixed' : checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(mixed ? true : !checked)}
        className={`relative h-[18px] w-[34px] flex-none rounded-full border transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40 ${
          on ? 'glow-on border-ink bg-ink' : 'border-edge bg-panel-2 hover:border-dim'
        }`}
      >
        <span
          className={`absolute top-1/2 size-3 -translate-y-1/2 rounded-full transition-[left] duration-100 ${
            on ? 'left-[18px] bg-ground' : mixed ? 'left-[10px] bg-dim' : 'left-[2px] bg-dim'
          }`}
        />
      </button>
      {label && <span className="lbl text-[11px]">{label}</span>}
    </span>
  )
}

/**
 * Small square checkbox in ink, for marking a value as overridden (Unreal-style override toggle).
 * ``mixed`` (multi-edit) shows a dash; clicking it switches all on.
 */
export function Check({ checked, mixed, onChange, tip, hint = 'override' }: { checked: boolean; mixed?: boolean; onChange: (v: boolean) => void; tip?: string; hint?: HintKind }) {
  const on = checked && !mixed
  return (
    <button
      type="button"
      role="checkbox"
      data-hint={hint}
      aria-checked={mixed ? 'mixed' : checked}
      data-tip={tip}
      onClick={() => onChange(mixed ? true : !checked)}
      className={`inline-flex size-[15px] flex-none items-center justify-center border font-mono text-[11px] leading-none ${
        on ? 'glow-on border-ink bg-ink text-ground' : 'border-edge text-ink hover:border-dim'
      }`}
    >
      {mixed ? '–' : on ? '✓' : ''}
    </button>
  )
}

export function Button({
  children,
  onClick,
  primary,
  disabled,
  tip,
  className = '',
}: {
  children: ReactNode
  onClick: () => void
  primary?: boolean
  disabled?: boolean
  tip?: string // footer tip: what the button does
  className?: string // e.g. shrink-0, for a button beside a field that has to give way
}) {
  return (
    <button
      disabled={disabled}
      data-tip={tip}
      onClick={onClick}
      className={`lbl h-8 px-3 text-[11px] font-medium whitespace-nowrap disabled:opacity-35 ${
        primary ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge bg-panel text-ink'
      } ${className}`}
    >
      {children}
    </button>
  )
}

export function StatusDot({ ok, label, error, tip, onClick }: { ok: boolean | null | undefined; label: string; error?: string | null; tip?: string; onClick?: () => void }) {
  // filled = OK, hollow = off, crossed = error; an error replaces the tip in the footer. With onClick it is a button (the
  // header's indicators open their Connections tab)
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag
      data-hint={onClick ? 'button' : 'info'}
      data-tip={error ? `${label}: ${error}` : tip}
      onClick={onClick}
      className={`lbl inline-flex flex-none items-center gap-1.5 text-[11px] whitespace-nowrap ${ok ? 'text-ink' : 'text-dim'} ${onClick ? 'hover:text-glow' : ''}`}
    >
      <span
        className={`relative inline-block size-[7px] ${ok ? 'dot-on' : 'border border-dim'} ${
          ok === false ? "after:absolute after:inset-[-2px] after:content-['×'] after:text-[9px] after:leading-[9px]" : ''
        }`}
      />
      {label}
    </Tag>
  )
}

export function deviceKey(d: DeviceRef | SerialDevice): string {
  return d.serial_number ? `sn:${d.serial_number}` : `port:${d.port ?? ''}`
}

export function DevicePicker({
  value,
  devices,
  onChange,
  tip = 'USB device of this output; chosen by serial number, so it survives a different USB port',
}: {
  value: DeviceRef
  devices: SerialDevice[]
  onChange: (d: DeviceRef) => void
  tip?: string
}) {
  const current = deviceKey(value)
  const known = devices.some((d) => deviceKey(d) === current)
  return (
    <select
      className="w-full"
      data-tip={tip}
      value={current}
      onChange={(e) => {
        const d = devices.find((x) => deviceKey(x) === e.target.value)
        onChange(
          d
            ? { serial_number: d.serial_number, vid: d.vid, pid: d.pid, description: d.description, port: d.port }
            : {},
        )
      }}
    >
      <option value="port:">— select a USB device —</option>
      {!known && current !== 'port:' && (
        <option value={current}>
          {value.description ?? 'configured device'} {value.serial_number ?? value.port} (not connected)
        </option>
      )}
      {devices.map((d) => (
        <option key={deviceKey(d) + d.port} value={deviceKey(d)}>
          {d.label}
        </option>
      ))}
    </select>
  )
}

/**
 * Load the settings. Every change is written and applied at once (item 88): ``commit(fn)`` changes the draft and queues
 * a PUT of the whole draft, the PUTs one after the other with the latest draft winning (saveQueue.ts). A PUT that fails
 * shows its message and loads what is saved.
 */
export function useSettings() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const draft = useRef<Settings | null>(null) // the latest draft: commits that follow each other before a render build on it
  const version = useRef(0) // counts the changes, so a late reload doesn't overwrite a newer one
  const queue = useRef(createSaveQueue((s: Settings) => api.put('/api/settings', s)))

  const show = useCallback((s: Settings) => {
    draft.current = s
    setSettings(s)
  }, [])

  const reload = useCallback(() => {
    const seen = version.current
    api.get<Settings>('/api/settings').then((s) => {
      if (seen === version.current) show(s)
    })
  }, [show])
  useEffect(reload, [reload])

  const commit = useCallback(
    (fn: (s: Settings) => void) => {
      if (!draft.current) return
      const next = structuredClone(draft.current)
      fn(next)
      version.current++
      show(next)
      queue.current.push(next).then((r) => {
        if (r.ok) return
        setMessage(String((r.error as Error)?.message ?? r.error))
        window.setTimeout(() => setMessage(null), 6000)
        version.current++ // what is shown is wrong now; the saved settings replace it
        reload()
      })
    },
    [show, reload],
  )

  /** Something else already saved this change to the server: mirror it in the draft without writing it again. */
  const applySaved = useCallback(
    (fn: (s: Settings) => void) => {
      if (!draft.current) return
      const next = structuredClone(draft.current)
      fn(next)
      show(next)
    },
    [show],
  )

  return { settings, commit, applySaved, reload, message }
}

export function SaveBar({
  dirty,
  save,
  reload,
  message,
  saveTip = 'Write the changes to settings.json; outputs and inputs restart with the new values',
}: {
  dirty: boolean
  save: () => void
  reload: () => void
  message: string | null
  saveTip?: string
}) {
  return (
    <div className="flex items-center gap-3">
      {message && <span className="lbl text-[11px] text-dim">{message}</span>}
      <Button onClick={reload} disabled={!dirty} tip="Discard the unsaved changes on this page and load what is saved">
        Revert
      </Button>
      <Button onClick={save} primary disabled={!dirty} tip={saveTip}>
        Save
      </Button>
    </div>
  )
}
