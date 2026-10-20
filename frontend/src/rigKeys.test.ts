import { describe, expect, it } from 'vitest'
import type { FieldBox } from './fieldNav'
import { editKind, navStep, rigKeyAction, stepSelection, toggleCurrent, type KeyContext, type KeyInfo, type ListCursor, type NavState } from './rigKeys'

const key = (k: string, extra: Partial<KeyInfo> = {}): KeyInfo => ({ key: k, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false, ...extra })
const list: KeyContext = { typing: false, onList: true, zone: 'list', inDetails: false }
const details: KeyContext = { typing: false, onList: false, zone: 'details', inDetails: false }
const act = (k: string, extra: Partial<KeyInfo> = {}, ctx: Partial<KeyContext> = {}) => rigKeyAction(key(k, extra), { ...list, ...ctx })
const inDetails = (k: string, extra: Partial<KeyInfo> = {}, ctx: Partial<KeyContext> = {}) => rigKeyAction(key(k, extra), { ...details, ...ctx })
const typing = { typing: true, onList: false }

// shown in this order (the indices are the fixtures' positions in the file, not in the list)
const ORDER = [3, 0, 4, 1, 2]
const cur = (selected: number[], anchor: number | null, cursor: number | null = selected[selected.length - 1] ?? null): ListCursor => ({ selected, anchor, cursor })
const sorted = (s: ListCursor) => [...s.selected].sort((a, b) => a - b)

describe('rigKeyAction, on the list', () => {
  it('W / S and ↑ / ↓ move, up and down', () => {
    expect(act('w')).toEqual({ kind: 'move', step: -1, shift: false })
    expect(act('s')).toEqual({ kind: 'move', step: 1, shift: false })
    expect(act('ArrowUp')).toEqual({ kind: 'move', step: -1, shift: false })
    expect(act('ArrowDown')).toEqual({ kind: 'move', step: 1, shift: false })
  })

  it('Shift with them extends (and the capital letter is the same key)', () => {
    expect(act('ArrowDown', { shiftKey: true })).toEqual({ kind: 'move', step: 1, shift: true })
    expect(act('ArrowUp', { shiftKey: true })).toEqual({ kind: 'move', step: -1, shift: true })
    expect(act('W', { shiftKey: true })).toEqual({ kind: 'move', step: -1, shift: true })
    expect(act('S', { shiftKey: true })).toEqual({ kind: 'move', step: 1, shift: true })
  })

  it('Space toggles the current fixture', () => {
    expect(act(' ')).toEqual({ kind: 'toggle' })
  })

  it('Space stays with a focused switch or button, and does not repeat', () => {
    expect(act(' ', {}, { onList: false })).toBeNull()
    expect(act(' ', { repeat: true })).toBeNull()
  })

  it('D and → go into the details (which only highlights the first field, see navStep)', () => {
    expect(act('d')).toEqual({ kind: 'details' })
    expect(act('D', { shiftKey: true })).toEqual({ kind: 'details' })
    expect(act('ArrowRight')).toEqual({ kind: 'details' })
  })

  it('A and Esc go back to the list', () => {
    expect(act('a')).toEqual({ kind: 'list' })
    expect(act('Escape')).toEqual({ kind: 'list' })
  })

  it('⏎ does nothing new, and other keys are not ours', () => {
    expect(act('Enter')).toBeNull()
    expect(act('ArrowLeft')).toBeNull()
    expect(act('q')).toBeNull()
    expect(act('5')).toBeNull()
  })

  it('a shortcut with Ctrl, Cmd or Alt is not ours', () => {
    for (const mod of ['ctrlKey', 'metaKey', 'altKey'] as const) {
      expect(act('s', { [mod]: true })).toBeNull()
      expect(act('ArrowDown', { [mod]: true })).toBeNull()
      expect(act('Escape', { [mod]: true })).toBeNull()
    }
  })
})

describe('rigKeyAction, editing a field', () => {
  it('W A S D and Space are text', () => {
    for (const k of ['w', 'a', 's', 'd', 'W', 'D', ' ']) {
      expect(act(k, {}, typing)).toBeNull()
      expect(inDetails(k, {}, { ...typing, inDetails: true })).toBeNull()
    }
  })

  it('the arrows are left to the field (↑ / ↓ change a number, Shift = fine step)', () => {
    for (const k of ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']) expect(inDetails(k, {}, { ...typing, inDetails: true })).toBeNull()
    expect(inDetails('ArrowDown', { shiftKey: true }, { ...typing, inDetails: true })).toBeNull()
  })

  it('Esc leaves a field outside the details for the list, and stops editing one in the details', () => {
    expect(act('Escape', {}, typing)).toEqual({ kind: 'list' })
    expect(inDetails('Escape', {}, { ...typing, inDetails: true })).toEqual({ kind: 'stop' })
  })

  it('⏎ stops editing a field of the details, but not in a text area or in a field elsewhere', () => {
    expect(inDetails('Enter', {}, { ...typing, inDetails: true })).toEqual({ kind: 'stop' })
    expect(inDetails('Enter', {}, { ...typing, inDetails: true, multiline: true })).toBeNull()
    expect(act('Enter', {}, typing)).toBeNull()
  })
})

describe('rigKeyAction, in the details (not editing)', () => {
  it('W S ↑ ↓ A D and the arrows only move from field to field', () => {
    expect(inDetails('w')).toEqual({ kind: 'field', dir: 'up' })
    expect(inDetails('ArrowUp')).toEqual({ kind: 'field', dir: 'up' })
    expect(inDetails('s')).toEqual({ kind: 'field', dir: 'down' })
    expect(inDetails('ArrowDown')).toEqual({ kind: 'field', dir: 'down' })
    expect(inDetails('a')).toEqual({ kind: 'field', dir: 'left' })
    expect(inDetails('ArrowLeft')).toEqual({ kind: 'field', dir: 'left' })
    expect(inDetails('d')).toEqual({ kind: 'field', dir: 'right' })
    expect(inDetails('ArrowRight')).toEqual({ kind: 'field', dir: 'right' })
    // never a selection move, a toggle or a change of a value, with Shift either
    for (const k of ['w', 's', 'a', 'd', 'ArrowUp', 'ArrowDown']) expect(inDetails(k, { shiftKey: true })?.kind).toBe('field')
    expect(inDetails(' ')).toBeNull()
  })

  it('⏎ starts editing, Esc goes back to the list', () => {
    expect(inDetails('Enter')).toEqual({ kind: 'edit' })
    expect(inDetails('Enter', { repeat: true })).toBeNull()
    expect(inDetails('Escape')).toEqual({ kind: 'list' })
  })

  it('a shortcut with Ctrl, Cmd or Alt is not ours', () => {
    expect(inDetails('s', { ctrlKey: true })).toBeNull()
    expect(inDetails('Enter', { metaKey: true })).toBeNull()
  })
})

describe('rigKeyAction, on a page without a list', () => {
  const form = { hasList: false }

  it('W A S D and the arrows go into the controls from the start, and highlight only', () => {
    for (const k of ['w', 'a', 's', 'd', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']) expect(act(k, {}, form)).toEqual({ kind: 'details' })
    expect(navStep(nav('list', 0), { kind: 'details' }, BOXES)).toEqual({ state: nav('details', 0), effect: 'blur' })
  })

  it('Space and ⏎ are not ours before a control is highlighted', () => {
    expect(act(' ', {}, form)).toBeNull()
    expect(act('Enter', {}, form)).toBeNull()
  })

  it('once in the controls it is the same as in the details of the Rig page', () => {
    expect(inDetails('s', {}, form)).toEqual({ kind: 'field', dir: 'down' })
    expect(inDetails('Enter', {}, form)).toEqual({ kind: 'edit' })
  })
})

// rows of fields in a left column, one field in a right column
const BOXES: FieldBox[] = [
  { l: 50, r: 200, cy: 20, h: 20 }, // 0: name
  { l: 50, r: 200, cy: 50, h: 20 }, // 1: type
  { l: 40, r: 80, cy: 80, h: 20 }, // 2: universe
  { l: 120, r: 160, cy: 80, h: 20 }, // 3: address
  { l: 380, r: 450, cy: 52, h: 20 }, // 4: hue source
]
const nav = (zone: NavState['zone'], index: number): NavState => ({ zone, index })

describe('navStep', () => {
  it('D from the list highlights the first field without focusing it: a blur, no edit', () => {
    expect(navStep(nav('list', 3), { kind: 'details' }, BOXES)).toEqual({ state: nav('details', 0), effect: 'blur' })
  })

  it('does not enter the details without fields', () => {
    expect(navStep(nav('list', 0), { kind: 'details' }, [])).toEqual({ state: nav('list', 0), effect: 'none' })
  })

  it('W S ↑ ↓ move the highlight and do nothing to the page, so no value can change', () => {
    expect(navStep(nav('details', 0), { kind: 'field', dir: 'down' }, BOXES)).toEqual({ state: nav('details', 1), effect: 'none' })
    expect(navStep(nav('details', 1), { kind: 'field', dir: 'down' }, BOXES)).toEqual({ state: nav('details', 3), effect: 'none' })
    expect(navStep(nav('details', 3), { kind: 'field', dir: 'up' }, BOXES)).toEqual({ state: nav('details', 1), effect: 'none' })
  })

  it('stays on the first and last row', () => {
    expect(navStep(nav('details', 0), { kind: 'field', dir: 'up' }, BOXES)).toEqual({ state: nav('details', 0), effect: 'none' })
    expect(navStep(nav('details', 3), { kind: 'field', dir: 'down' }, BOXES)).toEqual({ state: nav('details', 3), effect: 'none' })
  })

  it('A D move across a row, and A at the left edge goes back to the list', () => {
    expect(navStep(nav('details', 2), { kind: 'field', dir: 'right' }, BOXES)).toEqual({ state: nav('details', 3), effect: 'none' })
    expect(navStep(nav('details', 3), { kind: 'field', dir: 'left' }, BOXES)).toEqual({ state: nav('details', 2), effect: 'none' })
    expect(navStep(nav('details', 2), { kind: 'field', dir: 'left' }, BOXES)).toEqual({ state: nav('list', 2), effect: 'blur' })
    expect(navStep(nav('details', 3), { kind: 'field', dir: 'right' }, BOXES).state.zone).toBe('details')
  })

  it('field keys do nothing while the keys are on the list', () => {
    expect(navStep(nav('list', 1), { kind: 'field', dir: 'down' }, BOXES)).toEqual({ state: nav('list', 1), effect: 'none' })
  })

  it('⏎ edits the highlighted field, and only in the details', () => {
    expect(navStep(nav('details', 1), { kind: 'edit' }, BOXES)).toEqual({ state: nav('details', 1), effect: 'edit' })
    expect(navStep(nav('list', 1), { kind: 'edit' }, BOXES).effect).toBe('none')
  })

  it('⏎ / Esc stop editing and the field stays highlighted; Esc on the highlight goes back to the list', () => {
    expect(navStep(nav('details', 1), { kind: 'stop' }, BOXES)).toEqual({ state: nav('details', 1), effect: 'blur' })
    expect(navStep(nav('details', 1), { kind: 'list' }, BOXES)).toEqual({ state: nav('list', 1), effect: 'blur' })
  })

  it('list moves keep the zone', () => {
    expect(navStep(nav('list', 0), { kind: 'move', step: 1, shift: false }, BOXES)).toEqual({ state: nav('list', 0), effect: 'none' })
  })
})

describe('editKind', () => {
  it('a text or number field takes the caret, a select opens, a switch, checkbox, button or link is pressed', () => {
    expect(editKind({ tagName: 'INPUT', type: 'text' })).toBe('caret')
    expect(editKind({ tagName: 'INPUT' })).toBe('caret')
    expect(editKind({ tagName: 'TEXTAREA' })).toBe('caret')
    expect(editKind({ tagName: 'SELECT', type: 'select-one' })).toBe('open')
    expect(editKind({ tagName: 'BUTTON', type: 'button' })).toBe('press')
    expect(editKind({ tagName: 'INPUT', type: 'checkbox' })).toBe('press')
    expect(editKind({ tagName: 'A' })).toBe('press')
    expect(editKind({ tagName: 'DIV', role: 'slider' })).toBe('adjust') // a slider takes the focus, the arrows then change it
  })
})

describe('stepSelection', () => {
  it('moves one fixture in the shown order and selects only it', () => {
    expect(stepSelection(ORDER, cur([3], 3), 1, false)).toEqual({ selected: [0], anchor: 0, cursor: 0 })
    expect(stepSelection(ORDER, cur([4], 4), -1, false)).toEqual({ selected: [0], anchor: 0, cursor: 0 })
  })

  it('stops at the ends', () => {
    expect(stepSelection(ORDER, cur([3], 3), -1, false)).toEqual({ selected: [3], anchor: 3, cursor: 3 })
    expect(stepSelection(ORDER, cur([2], 2), 1, false)).toEqual({ selected: [2], anchor: 2, cursor: 2 })
  })

  it('a move out of a range collapses it to the one fixture', () => {
    expect(stepSelection(ORDER, cur([0, 4, 1], 0, 1), 1, false)).toEqual({ selected: [2], anchor: 2, cursor: 2 })
  })

  it('Shift extends the range from the anchor, as Shift + click does, and the anchor stays', () => {
    const a = stepSelection(ORDER, cur([0], 0), 1, true)
    expect(a).toEqual({ selected: [0, 4], anchor: 0, cursor: 4 })
    const b = stepSelection(ORDER, a, 1, true)
    expect(b).toEqual({ selected: [0, 4, 1], anchor: 0, cursor: 1 })
    // the other way shrinks it again, and past the anchor it flips
    expect(stepSelection(ORDER, b, -1, true)).toEqual({ selected: [0, 4], anchor: 0, cursor: 4 })
    expect(stepSelection(ORDER, stepSelection(ORDER, a, -1, true), -1, true)).toEqual({ selected: [3, 0], anchor: 0, cursor: 3 })
  })

  it('Shift at the end of the list keeps the range', () => {
    expect(stepSelection(ORDER, cur([4, 1, 2], 4, 2), 1, true)).toEqual({ selected: [4, 1, 2], anchor: 4, cursor: 2 })
  })

  it('Shift without an anchor starts at the cursor', () => {
    expect(stepSelection(ORDER, cur([4], null), 1, true).selected).toEqual([4, 1])
  })

  it('moves from the cursor, which can be a fixture that is not selected', () => {
    expect(stepSelection(ORDER, cur([3], 3, 4), 1, false).cursor).toBe(1)
  })

  it('a stale cursor falls back to the first selected fixture; an empty list does nothing', () => {
    expect(stepSelection(ORDER, cur([4], 4, 99), 1, false).cursor).toBe(1)
    const none = cur([], null, null)
    expect(stepSelection([], none, 1, false)).toBe(none)
  })
})

describe('toggleCurrent', () => {
  it('adds the current fixture when it is not selected, without moving, and it becomes the anchor', () => {
    expect(toggleCurrent(ORDER, cur([3], 3, 4))).toEqual({ selected: [3, 4], anchor: 4, cursor: 4 })
  })

  it('removes it when it is selected, and the cursor stays on it', () => {
    expect(toggleCurrent(ORDER, cur([3, 4], 3, 4))).toEqual({ selected: [3], anchor: 4, cursor: 4 })
  })

  it('does not remove the last selected fixture', () => {
    expect(toggleCurrent(ORDER, cur([4], 4))).toEqual({ selected: [4], anchor: 4, cursor: 4 })
  })

  it('a walk: select, add a gap, extend from the new anchor', () => {
    let s = stepSelection(ORDER, cur([3], 3), 1, true) // 3, 0
    s = toggleCurrent(ORDER, s) // toggles the current (0) off
    expect(sorted(s)).toEqual([3])
    s = stepSelection(ORDER, s, 1, true) // anchor is 0 now: range 0..4 replaces the selection
    expect(sorted(s)).toEqual([0, 4])
    expect(s.cursor).toBe(4)
  })

  it('does nothing without a selection', () => {
    const none = cur([], null, null)
    expect(toggleCurrent(ORDER, none)).toBe(none)
  })
})
