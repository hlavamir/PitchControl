import { describe, expect, it } from 'vitest'
import type { EngineState } from './api'
import { artnetDot, artnetInputActive, dmxDots, dmxInputActive } from './headerDots'
import type { LiveInputStatus } from './liveInput'

type Io = EngineState['io']
type Enttec = { connected: boolean; error: string | null } | null

const io = (o: { enttec?: Enttec[]; artnet?: { connected: boolean; error: string | null } | null; dmx?: LiveInputStatus['dmx']; an?: LiveInputStatus['artnet'] }): Io =>
  ({
    outputs: { enttec: o.enttec ?? [], artnet: o.artnet ?? null, pitchpls_v2: null, osc: null },
    audio: null,
    midi: null,
    live_input: { dmx: o.dmx ?? { enabled: false }, artnet: o.an ?? { enabled: false } },
  }) as unknown as Io

const dmxIn = (over: Partial<LiveInputStatus['dmx']> = {}): LiveInputStatus['dmx'] => ({ enabled: true, connected: true, age: 0.1, error: null, ...over })
const anIn = (age: number, over: Partial<LiveInputStatus['artnet']> = {}): LiveInputStatus['artnet'] => ({
  enabled: true,
  listening: true,
  universes: [{ key: 'a', universe: 0, sender: '10.0.0.2', pps: 40, age, packets: 5 }],
  ...over,
})
const up = { connected: true, error: null }

describe('dmxDots', () => {
  it('nothing configured: one hollow dot with the "no interface" tip', () => {
    const d = dmxDots(io({}))
    expect(d).toHaveLength(1)
    expect(d[0].ok).toBeNull()
    expect(d[0].tip).toMatch(/No USB DMX interface/)
    expect(dmxDots(undefined)[0].ok).toBeNull()
  })
  it('receiving only: one filled dot "dmx" for the input', () => {
    const d = dmxDots(io({ dmx: dmxIn() }))
    expect(d).toHaveLength(1)
    expect(d[0]).toMatchObject({ ok: true, label: 'dmx', error: null })
    expect(d[0].tip).not.toMatch(/No USB DMX interface/)
  })
  it('sending only: one dot per output, as before', () => {
    const d = dmxDots(io({ enttec: [up, { connected: false, error: null }] }))
    expect(d.map((x) => [x.label, x.ok])).toEqual([['dmx 1', true], ['dmx 2', false]])
  })
  it('both: the first dot is filled by the input even when its output is down; the second stays its own', () => {
    const d = dmxDots(io({ enttec: [{ connected: false, error: 'gone' }, up], dmx: dmxIn() }))
    expect(d.map((x) => x.ok)).toEqual([true, true])
    expect(d[0].error).toBeNull()
    const d2 = dmxDots(io({ enttec: [up, { connected: false, error: 'gone' }], dmx: dmxIn() }))
    expect(d2.map((x) => x.ok)).toEqual([true, false])
    expect(d2[1].error).toBe('gone')
  })
  it('input stale (age 2 s or more) or not connected: hollow, not filled', () => {
    expect(dmxInputActive(io({ dmx: dmxIn({ age: 1.99 }) }))).toBe(true)
    for (const dmx of [dmxIn({ age: 2 }), dmxIn({ age: null }), dmxIn({ connected: false })]) {
      expect(dmxInputActive(io({ dmx }))).toBe(false)
      expect(dmxDots(io({ dmx }))[0].ok).toBeNull()
    }
    expect(dmxDots(io({ dmx: dmxIn({ enabled: false }) }))[0].tip).toMatch(/No USB DMX interface/)
  })
  it('input error with nothing else working: crossed, with the error', () => {
    const d = dmxDots(io({ dmx: dmxIn({ connected: false, error: 'port busy' }) }))
    expect(d[0]).toMatchObject({ ok: false, error: 'port busy' })
    const w = dmxDots(io({ enttec: [{ connected: false, error: null }], dmx: dmxIn({ connected: false, error: 'port busy' }) }))
    expect(w[0]).toMatchObject({ ok: false, error: 'port busy' })
  })
  it('an input error does not cross a dot that works', () => {
    expect(dmxDots(io({ enttec: [up], dmx: dmxIn({ connected: false, error: 'x' }) }))[0]).toMatchObject({ ok: true, error: null })
  })
})

describe('artnetDot', () => {
  it('nothing configured: hollow', () => {
    expect(artnetDot(io({}))).toMatchObject({ ok: null, error: null, label: 'art-net' })
    expect(artnetDot(undefined).ok).toBeNull()
  })
  it('receiving only: filled', () => {
    expect(artnetDot(io({ an: anIn(0.5) })).ok).toBe(true)
  })
  it('sending only: filled; output down: crossed with its error', () => {
    expect(artnetDot(io({ artnet: up })).ok).toBe(true)
    expect(artnetDot(io({ artnet: { connected: false, error: 'bind failed' } }))).toMatchObject({ ok: false, error: 'bind failed' })
  })
  it('both: filled', () => {
    expect(artnetDot(io({ artnet: up, an: anIn(0.5) })).ok).toBe(true)
  })
  it('input stale (age 2 s or more): hollow', () => {
    expect(artnetInputActive(io({ an: anIn(1.99) }))).toBe(true)
    expect(artnetDot(io({ an: anIn(2) })).ok).toBeNull()
    expect(artnetDot(io({ an: anIn(0.1, { enabled: false }) })).ok).toBeNull()
    expect(artnetDot(io({ an: { enabled: true, listening: true, universes: [] } })).ok).toBeNull()
  })
  it('a quiet universe next to a live one still lights it', () => {
    const an = anIn(5)
    an.universes!.push({ key: 'b', universe: 1, sender: '10.0.0.3', pps: 40, age: 0.2, packets: 9 })
    expect(artnetDot(io({ an })).ok).toBe(true)
  })
  it('errors: the output\'s first, else the input\'s; a working dot shows none', () => {
    expect(artnetDot(io({ artnet: { connected: false, error: 'out' }, an: { enabled: true, error: 'in' } })).error).toBe('out')
    expect(artnetDot(io({ an: { enabled: true, listening: false, error: 'in' } }))).toMatchObject({ ok: false, error: 'in' })
    expect(artnetDot(io({ artnet: up, an: { ...anIn(5), error: 'in' } }))).toMatchObject({ ok: true, error: null })
  })
})
