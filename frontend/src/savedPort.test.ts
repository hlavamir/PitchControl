import { describe, expect, it } from 'vitest'
import { savedPortState } from './savedPort'

describe('savedPortState', () => {
  const ports = ['Some Keyboard 0', 'LCXL3 1 MIDI In 1']

  it('a saved port that is listed is listed', () => {
    expect(savedPortState('LCXL3 1 MIDI In 1', ports, { port: 'LCXL3 1 MIDI In 1', wanted: 'LCXL3 1 MIDI In 1' })).toEqual({ state: 'listed' })
  })

  it('a renumbered port that is open is not "not found"', () => {
    expect(savedPortState('LCXL3 1 MIDI In 0', ports, { port: 'LCXL3 1 MIDI In 0', wanted: 'LCXL3 1 MIDI In 0' })).toEqual({
      state: 'renamed',
      now: 'LCXL3 1 MIDI In 0',
    })
  })

  it('nothing open, or an open port that belongs to another wanted name, is missing', () => {
    expect(savedPortState('LCXL3 1 MIDI In 0', ports, { port: null, wanted: 'LCXL3 1 MIDI In 0' })).toEqual({ state: 'missing' })
    expect(savedPortState('LCXL3 1 MIDI In 0', ports, { port: 'Other 1', wanted: 'LCXL3' })).toEqual({ state: 'missing' })
    expect(savedPortState('LCXL3 1 MIDI In 0', ports, undefined)).toEqual({ state: 'missing' })
  })
})
