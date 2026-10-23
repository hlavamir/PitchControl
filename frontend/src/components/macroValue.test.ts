import { describe, expect, it } from 'vitest'
import type { MacroDef } from '../api'
import { formatValue, valueInRange } from './MacroControl'
import { macroHint } from '../hints'

const maskCurve = { name: 'Mask Curve', label: 'Mask Curve', min: 0.25, max: 4, steps: 129, kind: 'fader', page: 'general', default: 0.5, log_scale: true, decimals: 2, unit: '', display_scale: 1, deferred: false } as MacroDef

describe('a logarithmic macro (Mask Curve, item 76)', () => {
  it('runs from 0.25 to 4 with 1 in the middle', () => {
    expect(valueInRange(maskCurve, 0)).toBeCloseTo(0.25)
    expect(valueInRange(maskCurve, 0.5)).toBeCloseTo(1)
    expect(valueInRange(maskCurve, 1)).toBeCloseTo(4)
    expect(valueInRange(maskCurve, 0.25)).toBeCloseTo(0.5)
    expect(valueInRange(maskCurve, 0.75)).toBeCloseTo(2)
  })

  it('shows two decimals and its own footer hint', () => {
    expect(formatValue(maskCurve, 0.5)).toBe('1.00')
    expect(formatValue(maskCurve, 0.75)).toBe('2.00')
    expect(macroHint(maskCurve)).toBe('fader-wide')
  })

  it('leaves the linear macros alone', () => {
    const linear = { ...maskCurve, min: 0.1, max: 3, steps: 128, log_scale: false } as MacroDef
    expect(valueInRange(linear, 1)).toBeCloseTo(3)
    expect(valueInRange(linear, 0)).toBeCloseTo(0.1)
  })
})
