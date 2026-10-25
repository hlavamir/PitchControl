import { describe, expect, it } from 'vitest'
import type { MacroDef } from '../api'
import { formatValue, valueInRange } from './MacroControl'
import { macroHint } from '../hints'
import { FINE_STEP, STEP } from '../macroNav'

const maskCurve = { name: 'Mask Curve', label: 'Mask Curve', min: 0.25, max: 4, steps: 128, kind: 'fader', page: 'general', default: 0.5, log_scale: true, decimals: 2, unit: '', display_scale: 1, deferred: false } as MacroDef

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

describe('faders at full resolution (item 95)', () => {
  const linear = { ...maskCurve, name: 'Strobo Decay', min: 0.1, max: 3, log_scale: false } as MacroDef

  it('shows the exact value, not the nearest of 128 steps', () => {
    expect(valueInRange(linear, 0.3003)).toBeCloseTo(0.1 + 0.3003 * 2.9, 12)
    expect(valueInRange(linear, 1 / 127 / 3)).toBeCloseTo(0.1 + (1 / 127 / 3) * 2.9, 12)
    expect(valueInRange(maskCurve, Math.log(2.2 / 0.25) / Math.log(16))).toBeCloseTo(2.2, 12)
    expect(formatValue(maskCurve, Math.log(2.2 / 0.25) / Math.log(16))).toBe('2.20')
    expect(valueInRange(linear, 1.2)).toBeCloseTo(3)
    expect(valueInRange(linear, -0.2)).toBeCloseTo(0.1)
  })

  it('still snaps a toggle', () => {
    const toggle = { ...linear, kind: 'toggle', steps: 2, min: 0, max: 1 } as MacroDef
    expect(valueInRange(toggle, 0.4)).toBe(0)
    expect(valueInRange(toggle, 0.6)).toBe(1)
  })

  it('keeps the arrow keys at half a fader segment and a tenth of that with Shift', () => {
    expect(STEP).toBe(0.025)
    expect(FINE_STEP).toBe(0.0025)
  })
})
