import { describe, expect, it } from 'vitest'
import type { MacroDef, MidiMappingEntry } from './api'
import { LEARN_ASK, channelOf, clashes, deadMappings, defaultMode, detectedNote, learnedMapping, modesFor, newMapping, outChannelOf, overlaps } from './midiMapping'

// the cases follow backend/tests/test_midi.py: the editor's rules have to agree with the engine's

const mapping = (over: Partial<MidiMappingEntry>) => newMapping({ macro: 'Strobo', ...over })
const def = (kind: MacroDef['kind']) => ({ name: 'x', kind }) as MacroDef

describe('behaviours that fit a macro', () => {
  it('a fader can be a fader or an encoder', () => {
    expect(modesFor(def('fader'))).toEqual(['absolute', 'relative'])
    expect(defaultMode(def('fader'))).toBe('absolute')
  })
  it('a switch or a hold button can toggle, be held or be pressed', () => {
    expect(modesFor(def('toggle'))).toEqual(['toggle', 'momentary', 'trigger'])
    expect(modesFor(def('momentary'))).toEqual(['toggle', 'momentary', 'trigger'])
    expect(defaultMode(def('toggle'))).toBe('toggle')
    expect(defaultMode(def('momentary'))).toBe('momentary')
  })
  it('buttons and radio macros are only pressed', () => {
    expect(modesFor(def('button'))).toEqual(['trigger'])
    expect(modesFor(def('radio'))).toEqual(['trigger'])
    expect(defaultMode(def('radio'))).toBe('trigger')
  })
  it('a new mapping starts with the defaults of the file format', () => {
    expect(newMapping({ number: 5, macro: 'Hue A' })).toMatchObject({ type: 'cc', number: 5, macro: 'Hue A', mode: 'absolute', channel: null, page: null, shift: null, invert: false, sensitivity: 1 })
  })
})

describe('which channel a mapping listens on', () => {
  it("its own, else the controller's", () => {
    expect(channelOf(mapping({ channel: null }), 13)).toBe(13)
    expect(channelOf(mapping({ channel: 2 }), 13)).toBe(2)
  })
})

describe('the default out channel', () => {
  it('is the in channel until one is set (item 90)', () => {
    expect(outChannelOf({ channel: 13 })).toBe(13)
    expect(outChannelOf({ channel: 13, channel_out: null })).toBe(13)
    expect(outChannelOf({ channel: 13, channel_out: 2 })).toBe(2)
  })
})

describe('what Learn makes of a row (item 90)', () => {
  const row = mapping({ number: 0, channel: 7, page: 'dimmers', invert: true })
  it('takes the control and kind, and keeps the rest of the row', () => {
    expect(learnedMapping(row, { kind: 'note', number: 36, channel: 13, shift: false }, 13)).toMatchObject({ type: 'note', number: 36, macro: 'Strobo', page: 'dimmers', invert: true })
  })
  it('leaves the row on "default" when the message came on the default in channel', () => {
    expect(learnedMapping(row, { kind: 'cc', number: 5, channel: 13, shift: false }, 13).channel).toBeNull()
  })
  it('gives the row its own channel when the message came on another one', () => {
    expect(learnedMapping(mapping({ channel: null }), { kind: 'cc', number: 5, channel: 4, shift: false }, 13).channel).toBe(4)
  })
  it('a control learned with shift held is the "with shift" row; otherwise the shift setting stays', () => {
    expect(learnedMapping(row, { kind: 'cc', number: 5, channel: 13, shift: true }, 13).shift).toBe('on')
    expect(learnedMapping(mapping({ shift: 'off' }), { kind: 'cc', number: 5, channel: 13, shift: false }, 13).shift).toBe('off')
  })
})

describe('what Learn sets from the hardware it found (item 93)', () => {
  const found = { kind: 'cc', number: 5, channel: 13, shift: false } as const
  const detected = (over: Partial<NonNullable<Parameters<typeof learnedMapping>[1]['detected']>>) => ({ kind: 'gate' as const, label: 'gate button', mode: null, encoder: null, note: '', ...over })
  it('sets the mode the engine chose', () => {
    expect(learnedMapping(mapping({ mode: 'toggle' }), { ...found, detected: detected({ mode: 'momentary' }) }, 13).mode).toBe('momentary')
  })
  it('sets the encoder type with relative, and leaves it alone otherwise', () => {
    const encoder = learnedMapping(mapping({ mode: 'absolute' }), { ...found, detected: detected({ kind: 'encoder', label: 'encoder (offset 64)', mode: 'relative', encoder: 'offset_64' }) }, 13)
    expect(encoder).toMatchObject({ mode: 'relative', encoder: 'offset_64' })
    expect(learnedMapping(mapping({ encoder: 'sign_bit' }), { ...found, detected: detected({ mode: 'toggle', encoder: 'offset_64' }) }, 13).encoder).toBe('sign_bit')
  })
  it('keeps the mode the row had when the engine set none, or found nothing', () => {
    expect(learnedMapping(mapping({ mode: 'absolute' }), { ...found, detected: detected({ note: 'a gate button on a fader, mode kept' }) }, 13).mode).toBe('absolute')
    expect(learnedMapping(mapping({ mode: 'trigger' }), found, 13).mode).toBe('trigger')
  })
  it('tells the user what was found, and why a mode was kept', () => {
    expect(detectedNote(detected({}))).toBe('detected: gate button')
    expect(detectedNote(detected({ kind: 'encoder', label: 'encoder (offset 64)' }))).toBe('detected: encoder (offset 64)')
    expect(detectedNote(detected({ kind: 'trigger', label: 'trigger button', note: "the button can't be held, it only fires" }))).toBe("detected: trigger button, the button can't be held, it only fires")
    expect(detectedNote(detected({ kind: 'undecided', label: 'unclear', note: "couldn't tell what it sends, mode kept" }))).toContain('not sure')
    expect(detectedNote(undefined)).toBeNull()
  })
  it('has words for what Learn asks', () => {
    expect(LEARN_ASK.press_again).toBe('Press it once more')
    expect(LEARN_ASK.turn).toBe('Turn it a bit')
  })
})

describe('overlap', () => {
  const a = mapping({ number: 5 })
  it('needs the same kind and number', () => {
    expect(overlaps(a, mapping({ number: 5 }), 1)).toBe(true)
    expect(overlaps(a, mapping({ number: 6 }), 1)).toBe(false)
    expect(overlaps(a, mapping({ number: 5, type: 'note' }), 1)).toBe(false)
  })
  it('compares the channels after the controller default is applied', () => {
    expect(overlaps(a, mapping({ number: 5, channel: 13 }), 13)).toBe(true) // the same channel, said once explicitly
    expect(overlaps(a, mapping({ number: 5, channel: 2 }), 13)).toBe(false)
  })
  it('"any" page or shift overlaps with everything, two settings only when equal', () => {
    expect(overlaps(mapping({ number: 5, page: 'dimmers' }), a, 1)).toBe(true)
    expect(overlaps(mapping({ number: 5, page: 'dimmers' }), mapping({ number: 5, page: 'general' }), 1)).toBe(false)
    expect(overlaps(mapping({ number: 5, shift: 'on' }), mapping({ number: 5, shift: 'off' }), 1)).toBe(false)
    expect(overlaps(mapping({ number: 5, shift: 'on' }), mapping({ number: 5, shift: 'on' }), 1)).toBe(true)
  })
  it('a page-only and a shift-only mapping overlap (item 11: the shift one wins, the app only warns)', () => {
    expect(overlaps(mapping({ number: 5, page: 'general' }), mapping({ number: 5, shift: 'on' }), 1)).toBe(true)
  })
  it('does not compare the shift button with the macros (that is the "never fires" case)', () => {
    expect(overlaps(a, mapping({ number: 5, mode: 'shift', macro: null }), 1)).toBe(false)
  })
  it('agrees with the engine: they overlap exactly when some page and shift state fits both', () => {
    const pages = [null, 'general', 'dimmers'] as const
    const shifts = [null, 'on', 'off'] as const
    for (const p1 of pages) for (const s1 of shifts) for (const p2 of pages) for (const s2 of shifts) {
      const x = mapping({ number: 5, page: p1, shift: s1 })
      const y = mapping({ number: 5, page: p2, shift: s2 })
      const fits = (m: MidiMappingEntry, page: string, shift: string) => (m.page == null || m.page === page) && (m.shift == null || m.shift === shift) // midi_in.py `_pick`
      const both = ['general', 'dimmers'].some((page) => ['on', 'off'].some((shift) => fits(x, page, shift) && fits(y, page, shift)))
      expect(overlaps(x, y, 1), `${p1}/${s1} and ${p2}/${s2}`).toBe(both)
    }
  })
})

describe('controls used twice', () => {
  it('names the others on an overlapping control, both ways round', () => {
    const ms = [mapping({ number: 5 }), mapping({ number: 6 }), mapping({ number: 5, page: 'dimmers' })]
    const found = clashes(ms, 1)
    expect(found.get(0)).toEqual([2])
    expect(found.get(2)).toEqual([0])
    expect(found.has(1)).toBe(false)
  })
  it('nothing for mappings that never apply together', () => {
    expect(clashes([mapping({ number: 5, shift: 'on' }), mapping({ number: 5, shift: 'off' })], 1).size).toBe(0)
  })
})

describe('a mapping on the shift button', () => {
  const shift = mapping({ number: 44, mode: 'shift', macro: null })
  it('never fires: both rows say so', () => {
    const dead = deadMappings([mapping({ number: 44 }), shift, mapping({ number: 45 })], 1)
    expect(dead.get(0)).toBe('self')
    expect(dead.get(1)).toEqual([0])
    expect(dead.has(2)).toBe(false)
  })
  it('the shift button lists every mapping it shadows', () => {
    const dead = deadMappings([mapping({ number: 44, macro: 'Hue A' }), shift, mapping({ number: 44, macro: 'Hue B', page: 'dimmers' })], 1)
    expect(dead.get(1)).toEqual([0, 2])
  })
  it('on another channel the control is another one', () => {
    expect(deadMappings([mapping({ number: 44, channel: 2 }), shift], 1).size).toBe(0)
    expect(deadMappings([mapping({ number: 44, channel: 13 }), shift], 13).size).toBe(2)
  })
})
