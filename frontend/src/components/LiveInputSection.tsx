import { useEffect, useState } from 'react'
import { api, type SerialDevice } from '../api'
import { ARTNET_DEFAULT_PORT, QUIET_AFTER_S, lastSeen, liveInputSummary, portAddressParts, portProblem, sortUniverses, type LiveInputSettings, type LiveInputView } from '../liveInput'
import type { EngineConnection } from '../useEngine'
import { usePolling } from '../usePolling'
import { Button, DevicePicker, Section, StatusDot, Toggle } from './forms'

const POLL_MS = 3000 // the adapters and USB devices change when a cable does

/**
 * Inputs → Art-Net / DMX input (item 57): DMX that comes in from outside, for the routes of the Control Desk (item 58).
 * Per computer (machine.json); the switches apply at once, the port with its button. Only the computer that runs
 * PitchControl changes it, like the network switch.
 */
export function LiveInputSection({ index, engine }: { index: string; engine: EngineConnection }) {
  const [view, setView] = useState<LiveInputView | null>(null)
  const [remote, setRemote] = useState(false)
  const [devices, setDevices] = useState<SerialDevice[]>([])
  const [port, setPort] = useState<string | null>(null) // the port field while it is being edited
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

  const live = engine.state?.io?.live_input // live, at the preview rate; the settings come from the page's own reads
  const cfg = view?.settings
  const art = live?.artnet
  const dmx = live?.dmx
  const portText = port ?? String(cfg?.artnet.port ?? ARTNET_DEFAULT_PORT)
  const portBad = port !== null ? portProblem(port) : null
  const portDirty = port !== null && port !== String(cfg?.artnet.port)
  const adapters = view?.adapters ?? []
  const adapterMissing = !!cfg?.artnet.adapter && !adapters.some((a) => a.ip === cfg.artnet.adapter)
  const universes = sortUniverses(art?.universes ?? [])
  const applyPort = () => save((s) => (s.artnet.port = Number(port))).then(() => setPort(null))

  return (
    <Section
      index={index}
      title="Art-Net / DMX input"
      right={remote ? 'this device' : liveInputSummary(live)}
      bodyClassName="p-3.5 gap-3"
      tip="DMX that comes in from another program or a console: Art-Net over the network, or DMX over an Enttec DMX USB Pro. The Control Desk routes it to output channels"
    >
      {remote && <p className="text-[12px] leading-snug text-dim">The live input can only be changed on the computer that runs PitchControl.</p>}
      {!remote && !cfg && !problem && <p className="lbl text-[11px] text-dim">…</p>}
      {cfg && (
        <>
          <div className="flex flex-col gap-2 border border-edge p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2.5">
                <Toggle checked={cfg.artnet.enabled} tip="Listen for Art-Net on this computer. Off: nothing is received (the last values of a universe stay for the routes)" onChange={(v) => save((s) => (s.artnet.enabled = v))} />
                <span className="lbl text-[12px]">Art-Net</span>
              </span>
              <StatusDot
                ok={cfg.artnet.enabled ? !!art?.listening : null}
                label={!cfg.artnet.enabled ? 'off' : art?.listening ? `listening on ${art.port}` : 'not listening'}
                error={art?.error}
                tip="Whether the Art-Net listener is open"
              />
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
                <select value={cfg.artnet.adapter} onChange={(e) => save((s) => (s.artnet.adapter = e.target.value))}>
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
              <div className="font-mono text-[12px]" data-tip="Every Art-Net universe that has sent something since the listener started, and where it comes from. A universe that went quiet keeps its last values">
                <div className="lbl grid grid-cols-[4.5rem_minmax(0,1fr)_4.5rem_5.5rem] gap-2 border-b border-seam pb-1 text-[10px] text-dim">
                  <span>Universe</span>
                  <span>Sender</span>
                  <span className="text-right">Packets/s</span>
                  <span className="text-right">Last seen</span>
                </div>
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
                {!!art?.own_ignored && <p className="pt-1 text-[11px] text-dim">{art.own_ignored} packets of this app's own output ignored.</p>}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2 border border-edge p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2.5">
                <Toggle checked={cfg.dmx.enabled} tip="Receive DMX on an Enttec DMX USB Pro. A Pro that receives doesn't send: the same device can't also be an output" onChange={(v) => save((s) => (s.dmx.enabled = v))} />
                <span className="lbl text-[12px]">DMX over USB</span>
              </span>
              <StatusDot
                ok={cfg.dmx.enabled ? !!(dmx?.enabled && dmx.connected) : null}
                label={!cfg.dmx.enabled ? 'off' : dmx?.connected ? 'receiving' : 'not connected'}
                error={dmx?.error}
                tip="Whether the Pro is open"
              />
            </div>
            <div className="flex items-center gap-2 text-[13px]">
              <span className="text-dim">Device</span>
              <div className="min-w-0 flex-1">
                <DevicePicker
                  value={cfg.dmx.device}
                  devices={devices}
                  tip="The Enttec DMX USB Pro that receives; chosen by serial number, so it survives a different USB port"
                  onChange={(d) => save((s) => (s.dmx.device = d))}
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
          </div>

          {problem && (
            <p className="text-[12px] leading-snug" role="alert">
              {problem}
            </p>
          )}
        </>
      )}
      {!remote && !cfg && problem && (
        <p className="text-[12px] leading-snug" role="alert">
          {problem}
        </p>
      )}
    </Section>
  )
}
