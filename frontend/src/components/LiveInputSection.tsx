import { useEffect, useState, type ReactNode } from 'react'
import { api, type SerialDevice } from '../api'
import { ARTNET_DEFAULT_PORT, QUIET_AFTER_S, lastSeen, portAddressParts, portProblem, sortUniverses, type LiveInputSettings, type LiveInputView } from '../liveInput'
import type { EngineConnection } from '../useEngine'
import { usePolling } from '../usePolling'
import { Button, DevicePicker, Section, StatusDot, Toggle } from './forms'

const POLL_MS = 3000 // the adapters and USB devices change when a cable does

export type LiveInput = ReturnType<typeof useLiveInput>

/**
 * Connections → DMX & Art-Net: the Art-Net input and the DMX input (item 57), DMX that comes in from outside, for the
 * routes of the Control Desk (item 58). Per computer (machine.json); the switches apply at once, the port with its
 * button. Only the computer that runs PitchControl changes it, like the network switch.
 */
export function useLiveInput() {
  const [view, setView] = useState<LiveInputView | null>(null)
  const [remote, setRemote] = useState(false)
  const [devices, setDevices] = useState<SerialDevice[]>([])
  const [problem, setProblem] = useState<string | null>(null)

  const read = async () => {
    const info = await api.get<{ local?: boolean }>('/api/app-info')
    if (info.local === false) return setRemote(true)
    const [v, d] = await Promise.all([api.get<LiveInputView>('/api/live-input'), api.get<SerialDevice[]>('/api/devices/serial')])
    setView((prev) => (JSON.stringify(prev?.settings) === JSON.stringify(v.settings) && JSON.stringify(prev?.adapters) === JSON.stringify(v.adapters) ? prev : v))
    setDevices((prev) => (JSON.stringify(prev) === JSON.stringify(d) ? prev : d))
  }
  useEffect(() => {
    read().catch((e) => setProblem(String(e.message ?? e)))
  }, [])
  usePolling(read, POLL_MS)

  const save = async (change: (s: LiveInputSettings) => void) => {
    if (!view) return
    setProblem(null)
    const next = structuredClone(view.settings)
    change(next)
    try {
      setView(await api.put<LiveInputView>('/api/live-input', next))
    } catch (e) {
      setProblem(String((e as Error).message ?? e))
    }
  }
  return { view, remote, devices, problem, save }
}

/** What both input sections show before their settings: this device can't change them, still loading, a problem. */
function Status({ input, children }: { input: LiveInput; children: ReactNode }) {
  const { view, remote, problem } = input
  return (
    <>
      {remote && <p className="text-[12px] leading-snug text-dim">The live input can only be changed on the computer that runs PitchControl.</p>}
      {!remote && !view && !problem && <p className="lbl text-[11px] text-dim">…</p>}
      {view && children}
      {problem && (
        <p className="text-[12px] leading-snug" role="alert">
          {problem}
        </p>
      )}
    </>
  )
}

export function ArtnetInputSection({ index, input, engine, className = '' }: { index: string; input: LiveInput; engine: EngineConnection; className?: string }) {
  const [port, setPort] = useState<string | null>(null) // the port field while it is being edited
  const cfg = input.view?.settings
  const art = engine.state?.io?.live_input?.artnet // live, at the preview rate; the settings come from the page's own reads
  const portText = port ?? String(cfg?.artnet.port ?? ARTNET_DEFAULT_PORT)
  const portBad = port !== null ? portProblem(port) : null
  const portDirty = port !== null && port !== String(cfg?.artnet.port)
  const adapters = input.view?.adapters ?? []
  const adapterMissing = !!cfg?.artnet.adapter && !adapters.some((a) => a.ip === cfg.artnet.adapter)
  const universes = sortUniverses(art?.universes ?? [])
  const applyPort = () => input.save((s) => (s.artnet.port = Number(port))).then(() => setPort(null))

  return (
    <Section
      index={index}
      title="Art-Net input" icon="in"
      className={className}
      bodyClassName="p-3 gap-2"
      right={
        input.remote ? (
          'this device'
        ) : (
          <StatusDot
            ok={cfg?.artnet.enabled ? !!art?.listening : null}
            label={!cfg?.artnet.enabled ? 'off' : art?.listening ? `listening on ${art.port}` : 'not listening'}
            error={art?.error}
            tip="Whether the Art-Net listener is open"
          />
        )
      }
      tip="Art-Net that comes in over the network from another program or a console. The Control Desk's routes send it to output channels"
    >
      <Status input={input}>
        {cfg && (
          <>
            <div className="flex items-center gap-2.5">
              <Toggle checked={cfg.artnet.enabled} tip="Listen for Art-Net on this computer. Off: nothing is received (the last values of a universe stay for the routes)" onChange={(v) => input.save((s) => (s.artnet.enabled = v))} />
              <span className="lbl text-[12px]">Receive Art-Net</span>
            </div>
            <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
              <label className="flex flex-col gap-1" data-tip="The Art-Net standard port is 6454. Change it only when another Art-Net program on this computer has the port and doesn't share it">
                <span className="lbl text-[10px] text-dim">Port</span>
                <input
                  type="text"
                  inputMode="numeric"
                  className="w-24"
                  value={portText}
                  onChange={(e) => setPort(e.target.value.trim())}
                  onKeyDown={(e) => e.key === 'Enter' && !portBad && portDirty && applyPort()}
                />
              </label>
              <Button disabled={!portDirty || !!portBad} tip="Listen on this port" onClick={applyPort}>
                Apply
              </Button>
              <label className="flex min-w-[12rem] flex-1 flex-col gap-1" data-tip="Which network adapter to listen on. All adapters takes Art-Net from any network this computer is on; Loopback is for a program on this computer">
                <span className="lbl text-[10px] text-dim">Network adapter</span>
                <select value={cfg.artnet.adapter} onChange={(e) => input.save((s) => (s.artnet.adapter = e.target.value))}>
                  <option value="">All adapters</option>
                  {adapterMissing && <option value={cfg.artnet.adapter}>{cfg.artnet.adapter} (not found)</option>}
                  {adapters.map((a) => (
                    <option key={a.ip} value={a.ip}>
                      {a.name} — {a.ip}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {portBad && (
              <p className="text-[12px] leading-snug" role="alert">
                {portBad}
              </p>
            )}
            {cfg.artnet.enabled && art?.error && (
              <p className="border border-ink px-2.5 py-2 text-[12px] leading-snug" role="alert">
                {art.error}
              </p>
            )}
            <p className="text-[11px] leading-snug text-dim">
              Universe numbers here are the raw Art-Net values (port addresses), counted from 0. PitchControl's own Art-Net output is ignored.
            </p>
            {cfg.artnet.enabled && (
              <div className="flex min-h-0 flex-1 flex-col font-mono text-[12px]" data-tip="Every Art-Net universe that has sent something since the listener started, and where it comes from. A universe that went quiet keeps its last values">
                <div className="lbl grid flex-none grid-cols-[4.5rem_minmax(0,1fr)_4.5rem_5.5rem] gap-2 border-b border-seam pb-1 text-[10px] text-dim">
                  <span>Universe</span>
                  <span>Sender</span>
                  <span className="text-right">Packets/s</span>
                  <span className="text-right">Last seen</span>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">
                  {universes.length === 0 && <p className="py-1.5 text-dim">{art?.listening ? 'Nothing received yet.' : '—'}</p>}
                  {universes.map((u) => (
                    <div
                      key={u.key}
                      className={`grid grid-cols-[4.5rem_minmax(0,1fr)_4.5rem_5.5rem] gap-2 py-0.5 ${u.age > QUIET_AFTER_S ? 'text-dim' : ''}`}
                      data-tip={`Art-Net universe ${u.universe} (${portAddressParts(u.universe)}); ${u.packets} packets`}
                    >
                      <span>{u.universe}</span>
                      <span className="truncate">{u.sender}</span>
                      <span className="text-right">{u.age > QUIET_AFTER_S ? '0' : u.pps.toFixed(0)}</span>
                      <span className="text-right">{lastSeen(u.age)}</span>
                    </div>
                  ))}
                </div>
                {!!art?.own_ignored && <p className="flex-none pt-1 text-[11px] text-dim">{art.own_ignored} packets of this app's own output ignored.</p>}
              </div>
            )}
          </>
        )}
      </Status>
    </Section>
  )
}

export function DmxInputSection({ index, input, engine, className = '' }: { index: string; input: LiveInput; engine: EngineConnection; className?: string }) {
  const cfg = input.view?.settings
  const dmx = engine.state?.io?.live_input?.dmx
  return (
    <Section
      index={index}
      title="USB DMX input" icon="in"
      className={className}
      bodyClassName="p-3 gap-2"
      right={
        input.remote ? (
          'this device'
        ) : (
          <StatusDot
            ok={cfg?.dmx.enabled ? !!(dmx?.enabled && dmx.connected) : null}
            label={!cfg?.dmx.enabled ? 'off' : dmx?.connected ? 'receiving' : 'not connected'}
            error={dmx?.error}
            tip="Whether the Pro is open"
          />
        )
      }
      tip="DMX that comes in on an Enttec DMX USB Pro, from a console or another DMX line. The Control Desk's routes send it to output channels"
    >
      <Status input={input}>
        {cfg && (
          <>
            <div className="flex items-center gap-2.5">
              <Toggle checked={cfg.dmx.enabled} tip="Receive DMX on an Enttec DMX USB Pro. A Pro that receives doesn't send: the same device can't also be an output" onChange={(v) => input.save((s) => (s.dmx.enabled = v))} />
              <span className="lbl text-[12px]">Receive DMX over USB</span>
            </div>
            <div className="flex items-center gap-2 text-[13px]">
              <span className="text-dim">Device</span>
              <div className="min-w-0 flex-1">
                <DevicePicker
                  value={cfg.dmx.device}
                  devices={input.devices}
                  tip="The Enttec DMX USB Pro that receives; chosen by serial number, so it survives a different USB port"
                  onChange={(d) => input.save((s) => (s.dmx.device = d))}
                />
              </div>
            </div>
            {cfg.dmx.enabled && dmx?.error && (
              <p className="border border-ink px-2.5 py-2 text-[12px] leading-snug" role="alert">
                {dmx.error}
              </p>
            )}
            {cfg.dmx.enabled && dmx?.connected && (
              <p className="font-mono text-[12px] text-dim">
                {dmx.packets
                  ? `${(dmx.age ?? 0) > QUIET_AFTER_S ? 0 : (dmx.pps ?? 0).toFixed(0)} packets/s · last ${lastSeen(dmx.age)}`
                  : "No DMX received yet: connect the DMX line to the Pro's input."}
                {!!dmx.damaged && ` · ${dmx.damaged} damaged`}
              </p>
            )}
            <p className="text-[11px] leading-snug text-dim">
              Enttec DMX USB Pro only. A Pro that receives can't send, so use a second interface for the output. The DMX input is one universe; the Control Desk calls it "DMX input".
            </p>
          </>
        )}
      </Status>
    </Section>
  )
}
