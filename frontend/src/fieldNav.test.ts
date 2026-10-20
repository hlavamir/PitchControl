import { describe, expect, it } from 'vitest'
import { moveField, type FieldBox } from './fieldNav'

// the details of a fixture in a wide window: a left column of rows (some with two fields side by side) and a right column
const B = (cx: number, cy: number, col = 0, h = 20): FieldBox => ({ cx, cy, h, col })
const BOXES: FieldBox[] = [
  B(100, 20), // 0 name
  B(100, 50), // 1 type
  B(60, 80), // 2 universe
  B(140, 80), // 3 address
  B(60, 110), // 4 position u
  B(140, 110), // 5 position v
  B(100, 140), // 6 rotation
  B(400, 52, 1), // 7 hue source (right column, between the rows of the left one)
  B(400, 82, 1), // 8 saturation source
]

describe('moveField', () => {
  it('down and up go row by row, in the same column', () => {
    expect(moveField(BOXES, 0, 'down')).toBe(1)
    expect(moveField(BOXES, 1, 'down')).toBe(2)
    expect(moveField(BOXES, 6, 'up')).toBe(4)
    expect(moveField(BOXES, 7, 'down')).toBe(8)
    expect(moveField(BOXES, 8, 'up')).toBe(7)
  })

  it('a row with two fields: the one closest horizontally', () => {
    expect(moveField(BOXES, 1, 'down')).toBe(2) // from x=100: 60 is 40 away, 140 is 40 away: the first
    expect(moveField(BOXES, 3, 'down')).toBe(5)
    expect(moveField(BOXES, 3, 'up')).toBe(1)
    expect(moveField(BOXES, 6, 'up')).toBe(4)
  })

  it('stops at the first and last row of a column', () => {
    expect(moveField(BOXES, 0, 'up')).toBeNull()
    expect(moveField(BOXES, 6, 'down')).toBeNull()
    expect(moveField(BOXES, 7, 'up')).toBeNull()
  })

  it('left and right go along the row', () => {
    expect(moveField(BOXES, 2, 'right')).toBe(3)
    expect(moveField(BOXES, 3, 'left')).toBe(2)
    expect(moveField(BOXES, 4, 'right')).toBe(5)
  })

  it('a row with one field has no left or right neighbour in its column; the left edge is null', () => {
    expect(moveField(BOXES, 0, 'left')).toBeNull()
    expect(moveField(BOXES, 6, 'left')).toBeNull()
    expect(moveField(BOXES, 2, 'left')).toBeNull()
  })

  it('across the columns: to the field of the other column closest in height', () => {
    expect(moveField(BOXES, 1, 'right')).toBe(7) // same row (y 50 and 52)
    expect(moveField(BOXES, 7, 'left')).toBe(1)
    expect(moveField(BOXES, 6, 'right')).toBe(8) // no field in its row: the closest in height
    expect(moveField(BOXES, 8, 'left')).toBe(3) // the row has the address field right of the universe: the nearest one
  })

  it('an unknown field or a single field moves nowhere', () => {
    expect(moveField(BOXES, 99, 'down')).toBeNull()
    expect(moveField([B(0, 0)], 0, 'down')).toBeNull()
    expect(moveField([B(0, 0)], 0, 'right')).toBeNull()
  })
})
