import { describe, expect, it } from 'vitest'
import { BUTTONS, FADERS, MASKS } from './generalControls'
import { macroPlace, placeOrder } from './macroPlace'

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

describe('placeOrder (item 96)', () => {
  it('sorts faders, then buttons, by number; macros without a place last, in their old order', () => {
    const fn1 = BUTTONS[0][0], mask1 = MASKS[0][0], fn6 = BUTTONS[5][0]
    const names = ['Mask Curve', fn6, FADERS[10], FADERS[0], mask1, 'Page General', fn1]
    const sorted = [...names].sort((a, b) => placeOrder(a) - placeOrder(b))
    expect(sorted.map((n) => macroPlace(n) ?? n)).toEqual(['fader 01', 'fader 11', 'button 01', 'button 06', 'button 09', 'Mask Curve', 'Page General'])
  })
})
