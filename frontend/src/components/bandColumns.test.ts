import { describe, expect, it } from 'vitest'
import { bandColumns } from './bandColumns'

describe('bandColumns', () => {
  it('turns the live values into percent heights, clamped', () => {
    const c = bandColumns([0, 0.5, 1.4, -1, NaN])
    expect(c.map((x) => x.live)).toEqual([0, 50, 100, 0, 0])
    expect(c.every((x) => x.max === 0 && x.min === 0 && x.weight === null && !x.peak)).toBe(true)
  })

  it("draws each band's own maximum and minimum, clamped, and leaves them out when absent", () => {
    const c = bandColumns([0.1, 0.2, 0.3], [0.4, 0.7, 1.5], [0.05, 0.1])
    expect(c.map((x) => x.max)).toEqual([40, 70, 100])
    expect(c.map((x) => x.min)).toEqual([5, 10, 0])
  })

  it('carries the peaks and the strobo trigger weights', () => {
    const c = bandColumns([0.1, 0.2], [0.3, 0.3], [0, 0], [0, 1], [1, 0.25])
    expect(c.map((x) => x.peak)).toEqual([false, true])
    expect(c.map((x) => x.weight)).toEqual([100, 25])
  })
})
