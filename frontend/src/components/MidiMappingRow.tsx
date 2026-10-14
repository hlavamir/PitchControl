import type { MacroDef, MidiMappingEntry, MidiMode } from '../api'
import { MODE_LABEL, MODE_TIP, defaultMode, modesFor } from '../midiMapping'
import { NumberInput } from './forms'

/** One row of the mapping editor: a macro and the control that drives it (or an empty row to take one). */
export function MidiMappingRow({
  label,
  hint,
  index: i,
  mapping: m,
  def: d,
  template,
  controllerChannel,
  waiting,
  clashes: others,
  deadText,
  highlighted,
  patch,
  remove,
  onAdd,
  onLearn,
}: {
  label: string
  hint: string | undefined
  /** the index in the controller's mappings; null: an empty row, nothing is mapped yet */
  index: number | null
  mapping: MidiMappingEntry | null
  def: MacroDef | null
  /** what a mapping made from this row starts as */
  template: MidiMappingEntry
  controllerChannel: number
  /** Learn is waiting for a control for this row */
  waiting: boolean
  /** the labels of the other macros on a control that overlaps this one's */
  clashes: string[] | undefined
  deadText: string | undefined
  highlighted: boolean
  patch: (index: number, change: Partial<MidiMappingEntry>) => void
  remove: (index: number) => void
  /** the number typed into an empty row: the mapping is created from the template */
  onAdd: (number: number) => void
  /** start Learn for this row, or cancel it when it is waiting */
  onLearn: () => void
}) {
  const special = m?.mode === 'shift' || template.mode === 'shift'
  const modes = d ? modesFor(d) : []
  return (
    <div
      data-tip={hint}
      className={`grid min-w-[880px] grid-cols-[minmax(11rem,1.4fr)_8.6rem_11.6rem_9.5rem_5.5rem_5.5rem_minmax(4rem,auto)_1.5rem] items-center gap-x-2 border-b border-edge/50 px-2 py-[3px] text-[12px] ${
        highlighted ? 'bg-panel-2' : ''
      }`}
    >
      <span className="truncate" title={label}>
        {label}
        {deadText && (
          <span className="ml-1.5 text-[10px] text-ink" data-hint="info" data-tip="A shift button always wins on its control, so nothing else mapped to the same CC / note and channel ever fires. Give the macro another control or change the shift button">
            ⚠ {deadText}
          </span>
        )}
        {others && (
          <span className="ml-1.5 text-[10px] text-ink" data-hint="info" data-tip={`Also used by ${others.join(', ')} where the page and shift settings overlap ("any" overlaps with everything). When both apply, the one with a shift setting wins, then the one with a page setting; with the same settings the first in the list`}>
            ⚠ also {others[0]}
            {others.length > 1 ? ` +${others.length - 1}` : ''}
          </span>
        )}
      </span>
      <span className="flex items-center gap-1">
        <select value={m?.type ?? 'cc'} disabled={!m} onChange={(e) => i !== null && patch(i, { type: e.target.value as 'cc' | 'note' })} data-tip="Which kind of MIDI message: a controller (CC) or a note">
          <option value="cc">CC</option>
          <option value="note">Note</option>
        </select>
        <NumberInput
          value={m?.number ?? null}
          integer
          min={0}
          max={127}
          className="w-14"
          placeholder="–"
          tip="CC or note number (0–127)"
          onChange={(v) => (i !== null ? patch(i, { number: v }) : onAdd(v))}
        />
      </span>
      <span className="flex items-center gap-1">
        <select
          value={m?.channel ?? ''}
          disabled={!m}
          className="w-[4.6rem]"
          onChange={(e) => i !== null && patch(i, { channel: e.target.value ? Number(e.target.value) : null })}
          data-tip={`MIDI channel of this control: ${controllerChannel} unless you pick another one (some controllers use a channel per track)`}
        >
          <option value="">ch {controllerChannel}</option>
          {Array.from({ length: 16 }, (_, c) => (
            <option key={c} value={c + 1}>
              ch {c + 1}
            </option>
          ))}
        </select>
        <button
          className={`lbl h-6 px-2 text-[10px] whitespace-nowrap ${waiting ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge text-ink'}`}
          data-tip={waiting ? 'Waiting for a message: move or press the control (click again to cancel)' : 'Learn: then move or press the control on the controller'}
          onClick={onLearn}
        >
          {waiting ? 'move it…' : 'Learn'}
        </button>
      </span>
      {special ? (
        <span className="lbl text-[10px] text-dim">{MODE_LABEL[(m?.mode ?? template.mode) as MidiMode]}</span>
      ) : (
        <select
          value={m?.mode ?? (d ? defaultMode(d) : 'absolute')}
          disabled={!m || modes.length < 2}
          onChange={(e) => i !== null && patch(i, { mode: e.target.value as MidiMode })}
          data-tip={m ? MODE_TIP[m.mode] : 'How the control acts on this macro'}
        >
          {(m && !modes.includes(m.mode) ? [m.mode, ...modes] : modes).map((x) => (
            <option key={x} value={x}>
              {MODE_LABEL[x]}
            </option>
          ))}
        </select>
      )}
      {special ? (
        <span />
      ) : (
        <select
          value={m?.page ?? ''}
          disabled={!m}
          onChange={(e) => i !== null && patch(i, { page: (e.target.value || null) as MidiMappingEntry['page'] })}
          data-tip="On which control page the control does this: the same fader can drive other macros on the other page"
        >
          <option value="">any page</option>
          <option value="general">General</option>
          <option value="dimmers">Dimmers</option>
        </select>
      )}
      {special ? (
        <span />
      ) : (
        <select
          value={m?.shift ?? ''}
          disabled={!m}
          onChange={(e) => i !== null && patch(i, { shift: (e.target.value || null) as MidiMappingEntry['shift'] })}
          data-tip="Whether the shift button must be held (or must not be) for the control to do this"
        >
          <option value="">shift: any</option>
          <option value="off">no shift</option>
          <option value="on">with shift</option>
        </select>
      )}
      <span className="flex items-center gap-1.5">
        {m && !special && (
          <label className="lbl flex items-center gap-1 text-[10px] text-dim" data-tip="Flip the direction: 127 becomes 0">
            <input type="checkbox" checked={m.invert} onChange={(e) => i !== null && patch(i, { invert: e.target.checked })} />
            inv
          </label>
        )}
        {m?.mode === 'relative' && (
          <>
            <select
              value={m.encoder}
              onChange={(e) => i !== null && patch(i, { encoder: e.target.value as MidiMappingEntry['encoder'] })}
              data-tip="How the encoder sends its steps: most controllers use two's complement (127 = one step down); try the others if it turns the wrong way or jumps"
            >
              <option value="twos_complement">2's compl.</option>
              <option value="sign_bit">sign bit</option>
              <option value="offset_64">offset 64</option>
            </select>
            <NumberInput value={m.sensitivity} min={0.05} className="w-14" max={127} tip="Steps per message: 1 = 127 steps cover the whole range" onChange={(v) => i !== null && patch(i, { sensitivity: v })} />
          </>
        )}
      </span>
      <button
        className="text-dim hover:text-ink disabled:opacity-30"
        disabled={!m}
        data-tip="Remove this control from the macro"
        onClick={() => i !== null && remove(i)}
        aria-label="Remove"
      >
        ×
      </button>
    </div>
  )
}
