import { describe, expect, it } from 'vitest'
import { rigKeyAction, stepSelection, toggleCurrent, type KeyInfo, type ListCursor } from './rigKeys'

const key = (k: string, extra: Partial<KeyInfo> = {}): KeyInfo => ({ key: k, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false, ...extra })
const act = (k: string, extra: Partial<KeyInfo> = {}, typing = false, onList = true) => rigKeyAction(key(k, extra), typing, onList)

// shown in this order (the indices are the fixtures' positions in the file, not in the list)
const ORDER = [3, 0, 4, 1, 2]
const at = (selected: number[], anchor: number | null, cursor: number | null = selected[selected.length - 1] ?? null): ListCursor => ({ selected, anchor, cursor })
const sorted = (s: ListCursor) => [...s.selected].sort((a, b) => a - b)

describe('rigKeyAction, outside a field', () => {
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
    expect(act(' ', {}, false, false)).toBeNull()
    expect(act(' ', { repeat: true })).toBeNull()
  })

  it('D and → go into the details', () => {
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

describe('rigKeyAction, typing in a field', () => {
  it('W A S D and Space are text', () => {
    for (const k of ['w', 'a', 's', 'd', 'W', 'D', ' ']) expect(act(k, {}, true)).toBeNull()
  })

  it('the arrows and ⏎ are left to the field (↑ / ↓ change a number, ⏎ applies it)', () => {
    for (const k of ['ArrowUp', 'ArrowDown', 'ArrowRight', 'Enter']) expect(act(k, {}, true)).toBeNull()
    expect(act('ArrowDown', { shiftKey: true }, true)).toBeNull() // Shift = fine step
  })

  it('Esc leaves the field', () => {
    expect(act('Escape', {}, true)).toEqual({ kind: 'list' })
  })
})

describe('stepSelection', () => {
  it('moves one fixture in the shown order and selects only it', () => {
    expect(stepSelection(ORDER, at([3], 3), 1, false)).toEqual({ selected: [0], anchor: 0, cursor: 0 })
    expect(stepSelection(ORDER, at([4], 4), -1, false)).toEqual({ selected: [0], anchor: 0, cursor: 0 })
  })

  it('stops at the ends', () => {
    expect(stepSelection(ORDER, at([3], 3), -1, false)).toEqual({ selected: [3], anchor: 3, cursor: 3 })
    expect(stepSelection(ORDER, at([2], 2), 1, false)).toEqual({ selected: [2], anchor: 2, cursor: 2 })
  })

  it('a move out of a range collapses it to the one fixture', () => {
    expect(stepSelection(ORDER, at([0, 4, 1], 0, 1), 1, false)).toEqual({ selected: [2], anchor: 2, cursor: 2 })
  })

  it('Shift extends the range from the anchor, as Shift + click does, and the anchor stays', () => {
    const a = stepSelection(ORDER, at([0], 0), 1, true)
    expect(a).toEqual({ selected: [0, 4], anchor: 0, cursor: 4 })
    const b = stepSelection(ORDER, a, 1, true)
    expect(b).toEqual({ selected: [0, 4, 1], anchor: 0, cursor: 1 })
    // the other way shrinks it again, and past the anchor it flips
    expect(stepSelection(ORDER, b, -1, true)).toEqual({ selected: [0, 4], anchor: 0, cursor: 4 })
    expect(stepSelection(ORDER, stepSelection(ORDER, a, -1, true), -1, true)).toEqual({ selected: [3, 0], anchor: 0, cursor: 3 })
  })

  it('Shift at the end of the list keeps the range', () => {
    expect(stepSelection(ORDER, at([4, 1, 2], 4, 2), 1, true)).toEqual({ selected: [4, 1, 2], anchor: 4, cursor: 2 })
  })

  it('Shift without an anchor starts at the cursor', () => {
    expect(stepSelection(ORDER, at([4], null), 1, true).selected).toEqual([4, 1])
  })

  it('moves from the cursor, which can be a fixture that is not selected', () => {
    expect(stepSelection(ORDER, at([3], 3, 4), 1, false).cursor).toBe(1)
  })

  it('a stale cursor falls back to the first selected fixture; an empty list does nothing', () => {
    expect(stepSelection(ORDER, at([4], 4, 99), 1, false).cursor).toBe(1)
    const none = at([], null, null)
    expect(stepSelection([], none, 1, false)).toBe(none)
  })
})

describe('toggleCurrent', () => {
  it('adds the current fixture when it is not selected, without moving, and it becomes the anchor', () => {
    expect(toggleCurrent(ORDER, at([3], 3, 4))).toEqual({ selected: [3, 4], anchor: 4, cursor: 4 })
  })

  it('removes it when it is selected, and the cursor stays on it', () => {
    expect(toggleCurrent(ORDER, at([3, 4], 3, 4))).toEqual({ selected: [3], anchor: 4, cursor: 4 })
  })

  it('does not remove the last selected fixture', () => {
    expect(toggleCurrent(ORDER, at([4], 4))).toEqual({ selected: [4], anchor: 4, cursor: 4 })
  })

  it('a walk: select, add a gap, extend from the new anchor', () => {
    let s = stepSelection(ORDER, at([3], 3), 1, true) // 3, 0
    s = toggleCurrent(ORDER, s) // toggles the current (0) off
    expect(sorted(s)).toEqual([3])
    s = stepSelection(ORDER, s, 1, true) // anchor is 0 now: range 0..4 replaces the selection
    expect(sorted(s)).toEqual([0, 4])
    expect(s.cursor).toBe(4)
  })

  it('does nothing without a selection', () => {
    const none = at([], null, null)
    expect(toggleCurrent(ORDER, none)).toBe(none)
  })
})
