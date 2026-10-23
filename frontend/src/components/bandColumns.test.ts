import { describe, expect, it } from 'vitest'
import { bandColumns } from './bandColumns'

describe('bandColumns', () => {
  it('turns the live values into percent heights, clamped', () => {
    const c = bandColumns([0, 0.5, 1.4, -1, NaN])
    expect(c.map((x) => x.live)).toEqual([0, 50, 100, 0, 0])
    expect(c.every((x) => x.norm === 0 && x.weight === null && !x.peak)).toBe(true)
  })

  it('draws one shared normalisation value behind every band, or one per band', () => {
    expect(bandColumns([0.1, 0.2], 0.4).map((x) => x.norm)).toEqual([40, 40])
    expect(bandColumns([0.1, 0.2], [0.4, 0.7]).map((x) => x.norm)).toEqual([40, 70])
  })

  it('carries the peaks and the strobo trigger weights', () => {
    const c = bandColumns([0.1, 0.2], 0.3, [0, 1], [1, 0.25])
    expect(c.map((x) => x.peak)).toEqual([false, true])
    expect(c.map((x) => x.weight)).toEqual([100, 25])
  })
})
