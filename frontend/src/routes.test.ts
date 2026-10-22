import { describe, expect, it } from 'vitest'
import { newRoute, overlapText, routeLabel, routedChannels, routedCount, sourceState, type RouteState } from './routes'

const route = (over: Partial<RouteState> = {}): RouteState => ({
  ...newRoute(0),
  id: 'r1',
  seen: true,
  age: 0.1,
  pps: 40,
  count: 1,
  ...over,
})

describe('routedChannels', () => {
  it('maps the channels of the shown universe to the route that decides them', () => {
    const a = route({ id: 'a', first_output: 10, count: 4 })
    const b = route({ id: 'b', first_output: 12, count: 4 })
    const other = route({ id: 'c', universe: 1, first_output: 1, count: 512 })
    const off = route({ id: 'd', enabled: false, first_output: 100, count: 5 })
    const map = routedChannels([a, b, other, off], 0)
    expect([...map.keys()]).toEqual([10, 11, 12, 13, 14, 15])
    expect(map.get(11)?.id).toBe('a')
    expect(map.get(12)?.id).toBe('b') // the later route wins
    expect(map.has(100)).toBe(false)
  })
  it('counts every routed channel once, in every universe', () => {
    const routes = [route({ first_output: 1, count: 4 }), route({ first_output: 3, count: 4 }), route({ universe: 2, count: 512, first_output: 1 }), route({ enabled: false, count: 50 })]
    expect(routedCount(routes)).toBe(6 + 512)
  })
})

describe('sourceState', () => {
  it('tells never, receiving and holding apart', () => {
    expect(sourceState({ seen: false, age: null, pps: 0 })).toEqual({ text: 'no data yet', level: 'none' })
    expect(sourceState({ seen: true, age: 0.2, pps: 39.6 })).toEqual({ text: 'receiving, 40 packets/s', level: 'live' })
    expect(sourceState({ seen: true, age: 130, pps: 0 })).toEqual({ text: 'quiet for 2 min: holding the last values', level: 'holding' })
  })
})

describe('labels', () => {
  it('names a route by its name, else by its source and target', () => {
    expect(routeLabel(route({ name: 'Console' }))).toBe('Console')
    expect(routeLabel(route({ artnet_universe: 3, universe: 1, first_output: 33 }))).toBe('Art-Net 3 → 1:33')
    expect(routeLabel(route({ kind: 'dmx' }))).toBe('DMX input → 0:1')
  })
  it('describes an overlap with both names', () => {
    const rs = [route({ id: 'a', name: 'Console' }), route({ id: 'b', name: 'Back panel' })]
    expect(overlapText({ universe: 0, first: 21, last: 22, routes: ['a', 'b'] }, rs)).toBe('Output 0, channels 21–22: Console and Back panel; the last one wins')
    expect(overlapText({ universe: 1, first: 5, last: 5, routes: ['a', 'x'] }, rs)).toBe('Output 1, channel 5: Console and ?; the last one wins')
  })
})
