import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  MAX_MIDI_COUNT,
  learnHint,
  midiInputText,
  newMidiRoute,
  newRoute,
  otherUniverses,
  overlapText,
  routedCount,
  sourceState,
  type MidiChannelState,
  type MidiInputType,
  type MidiNotice,
  type MidiRoutesStatus,
  type RouteEdit,
  type RouteKind,
  type RouteOverlap,
  type RouteState,
} from '../routes'
import { usePolling } from '../usePolling'
import { Button, NumberInput, Section, TextInput, Toggle } from './forms'
import { Icon } from './Icon'

const GRID = 'grid grid-cols-[2.6rem_minmax(7rem,1.2fr)_7.5rem_4.5rem_4.5rem_4.5rem_1.2rem_5.5rem_5rem] items-center gap-x-2'
const CHANNEL_GRID = 'grid grid-cols-[3.2rem_9rem_5rem_6.5rem_6rem_2.6rem_minmax(0,1fr)] items-center gap-x-2'

const INPUT_TYPES: { value: MidiInputType; label: string }[] = [
  { value: 'none', label: 'no input' },
  { value: 'cc', label: 'CC' },
  { value: 'cc14', label: 'CC pair, 14-bit' },
  { value: 'note', label: 'Note' },
  { value: 'const', label: 'Constant' },
]

/**
 * The inputs of a MIDI route, one row per output channel (item 59): a CC, a 14-bit CC pair, a note or a constant, each with its
 * own Learn button (click it, move a control on the device, done: no stepping through the channels).
 */
function MidiChannels({
  route,
  live,
  learn,
  notices,
  onPatch,
  onLearn,
}: {
  route: RouteState
  live: number[] | null
  learn: MidiRoutesStatus['learn']
  notices: MidiNotice[]
  onPatch: (index: number, patch: Partial<MidiChannelState>) => void
  onLearn: (index: number, on: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-0.5 border border-edge p-2" data-tip="One input for each output channel of the route. Learn: click it, then move a knob or press a key on the device; the control is taken for that channel">
      <div className={`${CHANNEL_GRID} lbl border-b border-seam pb-1 text-[10px] text-dim`}>
        <span>Out</span>
        <span>Input</span>
        <span>Number</span>
        <span>Note as</span>
        <span />
        <span className="text-right">Value</span>
        <span />
      </div>
      {route.channels.map((c, i) => {
        const waiting = learn?.route === route.id && learn.index === i
        const notice = notices.find((n) => n.route === route.id && n.index === i)
        const value = live ? live[route.first_output - 1 + i] : null
        return (
          <div key={i} className="flex flex-col" data-channel={i}>
            <div className={CHANNEL_GRID}>
              <span className="font-mono text-[12px]">{route.first_output + i}</span>
              <select
                value={c.type}
                data-tip="What drives this channel: a CC (0–127 scaled to 0–255), a pair of CCs for 14 bits, a note, or a fixed value"
                onChange={(e) => {
                  const type = e.target.value as MidiInputType
                  onPatch(i, type === 'cc14' ? { type, number: Math.min(c.number, 31) } : { type })
                }}
              >
                {INPUT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              {c.type === 'const' ? (
                <NumberInput value={c.value} min={0} max={255} integer className="w-full" tip="The value to send, 0–255" onChange={(v) => onPatch(i, { value: v })} />
              ) : c.type === 'none' ? (
                <span className="text-dim">–</span>
              ) : (
                <NumberInput
                  value={c.number}
                  min={0}
                  max={c.type === 'cc14' ? 31 : 127}
                  integer
                  className="w-full"
                  tip={c.type === 'cc14' ? 'The first CC of the pair (0–31); the second half is 32 higher' : c.type === 'cc' ? 'The CC number (0–127)' : 'The note number (0–127)'}
                  onChange={(v) => onPatch(i, { number: v })}
                />
              )}
              {c.type === 'note' ? (
                <select value={c.note_mode} data-tip="Velocity: the force of the key press while it is held, 0 after. On / off: 255 while it is held, 0 after" onChange={(e) => onPatch(i, { note_mode: e.target.value as MidiChannelState['note_mode'] })}>
                  <option value="velocity">velocity</option>
                  <option value="onoff">on / off</option>
                </select>
              ) : (
                <span />
              )}
              <Button
                primary={waiting}
                onClick={() => onLearn(i, !waiting)}
                tip={waiting ? 'Waiting for a control: move a knob or press a key on the device. Click to cancel' : 'Click, then move a knob or press a key on the device: its CC or note is taken for this channel'}
                className="px-2"
              >
                {waiting ? '…' : 'Learn'}
              </Button>
              <span className="text-right font-mono text-[12px] text-dim" data-tip={`Output value now: ${midiInputText(c)}`}>
                {value ?? ''}
              </span>
              <span className="truncate pl-1 text-[11px] text-dim">{midiInputText(c)}</span>
            </div>
            {waiting && learn && <p className="pl-[3.2rem] text-[11px] text-route">{learnHint(learn)}</p>}
            {notice && (
              <p className="pl-[3.2rem] text-[11px]" role="status">
                ! {notice.text}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

/**
 * Control Desk → Routes (items 58 and 59). A route copies live input onto output channels: a block of an Art-Net universe or of
 * the DMX input, or, for a MIDI route, one CC, note or constant for each channel. Order of the layers, the later one
 * wins: the app's output → routes → manual overrides. The last value of an input stays when it goes quiet; a route lets
 * go when it is switched off or removed. Every change is one request that the server merges and saves.
 */
export function RoutesSection({
  index,
  className = '',
  routes: all,
  overlaps: allOverlaps,
  universe,
  midi,
  notices,
  live,
}: {
  index: string
  className?: string
  routes: RouteState[]
  overlaps: RouteOverlap[]
  universe: number // the universe the Control Desk shows: its routes are listed, new routes go there (item 74)
  midi?: MidiRoutesStatus
  notices: MidiNotice[]
  live: number[] // the output values of that universe
}) {
  const routes = all.filter((r) => r.universe === universe)
  const overlaps = allOverlaps.filter((o) => o.universe === universe)
  const others = otherUniverses(all, universe)
  const [problem, setProblem] = useState<string | null>(null)
  const [ports, setPorts] = useState<string[]>([])
  const [folded, setFolded] = useState<Record<string, boolean>>({}) // route id → its channel list is folded away
  const readPorts = () => api.get<string[]>('/api/devices/midi').then((p) => setPorts((prev) => (JSON.stringify(prev) === JSON.stringify(p) ? prev : p)))
  useEffect(() => {
    readPorts().catch(() => undefined)
  }, [])
  usePolling(readPorts)

  // one request per change, and the server changes only what was sent: quick edits of two fields can't undo each other
  const run = async (request: Promise<unknown>) => {
    setProblem(null)
    try {
      await request
    } catch (e) {
      setProblem(String((e as Error).message ?? e))
    }
  }
  const edit = (id: string, patch: RouteEdit) => void run(api.patch(`/api/routes/${id}`, patch)) // the server shrinks the count to fit when a first channel moves up
  const remove = (id: string) => void run(api.delete(`/api/routes/${id}`))
  const add = () => void run(api.post('/api/routes', { ...newRoute(universe), enabled: false })) // off until it is set up: a whole universe of zeros would blank the lights
  const addMidi = () => void run(api.post('/api/routes', newMidiRoute(universe, ports[0] ?? '')))
  const patchChannel = (id: string, i: number, patch: Partial<MidiChannelState>) => void run(api.patch(`/api/routes/${id}/channels/${i}`, patch))
  const learn = (id: string, i: number, on: boolean) => void run(api.post(`/api/routes/${id}/learn`, { index: i, on }))

  const covered = routedCount(routes)
  const overlapping = new Set(overlaps.flatMap((o) => o.routes))

  return (
    <Section
      index={index}
      title={`Universe ${universe} · routes`}
      className={className}
      right={`${routes.filter((r) => r.enabled).length} of ${routes.length} on · ${covered} channel${covered === 1 ? '' : 's'} routed · saved across restarts`}
      bodyClassName="p-3 gap-2 overflow-y-auto"
      tip="Live input (Art-Net and DMX over USB: set up in Connections → DMX & Art-Net; or MIDI) copied onto output channels. Order of the layers, the later one wins: the app's output, then routes, then manual overrides"
    >
      <p className="text-[11px] leading-snug text-dim">
        The routes of the universe selected at the top right; a new route goes to it. A route copies live input onto output channels: a block of an Art-Net universe or of the DMX input, up to a whole universe, or, for a MIDI route, one CC, note or fixed value for each channel. It sits over the fixtures and under the manual overrides: a channel you override keeps your value, and the route shows again when you release it. When the input stops, the last values stay; switch a route off or remove it to give the channels back to the fixtures.
      </p>
      {others.count > 0 && (
        <p className="text-[11px] text-dim" data-tip="Routes are listed by the universe they write to. Choose another universe at the top right to see and edit them">
          {others.count} more route{others.count === 1 ? '' : 's'} on other universes ({others.universes.join(', ')})
        </p>
      )}
      {routes.length > 0 && (
        <div className="flex flex-col gap-1.5 overflow-x-auto">
          <div className={`${GRID} lbl min-w-[56rem] border-b border-seam pb-1 text-[10px] text-dim`}>
            <span>On</span>
            <span>Name</span>
            <span className="flex items-center gap-1.5">
              <Icon name="in" label />
              Source
            </span>
            <span>Art-Net / MIDI ch.</span>
            <span>First in</span>
            <span>Count</span>
            <span />
            <span className="flex items-center gap-1.5">
              <Icon name="out" label />
              First out
            </span>
            <span />
          </div>
          {routes.map((r) => {
            const st = sourceState(r)
            const isMidi = r.kind === 'midi'
            return (
              <div key={r.id} className="flex min-w-[56rem] flex-col gap-0.5" data-route={r.id}>
                <div className={GRID}>
                  <Toggle checked={r.enabled} tip="Switch the route on or off. Off gives its channels back to the fixtures" onChange={(v) => edit(r.id, { enabled: v })} />
                  <TextInput
                    value={r.name}
                    maxLength={60}
                    placeholder="name (optional)"
                    tip="A name for this route, to tell it from the others"
                    onCommit={(name) => edit(r.id, { name })}
                  />
                  <select
                    value={r.kind}
                    data-tip="Where the values come from: an Art-Net universe, the DMX input (an Enttec DMX USB Pro that receives), or a MIDI device"
                    onChange={(e) => edit(r.id, e.target.value === 'midi' ? { kind: 'midi', count: Math.min(r.count, 8), midi_device: r.midi_device || (ports[0] ?? '') } : { kind: e.target.value as RouteKind })}
                  >
                    <option value="artnet">Art-Net</option>
                    <option value="dmx">DMX input</option>
                    <option value="midi">MIDI</option>
                  </select>
                  {isMidi ? (
                    <select value={r.midi_channel} data-tip="The MIDI channel (1–16) the controls of this route are on" onChange={(e) => edit(r.id, { midi_channel: Number(e.target.value) })}>
                      {Array.from({ length: 16 }, (_, i) => (
                        <option key={i} value={i + 1}>
                          ch {i + 1}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <NumberInput
                      value={r.artnet_universe}
                      min={0}
                      max={32767}
                      integer
                      disabled={r.kind !== 'artnet'}
                      className="w-full"
                      tip="The Art-Net universe to take, as its raw port address (net, sub-net and universe in one number), counted from 0, as in Connections → DMX & Art-Net"
                      onChange={(v) => edit(r.id, { artnet_universe: v })}
                    />
                  )}
                  {isMidi ? (
                    <span className="text-dim">–</span>
                  ) : (
                    <NumberInput value={r.first_input} min={1} max={512} integer className="w-full" tip="The first input channel (1–512) to copy" onChange={(v) => edit(r.id, { first_input: v })} />
                  )}
                  <NumberInput
                    value={r.count}
                    min={1}
                    max={Math.min(isMidi ? MAX_MIDI_COUNT : 512, 513 - (isMidi ? 1 : r.first_input), 513 - r.first_output)}
                    integer
                    className="w-full"
                    tip={`How many channels, 1 to ${isMidi ? MAX_MIDI_COUNT : 512}${isMidi ? ' (each has its own input)' : '; a whole universe is one row'}. It shrinks when a first channel is moved up so that the block would run past 512`}
                    onChange={(v) => edit(r.id, { count: v })}
                  />
                  <span className="text-center text-dim">→</span>
                  <NumberInput value={r.first_output} min={1} max={512} integer className="w-full" tip={`The first output channel (1–512) of universe ${universe} that gets the first input channel`} onChange={(v) => edit(r.id, { first_output: v })} />
                  <Button onClick={() => remove(r.id)} tip="Remove this route; its channels follow the fixtures again">
                    Remove
                  </Button>
                </div>
                {isMidi && (
                  <div className="flex items-center gap-2 pl-[2.6rem] text-[12px]">
                    <span className="lbl text-[10px] text-dim">Device</span>
                    <select className="min-w-[16rem]" value={r.midi_device} data-tip="The MIDI input this route listens to. The controller of the MIDI mapping can be used here too" onChange={(e) => edit(r.id, { midi_device: e.target.value })}>
                      <option value="">— choose a MIDI device —</option>
                      {r.midi_device && !ports.includes(r.midi_device) && <option value={r.midi_device}>{r.midi_device} (not found)</option>}
                      {ports.map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                    <button className="lbl text-[10px] text-dim underline decoration-dotted underline-offset-2" data-tip="Show or hide the inputs of the channels" onClick={() => setFolded((f) => ({ ...f, [r.id]: !f[r.id] }))}>
                      {folded[r.id] ? '▸ show the channels' : '▾ hide the channels'}
                    </button>
                  </div>
                )}
                <p className={`pl-[2.6rem] text-[11px] ${!r.enabled ? 'text-dim' : st.level === 'live' ? 'text-route' : st.level === 'holding' || st.level === 'problem' ? 'text-ink' : 'text-dim'}`}>
                  {r.enabled
                    ? `${st.level === 'problem' ? '! ' : ''}${st.text} · output channels ${r.first_output}–${r.first_output + r.count - 1}`
                    : 'off: its channels follow the fixtures. Switch it on when it is set up'}
                  {r.enabled && overlapping.has(r.id) && ' · overlaps another route'}
                </p>
                {isMidi && !folded[r.id] && (
                  <div className="pl-[2.6rem]">
                    <MidiChannels
                      route={r}
                      live={live}
                      learn={midi?.learn ?? null}
                      notices={notices}
                      onPatch={(i, patch) => patchChannel(r.id, i, patch)}
                      onLearn={(i, on) => learn(r.id, i, on)}
                    />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      {routes.length === 0 && <p className="text-[13px] text-dim">No routes in universe {universe}. Add one to send what comes in (Connections → DMX & Art-Net), or from a MIDI device, to its output channels.</p>}
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
      <div className="flex items-center gap-2">
        <Button onClick={add} tip="Add a route for Art-Net or the DMX input (off until you switch it on). The list is checked from top to bottom: a route lower down wins where two overlap" disabled={routes.length >= 256}>
          Add route
        </Button>
        <Button onClick={addMidi} tip="Add a route that takes each channel from a MIDI control: a CC, a note or a fixed value, set with Learn" disabled={routes.length >= 256}>
          Add MIDI route
        </Button>
      </div>
    </Section>
  )
}
