import { describe, expect, it } from 'vitest'
import type { ChannelMode } from './api'
import { channelLabels, defaultPixels, normalisePixels, pixelLabel, pixelSources, presetOf, withSource } from './pixelOrder'

describe('pixel order (item 103)', () => {
  it('knows the sources of a preset and a list', () => {
    expect(pixelSources('GRB')).toEqual(['RGB.green', 'RGB.red', 'RGB.blue'])
    expect(pixelSources('I')).toEqual(['HSB.brightness'])
    expect(pixelSources(['RGB.blue', 'RGB.green', 'RGB.red'])).toHaveLength(3)
  })

  it('takes a list that spells a preset as the preset, like the backend', () => {
    expect(normalisePixels(['RGB.red', 'RGB.green', 'RGB.blue'])).toBe('RGB')
    expect(normalisePixels(['RGB.green', 'RGB.red', 'RGB.blue'])).toBe('GRB')
    expect(normalisePixels(['HSB.brightness'])).toBe('I')
    expect(normalisePixels(['RGB.blue', 'RGB.green', 'RGB.red'])).toEqual(['RGB.blue', 'RGB.green', 'RGB.red'])
    expect(presetOf(['RGB.blue', 'RGB.green', 'RGB.red'])).toBeNull()
    expect(presetOf('RGBW')).toBe('RGBW')
  })

  it('has the defaults of 1, 3 and 4 channels', () => {
    expect(defaultPixels(1)).toBe('I')
    expect(defaultPixels(3)).toBe('RGB')
    expect(defaultPixels(4)).toBe('RGBW')
  })

  it('changes one channel and falls back to a preset when the order is one', () => {
    expect(withSource('RGB', 0, 'RGB.blue')).toEqual(['RGB.blue', 'RGB.green', 'RGB.blue'])
    expect(withSource(['RGB.green', 'RGB.green', 'RGB.blue'], 1, 'RGB.red')).toBe('GRB')
    expect(withSource('RGBW', 3, 'HSB.hue')).toEqual(['RGBW.red', 'RGBW.green', 'RGBW.blue', 'HSB.hue'])
  })

  it('does not change the preset it started from', () => {
    withSource('RGB', 0, 'RGB.blue')
    expect(pixelSources('RGB')).toEqual(['RGB.red', 'RGB.green', 'RGB.blue'])
  })

  it('writes a pixel block in a few characters', () => {
    expect(pixelLabel('GRB')).toBe('GRB')
    expect(pixelLabel(['RGB.blue', 'RGB.green', 'RGB.red'])).toBe('BGR')
    expect(pixelLabel(['RGBW.white', 'RGBW.red', 'RGBW.green', 'RGBW.blue'])).toBe('WRGB')
    expect(pixelLabel(['HSB.hue', 'HSB.saturation', 'HSB.brightness'])).toBe('hue sat bri')
  })

  it('labels every DMX channel of a mode in order', () => {
    const mode: ChannelMode = {
      id: 'm',
      name: 'm',
      description: '',
      pixels: 2,
      channels: [{ name: 'Dimmer', value: 255 }, { pixels: ['RGB.blue', 'RGB.green', 'RGB.red'] }, { name: 'Strobe', shutter: { open: 0, strobo: 255 } }],
    }
    expect(channelLabels(mode)).toEqual([
      'Dimmer (constant 255)',
      'pixel 1 · RGB.blue',
      'pixel 1 · RGB.green',
      'pixel 1 · RGB.red',
      'pixel 2 · RGB.blue',
      'pixel 2 · RGB.green',
      'pixel 2 · RGB.red',
      'Strobe (shutter)',
    ])
  })
})
