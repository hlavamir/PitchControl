import { describe, expect, it } from 'vitest'
import { cellBox, cssCells, seamThickness, snapCells, spreadWithin } from './deviceSnap'

describe('seamThickness', () => {
  it('rounds the CSS px to whole device px, at least 1', () => {
    expect(seamThickness(1, 1)).toBe(1)
    expect(seamThickness(1, 1.25)).toBe(1)
    expect(seamThickness(1, 1.5)).toBe(2)
    expect(seamThickness(1, 1.125)).toBe(1)
    expect(seamThickness(1, 0.4)).toBe(1)
    expect(seamThickness(2, 0.9)).toBe(2)
    expect(seamThickness(2, 1.25)).toBe(3)
  })
})

describe('snapCells', () => {
  const lengths = [97, 130, 131, 149, 233, 300, 301, 419]
  const scales = [1, 1.125, 1.25, 1.5, 2]

  it('makes every cell equally tall and every seam equally thick, leftover at the far end', () => {
    for (const length of lengths) {
      for (const scale of scales) {
        const c = snapCells(length, 20, 1, scale)
        expect(new Set(c.sizes).size).toBe(1)
        expect(c.seam).toBe(seamThickness(1, scale))
        expect(c.starts[0]).toBe(0)
        for (let i = 1; i < 20; i++) expect(c.starts[i] - (c.starts[i - 1] + c.sizes[i - 1])).toBe(0)
        expect(c.starts[19] + c.sizes[19]).toBeLessThanOrEqual(length)
        expect(length - c.extent).toBeLessThan(20)
      }
    }
  })

  it('computes a known case: 131 px, 20 cells', () => {
    // 6 px each, 120 used, 11 left over at the end
    const c = snapCells(131, 20, 1, 1.25)
    expect(c.sizes[0]).toBe(6)
    expect(c.starts[19]).toBe(114)
    expect(c.extent).toBe(120)
    expect(c.seam).toBe(1)
  })

  it('splits the leftover between the two ends', () => {
    const c = snapCells(131, 20, 1, 1.25, { leftover: 'split' })
    expect(c.origin).toBe(5)
    expect(131 - (c.origin + c.extent)).toBe(6)
  })

  it('keeps equal gaps between the cells when the seam is a gap', () => {
    for (const [length, gap, scale] of [[1000, 2, 1], [1259, 2, 1.25], [701, 2, 1.5], [333, 2, 2]]) {
      const c = snapCells(length, 32, gap, scale, { gap: true, leftover: 'split' })
      expect(new Set(c.sizes).size).toBe(1)
      for (let i = 1; i < 32; i++) expect(c.starts[i] - (c.starts[i - 1] + c.sizes[i - 1])).toBe(c.seam)
      expect(c.seam).toBe(seamThickness(gap, scale))
      expect(c.origin + c.extent).toBeLessThanOrEqual(length)
      expect(length - c.extent).toBeLessThan(32 + 2 * 32)
    }
  })

  it('spreads the leftover into the cells so they fill the length exactly', () => {
    for (const length of [97, 130, 131, 233]) {
      const c = snapCells(length, 12, 1, 1.25, { leftover: 'spread' })
      expect(c.origin).toBe(0)
      expect(c.extent).toBe(length)
      expect(Math.max(...c.sizes) - Math.min(...c.sizes)).toBeLessThanOrEqual(1)
      for (let i = 1; i < 12; i++) expect(c.starts[i]).toBe(c.starts[i - 1] + c.sizes[i - 1])
    }
    const g = snapCells(500, 8, 2, 1, { gap: true, leftover: 'spread' })
    expect(g.extent).toBe(500)
    for (let i = 1; i < 8; i++) expect(g.starts[i] - (g.starts[i - 1] + g.sizes[i - 1])).toBe(2)
  })

  it('drops the gap and keeps at least a pixel per cell when the track is too short', () => {
    const c = snapCells(20, 32, 2, 1, { gap: true })
    expect(c.seam).toBe(0)
    expect(c.sizes[0]).toBe(1)
    // a seam never swallows its cell
    expect(snapCells(25, 20, 2, 1).seam).toBe(0)
    expect(snapCells(60, 20, 2, 1).seam).toBe(2)
  })

  it('handles a single cell and nonsense counts', () => {
    expect(snapCells(100, 1, 1, 1)).toMatchObject({ sizes: [100], starts: [0], extent: 100 })
    expect(snapCells(100, 0, 1, 1).sizes).toEqual([100])
  })
})

describe('cssCells / cellBox / spreadWithin', () => {
  it('converts the device pixels to CSS px at the scale, with a hair that keeps the edge on its pixel', () => {
    const c = cssCells(snapCells(131, 20, 1, 1.25), 1.25)
    for (let i = 0; i < 20; i++) {
      expect(c.starts[i] * 1.25).toBeGreaterThanOrEqual(c.device.starts[i])
      expect(c.starts[i] * 1.25 - c.device.starts[i]).toBeLessThan(1 / 128)
      expect(c.sizes[i] * 1.25 - c.device.sizes[i]).toBeLessThan(1 / 128)
    }
    expect(c.seam * 1.25).toBeCloseTo(1, 9)
  })

  it('places the cells absolutely: a vertical fader from the bottom, a horizontal one from the left', () => {
    const c = cssCells(snapCells(100, 5, 1, 1), 1)
    expect(cellBox(c, 2, 'y')).toMatchObject({ position: 'absolute', left: 0, right: 0, bottom: c.starts[2], height: c.sizes[2] })
    expect(cellBox(c, 2, 'x')).toMatchObject({ position: 'absolute', top: 0, bottom: 0, left: c.starts[2], width: c.sizes[2] })
  })

  it('fits a second row into the extent of the first, from its origin', () => {
    const c = cssCells(snapCells(131, 20, 1, 1.25, { leftover: 'split' }), 1.25)
    const h = spreadWithin(c, 12, 1)
    expect(h.device.origin).toBe(c.device.origin)
    expect(h.device.extent).toBe(c.device.extent)
    expect(h.device.sizes).toHaveLength(12)
  })
})
