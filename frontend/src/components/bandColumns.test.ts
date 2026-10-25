import { describe, expect, it } from 'vitest'
import { bandColumns, layerHeight, snapColumns } from './bandColumns'

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

describe('snapColumns', () => {
  const edges = (w: number, n: number, gap: number) => {
    const s = snapColumns(w, n, gap)
    return { s, xs: Array.from({ length: n }, (_, i) => s.offset + i * (s.col + s.gap)) }
  }

  it('makes every column and every gap equal and keeps them inside the width', () => {
    for (const [w, n, gap] of [[1000, 31, 1], [1007, 31, 1], [1259, 31, 2], [1513, 24, 2], [999, 31, 3], [640, 8, 1]]) {
      const { s, xs } = edges(w, n, gap)
      expect(s.gap).toBe(gap)
      expect(xs[0]).toBe(s.offset)
      for (let i = 1; i < n; i++) expect(xs[i] - (xs[i - 1] + s.col)).toBe(gap)
      expect(xs[n - 1] + s.col).toBeLessThanOrEqual(w)
      // the leftover is less than one column plus gap, split at the sides
      const used = n * s.col + (n - 1) * s.gap
      expect(w - used).toBeLessThan(n)
      expect(s.offset).toBe(Math.floor((w - used) / 2))
    }
  })

  it('computes a known case: 1000 px, 31 bands, 1 px gap', () => {
    // col = floor((1000 - 30) / 31) = 31, used 31 * 31 + 30 = 991, leftover 9 → offset 4
    expect(snapColumns(1000, 31, 1)).toEqual({ col: 31, gap: 1, offset: 4 })
  })

  it('has no offset when the width divides exactly', () => {
    expect(snapColumns(991, 31, 1)).toEqual({ col: 31, gap: 1, offset: 0 })
  })

  it('shrinks the gap to 0 first when it leaves no room, and never goes below 1 px per column', () => {
    expect(snapColumns(40, 31, 1)).toEqual({ col: 1, gap: 0, offset: 4 })
    expect(snapColumns(31, 31, 1)).toEqual({ col: 1, gap: 0, offset: 0 })
    expect(snapColumns(10, 31, 1)).toEqual({ col: 1, gap: 0, offset: 0 })
    expect(snapColumns(0, 5, 2)).toEqual({ col: 1, gap: 0, offset: 0 })
  })

  it('handles a single band and nonsense counts', () => {
    expect(snapColumns(100, 1, 2)).toEqual({ col: 100, gap: 2, offset: 0 })
    expect(snapColumns(100, 0, 1).col).toBe(100)
  })
})

describe('layerHeight', () => {
  it('rounds the percent of the device height to whole pixels, clamped', () => {
    expect(layerHeight(0, 100)).toBe(0)
    expect(layerHeight(50, 101)).toBe(51)
    expect(layerHeight(33.3, 120)).toBe(40)
    expect(layerHeight(100, 97)).toBe(97)
    expect(layerHeight(150, 97)).toBe(97)
    expect(layerHeight(-5, 97)).toBe(0)
  })
})
