import { describe, expect, it } from 'vitest'
import { BUTTONS, FADERS, MASKS } from './generalControls'
import { macroPlace } from './macroPlace'

describe('macroPlace (item 96)', () => {
  it('numbers the faders as the General page does', () => {
    expect(macroPlace('Strobo Decay')).toBe('fader 01')
    expect(macroPlace('Hue A')).toBe('fader 05')
    expect(macroPlace('Idle Bright. B')).toBe('fader 16')
  })

  it('numbers the function buttons 01–08 and the masks 09–16', () => {
    expect(macroPlace('Manual Strobo')).toBe('button 01')
    expect(macroPlace('Swap Colors')).toBe('button 06')
    expect(macroPlace('Mask A')).toBe('button 09')
    expect(macroPlace('Mask D')).toBe('button 12')
  })

  it('gives the dimmers and the scene slots', () => {
    expect(macroPlace('Dimmer 03')).toBe('dimmer 03')
    expect(macroPlace('Dimmer 16')).toBe('dimmer 16')
    expect(macroPlace('Scene 4 Load')).toBe('scene 4')
    expect(macroPlace('Scene 7 Save')).toBe('scene 7')
  })

  it('has no place for macros that are not a numbered control', () => {
    expect(macroPlace('Mask Curve')).toBeNull()
    expect(macroPlace('Dimmer 17')).toBeNull()
    expect(macroPlace('Scene 9 Load')).toBeNull()
    expect(macroPlace('nothing')).toBeNull()
  })

  it('follows the order of the General page lists', () => {
    FADERS.forEach((n, i) => expect(macroPlace(n)).toBe(`fader ${String(i + 1).padStart(2, '0')}`))
    BUTTONS.forEach(([n], i) => expect(macroPlace(n)).toBe(`button ${String(i + 1).padStart(2, '0')}`))
    MASKS.forEach(([n], i) => expect(macroPlace(n)).toBe(`button ${String(i + 9).padStart(2, '0')}`))
  })
})
