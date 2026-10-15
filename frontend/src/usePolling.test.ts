import { describe, expect, it } from 'vitest'
import { unchanged } from './usePolling'

describe('unchanged', () => {
  it('keeps the previous value when the new one has the same content, so that nothing is redrawn', () => {
    const prev = [{ label: 'Komplete Audio 6', channels: 6 }]
    expect(unchanged(prev, [{ label: 'Komplete Audio 6', channels: 6 }])).toBe(prev)
  })

  it('takes the new value when a device came or went', () => {
    const prev = ['IAC Driver Bus 1']
    const next = ['IAC Driver Bus 1', 'LCXL3 1 MIDI In']
    expect(unchanged(prev, next)).toBe(next)
    expect(unchanged(next, ['IAC Driver Bus 1'])).toEqual(['IAC Driver Bus 1'])
  })

  it('takes the first value', () => {
    expect(unchanged(null as string[] | null, [])).toEqual([])
  })
})
