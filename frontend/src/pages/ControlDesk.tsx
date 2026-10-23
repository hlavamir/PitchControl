import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { api } from '../api'
import { Button, Section, Toggle, UNIVERSES } from '../components/forms'
import { RoutesSection } from '../components/RoutesSection'
import { SubTabs, useSubTab, type SubTab } from '../components/SubTabs'
import { DESK_TABS, type DeskTab } from '../pages'
import { routeLabel, routedChannels, routedCount, type RouteState } from '../routes'
import type { EngineConnection } from '../useEngine'
import { useFieldNav } from '../useFieldNav'
import { useGridNav, type NavItem } from '../useGridNav'

const PER_PAGE = 64 // 4 rows × 16
const POLL_MS = 100 // live output values

// the universe stays as it was when coming back to the page (the subpage is remembered with the tabs, subTabs.ts)
const memory = { universe: 0 }

interface Strip {
  channel: number // 1–512
  live: number // output value as sent (0–255)
  override: number | undefined
  fixture?: string // "Pinspot 1 · 3": which fixture uses the channel, and its channel number
  route?: RouteState // the route that decides the channel (item 58), when no override is on it
}

/** One DMX channel: drag up/down to set it (switches the override on), the switch releases it. */
function ChannelStrip({
  strip,
  selected,
  onSelect,
  setValue,
  release,
}: {
  strip: Strip
  selected: boolean
  onSelect: () => void
  setValue: (v: number) => void
  release: () => void
}) {
  const [dragValue, setDragValue] = useState<number | null>(null)
  const drag = useRef<{ startY: number; start: number; height: number; fine: boolean; frame: number; pending: number | null } | null>(null)
  const on = strip.override !== undefined
  const value = dragValue ?? strip.override ?? strip.live

  const send = () => {
    const d = drag.current
    if (!d) return
    d.frame = 0
    if (d.pending !== null) setValue(d.pending)
    d.pending = null
  }

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    onSelect()
    e.currentTarget.setPointerCapture(e.pointerId)
    const rect = e.currentTarget.getBoundingClientRect()
    // relative drag from the value shown: no jump, an unswitched channel starts at its live value
    drag.current = { startY: e.clientY, start: value, height: Math.max(rect.height, 40), fine: e.shiftKey, frame: 0, pending: null }
    setDragValue(value)
  }
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    if (e.shiftKey !== d.fine) {
      d.fine = e.shiftKey
      d.startY = e.clientY
      d.start = dragValue ?? d.start
    }
    const next = Math.round(Math.min(255, Math.max(0, d.start + ((d.startY - e.clientY) / d.height) * 255 * (d.fine ? 0.1 : 1))))
    setDragValue(next)
    d.pending = next
    if (!d.frame) d.frame = requestAnimationFrame(send)
  }
  const onPointerUp = () => {
    const d = drag.current
    if (d?.frame) cancelAnimationFrame(d.frame)
    send()
    drag.current = null
    setDragValue(null)
  }

  const fill = value / 255
  return (
    <div
      className={`flex min-h-0 min-w-0 flex-col bg-panel ${selected ? 'glow-sel' : ''}`}
      data-hint="channel"
      data-tip={`Channel ${strip.channel}: ${strip.route ? `routed from ${routeLabel(strip.route)}; ` : ''}${strip.fixture ?? 'not used by a fixture'}`}
    >
      <div className={`flex h-[26px] flex-none items-center justify-between gap-1 px-1.5 ${selected ? 'bg-ink text-ground' : 'border-b border-seam'}`}>
        <span className="flex items-center gap-1">
          {strip.route && <span className={`size-[5px] ${selected ? 'bg-ground' : 'bg-route'}`} data-tip={`Routed: ${routeLabel(strip.route)}`} />}
          <span className="font-mono text-[12px]">{String(strip.channel).padStart(3, '0')}</span>
        </span>
        <Toggle
          checked={on}
          tip={`Override channel ${strip.channel}: on sends the slider value instead of the fixtures'; off follows the fixtures again`}
          onChange={(v) => {
            onSelect()
            if (v) setValue(strip.live)
            else release()
          }}
        />
      </div>
      <div
        className="relative min-h-0 flex-1 cursor-ns-resize touch-none select-none"
        data-tip={`Channel ${strip.channel}: drag to override it (starts at the live value; Shift = fine). Fixture: ${strip.fixture ?? 'none'}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {/* overridden: bright ink; routed (live input): the route colour; following the fixtures: faint */}
        <div
          className={`absolute inset-x-1.5 bottom-1.5 ${on || dragValue !== null ? 'glow-on' : ''}`}
          style={{
            height: `calc((100% - 12px) * ${fill.toFixed(4)})`,
            background: on || dragValue !== null ? 'var(--color-ink)' : strip.route ? 'var(--color-route)' : 'rgb(var(--ink-rgb) / 0.28)',
            opacity: !(on || dragValue !== null) && strip.route ? 0.8 : undefined,
          }}
        />
        <div className="absolute inset-x-1.5 top-1.5 bottom-1.5 border border-seam" />
      </div>
      <div className="flex h-[22px] flex-none items-center justify-between gap-1 border-t border-seam px-1.5">
        <span className="lbl min-w-0 truncate text-[9px] text-dim">{strip.fixture ?? '—'}</span>
        <span className={`font-mono text-[13px] ${on ? 'text-glow' : strip.route ? 'text-route' : 'text-dim'}`}>{value}</span>
      </div>
    </div>
  )
}

/**
 * Control Desk: every DMX output channel as a slider, 64 per subpage. A channel with its override
 * switched on sends the slider value instead of what the fixtures compute. Overrides are saved and
 * restored on start; the header shows how many are active. The last subpage, Routes, copies live input (Art-Net, DMX over
 * USB, MIDI) onto output channels (items 58, 59, 61): the app's output, then routes, then manual overrides; the later layer wins.
 */
export function ControlDesk({ engine }: { engine: EngineConnection }) {
  const [universe, setUniverseState] = useState(memory.universe)
  const [tab, setTab] = useSubTab<DeskTab>('Control Desk', DESK_TABS, 'ch-0')
  const [live, setLive] = useState<number[]>(() => Array(512).fill(0))
  const [confirmReset, setConfirmReset] = useState(false)
  const setUniverse = (u: number) => setUniverseState((memory.universe = u))

  // live output values of the shown universe
  useEffect(() => {
    let alive = true
    const poll = () =>
      api
        .get<{ values: number[] }>(`/api/dmx/${universe}`)
        .then((r) => alive && setLive(r.values))
        .catch(() => undefined)
    poll()
    const id = window.setInterval(poll, POLL_MS)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [universe])

  const all = engine.state?.overrides ?? {}
  const overrides = all[String(universe)] ?? {}
  const total = Object.values(all).reduce((n, chans) => n + Object.keys(chans).length, 0)
  const routes = engine.state?.routes ?? []
  const routed = useMemo(() => routedChannels(routes, universe), [routes, universe])
  const routedTotal = routedCount(routes)

  const overridesOnSubpage = (p: number) => Object.keys(overrides).filter((c) => Math.floor((Number(c) - 1) / PER_PAGE) === p).length
  const routedOnSubpage = (p: number) => [...routed.keys()].filter((c) => Math.floor((c - 1) / PER_PAGE) === p).length
  const tabs: SubTab<DeskTab>[] = DESK_TABS.map((id, p) => {
    if (id === 'routes') {
      const on = routes.filter((r) => r.enabled).length
      return {
        id,
        label: 'Routes',
        gap: true,
        tip: `Live input (Art-Net, DMX over USB, MIDI) copied onto output channels; Q / E step through the subpages. ${on} of ${routes.length} route(s) on`,
        marks: (active) => on > 0 && <span className={`size-[5px] ${active ? 'bg-ground' : 'bg-route'}`} />,
      }
    }
    const n = overridesOnSubpage(p)
    const rn = routedOnSubpage(p)
    return {
      id,
      label: `${p * PER_PAGE + 1}–${(p + 1) * PER_PAGE}`,
      mono: true,
      tip: `Channels ${p * PER_PAGE + 1}–${(p + 1) * PER_PAGE} of 512; Q / E step through the subpages${n ? `. ${n} override(s) here` : ''}${rn ? `. ${rn} routed channel(s) here` : ''}`,
      marks: (active) => (
        <>
          {n > 0 && <span className={`size-[5px] ${active ? 'bg-ground' : 'dot-on'}`} />}
          {rn > 0 && <span className={`size-[5px] ${active ? 'bg-ground' : 'bg-route'}`} />}
        </>
      ),
    }
  })

  return (
    <div className="flex h-full flex-col gap-1.5">
      <div className="flex flex-none flex-wrap items-center gap-1.5">
        <label className="lbl flex items-center gap-2 text-[11px] text-dim" data-tip="DMX universe shown, numbered as on the Rig page and in Connections; each has 512 channels. New routes go to it">
          Universe
          <select value={universe} onChange={(e) => setUniverse(Number(e.target.value))}>
            {UNIVERSES.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </label>
        <SubTabs tabs={tabs} value={tab} onChange={setTab} />
        <div className="ml-auto flex items-center gap-1.5">
          {confirmReset ? (
            <>
              <span className="text-[11px]">
                Release all {total} override{total === 1 ? '' : 's'} in every universe?
              </span>
              <Button
                primary
                tip="Release every override in every universe: all channels follow the fixtures again"
                onClick={async () => {
                  await api.delete('/api/overrides')
                  setConfirmReset(false)
                }}
              >
                Release all
              </Button>
              <Button onClick={() => setConfirmReset(false)} tip="Keep the overrides">
                Cancel
              </Button>
            </>
          ) : (
            <>
              <span className="lbl text-[11px] text-dim">
                {total} override{total === 1 ? '' : 's'} · {routedTotal} routed · saved across restarts
              </span>
              <Button onClick={() => setConfirmReset(true)} disabled={total === 0} tip="Release all overrides, in every universe (asks first)">
                Reset all
              </Button>
            </>
          )}
        </div>
      </div>

      {tab === 'routes' ? (
        <RoutesView engine={engine} universe={universe} live={live} />
      ) : (
        <Channels engine={engine} universe={universe} subpage={DESK_TABS.indexOf(tab)} live={live} overrides={overrides} routed={routed} />
      )}
    </div>
  )
}

/** The 64 faders of a subpage, at the full height of the page; the keys move like on a hardware desk (useGridNav). */
function Channels({
  engine,
  universe,
  subpage,
  live,
  overrides,
  routed,
}: {
  engine: EngineConnection
  universe: number
  subpage: number
  live: number[]
  overrides: Record<string, number>
  routed: Map<number, RouteState>
}) {
  // which fixture uses each channel of this universe
  const fixtureAt = useMemo(() => {
    const map: Record<number, string> = {}
    for (const fx of engine.state?.fixtures ?? []) {
      if (fx.transport !== 'dmx' || fx.universe !== universe) continue
      fx.output.forEach((_, i) => (map[fx.address + i] = `${fx.name} · ${i + 1}`))
    }
    return map
  }, [engine.state?.fixtures, universe])

  const first = subpage * PER_PAGE + 1
  const strips: Strip[] = Array.from({ length: PER_PAGE }, (_, i) => {
    const channel = first + i
    return { channel, live: live[channel - 1] ?? 0, override: overrides[String(channel)], fixture: fixtureAt[channel], route: routed.get(channel) }
  })

  const setValue = (channel: number, v: number) => engine.setOverride(universe, channel, v)
  const release = (channel: number) => engine.setOverride(universe, channel, null)

  // keys: W/S/A/D move, ↑/↓ change (switches the override on), ⏎ switches the override on / off
  const navItem = (st: Strip): NavItem => ({
    id: `ch-${st.channel}`,
    label: `Ch ${st.channel}${st.fixture ? ` (${st.fixture})` : ''}`,
    value: `${st.override ?? st.live}${st.override !== undefined ? ' OVR' : st.route ? ' ROUTE' : ''}`,
    hint: 'channel',
    tip: `Channel ${st.channel}: ${st.route ? `routed from ${routeLabel(st.route)}; ` : ''}${st.fixture ?? 'not used by a fixture'}`,
    adjust: (dir, fine) => setValue(st.channel, Math.min(255, Math.max(0, (st.override ?? st.live) + dir * (fine ? 1 : 5)))),
    press: (down) => down && (st.override !== undefined ? release(st.channel) : setValue(st.channel, st.live)),
  })
  const rows = [0, 1, 2, 3].map((r) => strips.slice(r * 16, r * 16 + 16).map(navItem))
  const { selectedId, select } = useGridNav('Control Desk', rows)

  return (
    <Section
      index="01"
      title={`Universe ${universe} · channels ${first}–${first + PER_PAGE - 1}`}
      right="drag a channel to override it · the switch releases it · Q / E subpage"
      className="min-h-[28rem] flex-1"
      bodyClassName="p-0"
      tip="Every DMX channel of the universe, live. Override a channel by hand, e.g. to test a light; overrides win over routes and fixtures and are saved. Channels in the blue colour are decided by a route (live input)"
    >
      <div className="grid min-h-[36rem] flex-1 grid-cols-8 gap-px bg-edge wide:min-h-0 wide:grid-cols-16 wide:grid-rows-4">
        {strips.map((st) => (
          <ChannelStrip
            key={st.channel}
            strip={st}
            selected={selectedId === `ch-${st.channel}`}
            onSelect={() => select(`ch-${st.channel}`)}
            setValue={(v) => setValue(st.channel, v)}
            release={() => release(st.channel)}
          />
        ))}
      </div>
    </Section>
  )
}

/** The Routes subpage (items 58, 59): the keys move over its controls like on a form page (useFieldNav). */
function RoutesView({ engine, universe, live }: { engine: EngineConnection; universe: number; live: number[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useFieldNav({ root: ref })
  return (
    <div ref={ref} className="flex min-h-0 flex-1 flex-col">
      <RoutesSection
        index="01"
        className="min-h-0 flex-1"
        routes={engine.state?.routes ?? []}
        overlaps={engine.state?.route_overlaps ?? []}
        universe={universe}
        midi={engine.state?.io?.midi_routes}
        notices={engine.state?.route_midi_notices ?? []}
        live={live}
      />
    </div>
  )
}
