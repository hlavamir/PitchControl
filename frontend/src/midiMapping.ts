import type { DetectedHardware, MacroDef, MidiMappingEntry, MidiMode } from './api'

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
 *  the mapping's default in channel (then the row stays on "default"). With what the engine found out about the hardware
 *  (item 93) also the mode, and for an encoder its type; a mode the engine couldn't set stays as the row had it. */
export function learnedMapping(
  base: MidiMappingEntry,
  learned: { kind: 'cc' | 'note'; number: number; channel: number; shift: boolean; detected?: DetectedHardware },
  defaultChannel: number,
): MidiMappingEntry {
  const d = learned.detected
  return {
    ...base,
    type: learned.kind,
    number: learned.number,
    channel: learned.channel === defaultChannel ? null : learned.channel,
    // learned while holding the shift button: it is the 'with shift' variant
    shift: learned.shift ? 'on' : base.shift,
    ...(d?.mode ? { mode: d.mode } : {}),
    ...(d?.mode === 'relative' && d.encoder ? { encoder: d.encoder } : {}),
  }
}

/** The note a row shows after Learn: what the hardware was found to be, and what that did to the mode (null: nothing to show). */
export function detectedNote(d: DetectedHardware | undefined): string | null {
  if (!d) return null
  const what = d.kind === 'undecided' ? 'not sure what it is' : d.label
  return d.note ? `detected: ${what}, ${d.note}` : `detected: ${what}`
}

/** What the row says while Learn watches a control and wants more from it (item 93). */
export const LEARN_ASK: Record<'press_again' | 'turn' | 'turn_other', string> = {
  press_again: 'Press it once more',
  turn: 'Turn it a bit',
  turn_other: 'Turn it the other way',
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
