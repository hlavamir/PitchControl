import type { MacroDef, MidiMappingEntry, MidiMode } from './api'

// The rules of the MIDI mapping editor that must agree with the engine (backend/src/pitchcontrol/io/midi_in.py), kept
// apart from the component so that they can be tested (midiMapping.test.ts).

export const MODE_LABEL: Record<MidiMode, string> = {
  absolute: 'Fader / knob',
  relative: 'Encoder (relative)',
  toggle: 'Button: toggle',
  momentary: 'Button: while held',
  trigger: 'Button: press',
  shift: 'Shift',
}
export const MODE_TIP: Record<MidiMode, string> = {
  absolute: 'The control position is the value (with value scaling: nothing jumps when the fader and the value differ)',
  relative: 'An endless encoder: every step turns the value up or down',
  toggle: 'Every press flips the switch on or off',
  momentary: 'On while the button is held; also right for buttons that toggle themselves on the controller',
  trigger: 'One press does it (scene buttons, the masks A–D)',
  shift: '',
}

/** The behaviours that make sense for a macro. */
export function modesFor(d: MacroDef): MidiMode[] {
  if (d.kind === 'fader') return ['absolute', 'relative']
  if (d.kind === 'toggle' || d.kind === 'momentary') return ['toggle', 'momentary', 'trigger']
  return ['trigger']
}

export const defaultMode = (d: MacroDef): MidiMode => (d.kind === 'fader' ? 'absolute' : d.kind === 'toggle' ? 'toggle' : d.kind === 'momentary' ? 'momentary' : 'trigger')

export const newMapping = (over: Partial<MidiMappingEntry>): MidiMappingEntry => ({
  type: 'cc',
  number: 0,
  macro: null,
  mode: 'absolute',
  channel: null,
  page: null,
  shift: null,
  invert: false,
  encoder: 'twos_complement',
  sensitivity: 1,
  note: '',
  ...over,
})

/** The MIDI channel a mapping listens on: its own, else the controller's. */
export const channelOf = (m: MidiMappingEntry, controllerChannel: number) => m.channel ?? controllerChannel

/** The default out channel: its own, else the in channel (item 90; LED feedback will use it, nothing does yet). */
export const outChannelOf = (c: { channel: number; channel_out?: number | null }) => c.channel_out ?? c.channel

/** The row Learn makes (item 90): the control and kind that arrived, and its own channel only when the message was not on
 *  the mapping's default in channel (then the row stays on "default"). Everything else of the row is kept. */
export function learnedMapping(base: MidiMappingEntry, learned: { kind: 'cc' | 'note'; number: number; channel: number; shift: boolean }, defaultChannel: number): MidiMappingEntry {
  return {
    ...base,
    type: learned.kind,
    number: learned.number,
    channel: learned.channel === defaultChannel ? null : learned.channel,
    // learned while holding the shift button: it is the 'with shift' variant
    shift: learned.shift ? 'on' : base.shift,
  }
}

/** Two mappings on the same control (kind, number, channel) whose page and shift settings can both apply at once ("any"
 *  overlaps with everything). The shift button is not compared with the macros: see ``deadMappings``. */
export const overlaps = (a: MidiMappingEntry, b: MidiMappingEntry, controllerChannel: number) =>
  a.type === b.type &&
  a.number === b.number &&
  channelOf(a, controllerChannel) === channelOf(b, controllerChannel) &&
  (!a.page || !b.page || a.page === b.page) &&
  (!a.shift || !b.shift || a.shift === b.shift) &&
  (a.mode === 'shift') === (b.mode === 'shift')

/** For every mapping that shares its control with others: the indices of those others. When both apply the engine takes
 *  shift first, then page (shift and page > shift only > page only > neither); only identical settings tie, and the first
 *  in the list wins. */
export function clashes(mappings: MidiMappingEntry[], controllerChannel: number): Map<number, number[]> {
  const out = new Map<number, number[]>()
  mappings.forEach((a, i) =>
    mappings.forEach((b, j) => {
      if (i !== j && overlaps(a, b, controllerChannel)) out.set(i, [...(out.get(i) ?? []), j])
    }),
  )
  return out
}

/** A mapping on the same control (kind, number, channel) as a shift button never fires, the shift button wins. Maps the
 *  index of such a mapping to ``'self'``, and the index of the shift button to the indices of the mappings it shadows. */
export function deadMappings(mappings: MidiMappingEntry[], controllerChannel: number): Map<number, 'self' | number[]> {
  const out = new Map<number, 'self' | number[]>()
  mappings.forEach((a, i) =>
    mappings.forEach((b, j) => {
      if (i === j || b.mode !== 'shift' || a.mode === 'shift') return
      if (a.type !== b.type || a.number !== b.number || channelOf(a, controllerChannel) !== channelOf(b, controllerChannel)) return
      out.set(i, 'self')
      const shadowed = out.get(j)
      out.set(j, [...(Array.isArray(shadowed) ? shadowed : []), i])
    }),
  )
  return out
}
