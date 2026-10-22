// Routes (Control Desk, item 58): live input copied onto output channels.

export type RouteKind = 'artnet' | 'dmx'

/** A route as the API sends it: what is saved, and the state of its source. */
export interface RouteState {
  id: string
  name: string
  enabled: boolean
  kind: RouteKind
  artnet_universe: number // the raw Art-Net port address
  first_input: number // 1–512
  count: number // 1–512
  universe: number // the output universe
  first_output: number // 1–512
  seen: boolean // the source has sent something
  age: number | null // seconds since its last packet
  pps: number // packets per second
}

/** What goes back to the server: the saved fields only. */
export type RouteEdit = Omit<RouteState, 'seen' | 'age' | 'pps'>

export interface RouteOverlap {
  universe: number
  first: number
  last: number
  routes: string[] // ids; the last one wins
}

/** A source that was quiet for this long is "holding" its last values. */
export const HOLDING_AFTER_S = 2

export function newRoute(universe: number): RouteEdit {
  return { id: '', name: '', enabled: true, kind: 'artnet', artnet_universe: 0, first_input: 1, count: 512, universe, first_output: 1 }
}

export function sourceLabel(r: Pick<RouteState, 'kind' | 'artnet_universe'>): string {
  return r.kind === 'dmx' ? 'DMX input' : `Art-Net ${r.artnet_universe}`
}

/** The name of a route: its own, else "source → universe:channel". */
export function routeLabel(r: RouteState): string {
  return r.name || `${sourceLabel(r)} → ${r.universe}:${r.first_output}`
}

/** The route that decides each channel of a universe (the last enabled one that covers it wins). */
export function routedChannels(routes: RouteState[], universe: number): Map<number, RouteState> {
  const out = new Map<number, RouteState>()
  for (const r of routes) {
    if (!r.enabled || r.universe !== universe) continue
    for (let ch = r.first_output; ch < r.first_output + r.count; ch++) out.set(ch, r)
  }
  return out
}

/** How many output channels the enabled routes cover, in every universe (a channel two routes cover counts once). */
export function routedCount(routes: RouteState[]): number {
  const seen = new Set<string>()
  for (const r of routes) {
    if (!r.enabled) continue
    for (let ch = r.first_output; ch < r.first_output + r.count; ch++) seen.add(`${r.universe}:${ch}`)
  }
  return seen.size
}

/** What a route's source is doing, in a few words: never sent, receiving, or quiet (the last values are held). */
export function sourceState(r: Pick<RouteState, 'seen' | 'age' | 'pps'>): { text: string; level: 'none' | 'live' | 'holding' } {
  if (!r.seen || r.age == null) return { text: 'no data yet', level: 'none' }
  if (r.age > HOLDING_AFTER_S) return { text: `quiet for ${formatAge(r.age)}: holding the last values`, level: 'holding' }
  return { text: `receiving, ${r.pps.toFixed(0)} packets/s`, level: 'live' }
}

export function formatAge(age: number): string {
  if (age < 60) return `${Math.floor(age)} s`
  if (age < 3600) return `${Math.floor(age / 60)} min`
  return `${Math.floor(age / 3600)} h`
}

/** "Output 0, channels 21–22: Console and Back panel; the last one wins". */
export function overlapText(o: RouteOverlap, routes: RouteState[]): string {
  const names = o.routes.map((id) => routes.find((r) => r.id === id)).map((r) => (r ? routeLabel(r) : '?'))
  const chans = o.first === o.last ? `channel ${o.first}` : `channels ${o.first}–${o.last}`
  return `Output ${o.universe}, ${chans}: ${names.join(' and ')}; the last one wins`
}
