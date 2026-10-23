import { describe, expect, it } from 'vitest'
import { lastSeen, portAddressParts, portProblem, sortUniverses, type ArtNetUniverse } from './liveInput'

const uni = (universe: number, age: number): ArtNetUniverse => ({ key: `artnet:${universe}`, universe, sender: '10.0.0.2', pps: 40, age, packets: 100 })

describe('portProblem', () => {
  it('takes 1 to 65535, the standard Art-Net port among them', () => {
    for (const ok of ['1', '6454', '65535']) expect(portProblem(ok)).toBeNull()
    for (const bad of ['', '0', '65536', '64.5', 'abc', '-1']) expect(portProblem(bad)).not.toBeNull()
  })
})

describe('lastSeen', () => {
  it('says how long ago', () => {
    expect([null, 0.2, 3.9, 75, 7300].map(lastSeen)).toEqual(['never', 'now', '3 s ago', '1 min ago', '2 h ago'])
  })
})

describe('portAddressParts', () => {
  it('splits the 15 bits into net, sub-net and universe', () => {
    expect(portAddressParts(0x123)).toBe('net 1 · sub-net 2 · universe 3')
    expect(portAddressParts(0x7fff)).toBe('net 127 · sub-net 15 · universe 15')
  })
})

describe('sortUniverses', () => {
  it('lists the ones still sending first, each group by number', () => {
    expect(sortUniverses([uni(5, 30), uni(2, 0.1), uni(1, 60), uni(0, 1)]).map((u) => u.universe)).toEqual([0, 2, 1, 5])
  })
})
