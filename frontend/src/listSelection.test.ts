import { describe, expect, it } from 'vitest'
import { clickSelection, type ListSelection } from './listSelection'

// shown in this order (the indices are the items' positions in the file, not in the list)
const ORDER = [3, 0, 4, 1, 2]
const plain = { shift: false, toggle: false }
const shift = { shift: true, toggle: false }
const toggle = { shift: false, toggle: true }
const both = { shift: true, toggle: true }
const sorted = (s: ListSelection) => [...s.selected].sort((a, b) => a - b)

describe('clickSelection', () => {
  it('a plain click selects that item and makes it the anchor', () => {
    expect(clickSelection(ORDER, { selected: [3, 0], anchor: 3 }, 4, plain)).toEqual({ selected: [4], anchor: 4 })
  })

  it('Shift + click selects the range from the anchor, in the displayed order, and keeps the anchor', () => {
    const s = clickSelection(ORDER, { selected: [0], anchor: 0 }, 1, shift)
    expect(s).toEqual({ selected: [0, 4, 1], anchor: 0 })
    // the next Shift + click changes the range, it doesn't extend it
    expect(clickSelection(ORDER, s, 3, shift)).toEqual({ selected: [3, 0], anchor: 0 })
    expect(clickSelection(ORDER, s, 2, shift)).toEqual({ selected: [0, 4, 1, 2], anchor: 0 })
  })

  it('Shift + click works upwards too', () => {
    expect(clickSelection(ORDER, { selected: [1], anchor: 1 }, 3, shift).selected).toEqual([3, 0, 4, 1])
  })

  it('Shift + click on the anchor selects just it', () => {
    expect(clickSelection(ORDER, { selected: [0, 4], anchor: 0 }, 0, shift)).toEqual({ selected: [0], anchor: 0 })
  })

  it('without an anchor the range starts at the first selected item', () => {
    expect(clickSelection(ORDER, { selected: [4], anchor: null }, 2, shift).selected).toEqual([4, 1, 2])
    expect(clickSelection(ORDER, { selected: [4], anchor: 99 }, 2, shift).selected).toEqual([4, 1, 2]) // stale anchor
  })

  it('Ctrl / Cmd + click adds and removes one, and moves the anchor', () => {
    const added = clickSelection(ORDER, { selected: [3], anchor: 3 }, 1, toggle)
    expect(added).toEqual({ selected: [3, 1], anchor: 1 })
    expect(clickSelection(ORDER, added, 3, toggle)).toEqual({ selected: [1], anchor: 3 })
  })

  it('the last selected item can not be removed', () => {
    expect(clickSelection(ORDER, { selected: [4], anchor: 4 }, 4, toggle)).toEqual({ selected: [4], anchor: 4 })
  })

  it('Ctrl / Cmd + Shift + click adds the range to the selection', () => {
    const s = clickSelection(ORDER, { selected: [3, 2], anchor: 2 }, 4, both)
    expect(sorted(s)).toEqual([1, 2, 3, 4]) // 3 stays; from the anchor 2 to 4 the list shows 4, 1, 2
    expect(s.anchor).toBe(2)
    const t = clickSelection(ORDER, { selected: [3], anchor: 0 }, 4, both)
    expect(sorted(t)).toEqual([0, 3, 4])
  })
})
