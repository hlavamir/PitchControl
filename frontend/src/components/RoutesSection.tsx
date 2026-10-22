import { useEffect, useState } from 'react'
import { api } from '../api'
import { newRoute, overlapText, routedCount, sourceState, type RouteEdit, type RouteKind, type RouteOverlap, type RouteState } from '../routes'
import { Button, NumberInput, Section, Toggle, UNIVERSES } from './forms'

/** A text field that keeps what you type and applies it when you leave it or press Enter. */
function NameInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [text, setText] = useState(value)
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    if (!dirty) setText(value)
  }, [value, dirty])
  const commit = () => {
    if (!dirty) return
    setDirty(false)
    if (text !== value) onCommit(text)
  }
  return (
    <input
      type="text"
      className="w-full"
      value={text}
      maxLength={60}
      placeholder="name (optional)"
      data-tip="A name for this route, to tell it from the others"
      onChange={(e) => {
        setText(e.target.value)
        setDirty(true)
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        if (e.key === 'Escape') {
          setDirty(false)
          setText(value)
        }
      }}
    />
  )
}

const GRID = 'grid grid-cols-[2.6rem_minmax(7rem,1.2fr)_7.5rem_4.5rem_4.5rem_4.5rem_1.2rem_4.5rem_4.5rem_5rem] items-center gap-x-2'

/**
 * Control Desk → Routes (item 58). A route copies a block of input channels (an Art-Net universe, or the DMX input) onto
 * output channels. Order of the layers, the later one wins: the app's output → routes → manual overrides. The last
 * value of an input stays when it goes quiet; a route lets go when it is switched off or removed. Every change is sent
 * at once and saved on the server.
 */
export function RoutesSection({ index, routes, overlaps, universe }: { index: string; routes: RouteState[]; overlaps: RouteOverlap[]; universe: number }) {
  const [problem, setProblem] = useState<string | null>(null)

  // one request per change, and the server changes only what was sent: quick edits of two fields can't undo each other
  const run = async (request: Promise<unknown>) => {
    setProblem(null)
    try {
      await request
    } catch (e) {
      setProblem(String((e as Error).message ?? e))
    }
  }
  const edit = (id: string, patch: Partial<RouteEdit>) => void run(api.patch(`/api/routes/${id}`, patch)) // the server shrinks the count to fit when a first channel moves up
  const remove = (id: string) => void run(api.delete(`/api/routes/${id}`))
  const add = () => void run(api.post('/api/routes', { ...newRoute(universe), enabled: false })) // off until it is set up: a whole universe of zeros would blank the lights

  const covered = routedCount(routes)
  const overlapping = new Set(overlaps.flatMap((o) => o.routes))

  return (
    <Section
      index={index}
      title="Routes"
      right={`${routes.filter((r) => r.enabled).length} of ${routes.length} on · ${covered} channel${covered === 1 ? '' : 's'} routed · saved across restarts`}
      bodyClassName="p-3 gap-2"
      tip="Live input (Art-Net, DMX over USB: set up on the Inputs page) copied onto output channels. Order of the layers, the later one wins: the app's output, then routes, then manual overrides"
    >
      <p className="text-[11px] leading-snug text-dim">
        A route copies a block of an input onto output channels, up to a whole universe. It sits over the fixtures and under the manual overrides: a channel you override keeps your value, and the route shows again when you release it. When the input stops, the last values stay; switch a route off or remove it to give the channels back to the fixtures.
      </p>
      {routes.length > 0 && (
        <div className="flex flex-col gap-1.5 overflow-x-auto">
          <div className={`${GRID} lbl min-w-[56rem] border-b border-seam pb-1 text-[10px] text-dim`}>
            <span>On</span>
            <span>Name</span>
            <span>Source</span>
            <span>Art-Net univ.</span>
            <span>First in</span>
            <span>Count</span>
            <span />
            <span>Out univ.</span>
            <span>First out</span>
            <span />
          </div>
          {routes.map((r) => {
            const st = sourceState(r)
            return (
              <div key={r.id} className="flex min-w-[56rem] flex-col gap-0.5" data-route={r.id}>
                <div className={GRID}>
                  <Toggle checked={r.enabled} tip="Switch the route on or off. Off gives its channels back to the fixtures" onChange={(v) => edit(r.id, { enabled: v })} />
                  <NameInput value={r.name} onCommit={(name) => edit(r.id, { name })} />
                  <select
                    value={r.kind}
                    data-tip="Where the values come from: an Art-Net universe, or the DMX input (an Enttec DMX USB Pro that receives)"
                    onChange={(e) => edit(r.id, { kind: e.target.value as RouteKind })}
                  >
                    <option value="artnet">Art-Net</option>
                    <option value="dmx">DMX input</option>
                  </select>
                  <NumberInput
                    value={r.artnet_universe}
                    min={0}
                    max={32767}
                    integer
                    disabled={r.kind !== 'artnet'}
                    className="w-full"
                    tip="The Art-Net universe to take, as its raw port address (net, sub-net and universe in one number), counted from 0, as on the Inputs page"
                    onChange={(v) => edit(r.id, { artnet_universe: v })}
                  />
                  <NumberInput value={r.first_input} min={1} max={512} integer className="w-full" tip="The first input channel (1–512) to copy" onChange={(v) => edit(r.id, { first_input: v })} />
                  <NumberInput
                    value={r.count}
                    min={1}
                    max={Math.min(513 - r.first_input, 513 - r.first_output)}
                    integer
                    className="w-full"
                    tip="How many channels to copy, 1 to 512; a whole universe is one row. It shrinks when a first channel is moved up so that the block would run past 512"
                    onChange={(v) => edit(r.id, { count: v })}
                  />
                  <span className="text-center text-dim">→</span>
                  <select value={r.universe} data-tip="The output universe the channels go to (the universes of the Rig and Outputs pages)" onChange={(e) => edit(r.id, { universe: Number(e.target.value) })}>
                    {UNIVERSES.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                    {!UNIVERSES.includes(r.universe) && <option value={r.universe}>{r.universe}</option>}
                  </select>
                  <NumberInput value={r.first_output} min={1} max={512} integer className="w-full" tip="The first output channel (1–512) that gets the first input channel" onChange={(v) => edit(r.id, { first_output: v })} />
                  <Button onClick={() => remove(r.id)} tip="Remove this route; its channels follow the fixtures again">
                    Remove
                  </Button>
                </div>
                <p className={`pl-[2.6rem] text-[11px] ${r.enabled ? (st.level === 'live' ? 'text-route' : st.level === 'holding' ? 'text-ink' : 'text-dim') : 'text-dim'}`}>
                  {r.enabled
                    ? `${st.text} · output ${r.universe}, channels ${r.first_output}–${r.first_output + r.count - 1}`
                    : 'off: its channels follow the fixtures. Switch it on when it is set up'}
                  {r.enabled && overlapping.has(r.id) && ' · overlaps another route'}
                </p>
              </div>
            )
          })}
        </div>
      )}
      {routes.length === 0 && <p className="text-[13px] text-dim">No routes. Add one to send what comes in on the Inputs page to output channels.</p>}
      {overlaps.length > 0 && (
        <div className="border border-edge px-2.5 py-2 text-[12px] leading-snug" role="status" data-tip="Two routes write the same output channels; the one lower in the list wins there">
          <p>! Routes overlap:</p>
          <ul>
            {overlaps.map((o) => (
              <li key={`${o.universe}:${o.first}`} className="text-dim">
                {overlapText(o, routes)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {problem && (
        <p className="text-[12px] leading-snug" role="alert">
          {problem}
        </p>
      )}
      <div>
        <Button onClick={add} tip="Add a route (off until you switch it on). The list is checked from top to bottom: a route lower down wins where two overlap" disabled={routes.length >= 256}>
          Add route
        </Button>
      </div>
    </Section>
  )
}
