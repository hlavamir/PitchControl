import { useEffect, useRef, useState } from 'react'
import { api, type DeviceRef, type OscStatus, type SerialDevice } from '../api'
import { OutputMonitor } from '../components/OutputMonitor'
import { ARTNET_UNIVERSES, Button, NumberInput, Row, SaveBar, Section, StatusDot, Toggle, UniverseSelect, useSettings } from '../components/forms'
import type { EngineConnection } from '../useEngine'
import { usePolling } from '../usePolling'
import { useFieldNav } from '../useFieldNav'

function deviceKey(d: DeviceRef | SerialDevice): string {
  return d.serial_number ? `sn:${d.serial_number}` : `port:${d.port ?? ''}`
}

function DevicePicker({ value, devices, onChange }: { value: DeviceRef; devices: SerialDevice[]; onChange: (d: DeviceRef) => void }) {
  const current = deviceKey(value)
  const known = devices.some((d) => deviceKey(d) === current)
  return (
    <select
      className="w-full"
      data-tip="USB device of this output; chosen by serial number, so it survives a different USB port"
      value={current}
      onChange={(e) => {
        const d = devices.find((x) => deviceKey(x) === e.target.value)
        onChange(
          d
            ? { serial_number: d.serial_number, vid: d.vid, pid: d.pid, description: d.description, port: d.port }
            : {},
        )
      }}
    >
      <option value="port:">— select a USB device —</option>
      {!known && current !== 'port:' && (
        <option value={current}>
          {value.description ?? 'configured device'} {value.serial_number ?? value.port} (not connected)
        </option>
      )}
      {devices.map((d) => (
        <option key={deviceKey(d) + d.port} value={deviceKey(d)}>
          {d.label}
        </option>
      ))}
    </select>
  )
}

const MAX_ENTTEC = 4 // as in the backend (config/models.py)

/** The OSC section's dot: off, nothing to send (no file, or only entries that are ignored), a problem, or sending. */
function oscDot(osc: OscStatus | null | undefined, file: string): { ok: boolean | null; label: string; error?: string | null } {
  if (!osc) return { ok: null, label: 'off' }
  if (osc.error) return { ok: false, label: 'not sending', error: osc.error }
  if (osc.file_error) return { ok: false, label: osc.messages ? 'file problem' : 'no messages', error: osc.file_error }
  if (osc.messages === 0) return { ok: null, label: file ? 'nothing to send' : 'no file', error: osc.ignored[0] }
  return { ok: osc.connected ?? null, label: 'sending' }
}

const KIND_NAMES = { pro: 'Enttec DMX USB Pro or compatible', open: 'Enttec Open DMX USB (bare FTDI)' } as const

export function Output({ engine }: { engine: EngineConnection }) {
  // keys (rigKeys.ts, useFieldNav.ts): W S A D move over the controls, ⏎ edits the highlighted one
  const pageRef = useRef<HTMLDivElement>(null)
  useFieldNav({ root: pageRef })

  const { settings, update, save, dirty, reload, message } = useSettings()
  const [devices, setDevices] = useState<SerialDevice[]>([])
  const [advanced, setAdvanced] = useState<Record<number, boolean>>({}) // interface index -> the unusual settings are open
  const refresh = () => api.get<SerialDevice[]>('/api/devices/serial').then(setDevices)
  useEffect(() => {
    refresh()
  }, [])
  const [oscFiles, setOscFiles] = useState<{ available: string[]; folder: string }>({ available: [], folder: '' })
  const loadOscFiles = () => api.get<{ available: string[]; folder: string }>('/api/osc/files').then(setOscFiles)
  useEffect(() => {
    loadOscFiles().catch(() => undefined)
  }, [])
  usePolling(loadOscFiles) // a file put into the osc folder shows up in the list
  if (!settings) return null
  const o = settings.outputs
  const io = engine.state?.io.outputs
  // two interfaces on one device would garble both streams: the backend starts only the first
  const used = new Map<string, number>()
  const sameAs = o.enttec.map((e, i) => {
    const key = deviceKey(e.device)
    if (!e.enabled || key === 'port:') return null
    const first = used.get(key)
    if (first === undefined) used.set(key, i)
    return first ?? null
  })

  return (
    // settings and live output take half the page width each, or the full width under each other
    <div ref={pageRef} className="grid gap-1.5 wide:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex justify-between">
        <Button onClick={refresh} tip="Look for newly plugged-in USB devices; unplugged ones stay selected and show as not connected">
          Rescan USB devices
        </Button>
        <SaveBar dirty={dirty} save={save} reload={reload} message={message} />
      </div>

      <Section
        index="01"
        title="USB DMX interfaces"
        tip="DMX over USB: each interface (Enttec DMX USB Pro and compatibles, or the Enttec Open DMX USB) sends one universe to the lights on its cable"
        right={
          <>
            <span>
              {o.enttec.length} / {MAX_ENTTEC} interfaces
            </span>
            <button
              disabled={o.enttec.length >= MAX_ENTTEC}
              data-tip={o.enttec.length >= MAX_ENTTEC ? `Maximum of ${MAX_ENTTEC} interfaces reached` : 'Add another USB DMX interface, with its own device and universe (up to 4)'}
              className="lbl h-[18px] border border-edge px-2 text-[10px] text-ink disabled:opacity-40"
              onClick={() =>
                update((s) =>
                  s.outputs.enttec.push({ enabled: true, device: {}, type: 'auto', break_method: 'baud', log_timing: false, universe: s.outputs.enttec.reduce((n, x) => Math.max(n, x.universe + 1), 0) }),
                )
              }
            >
              Add interface
            </button>
          </>
        }
      >
        <div className="flex flex-col gap-2.5">
          {o.enttec.length === 0 && <p className="text-[13px] text-dim">No USB DMX interface. Add one for each interface you plug in; each sends its own universe.</p>}
          {o.enttec.map((e, i) => {
            const st = io?.enttec?.[i]
            return (
              <div key={i} className="flex flex-col gap-1.5 border border-edge p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2.5">
                    <Toggle checked={e.enabled} tip="Switch on to send this interface's universe; off keeps the settings but sends nothing" onChange={(v) => update((s) => (s.outputs.enttec[i].enabled = v))} />
                    <span className="lbl text-[12px]" data-tip="Switch on to send this interface's universe; off keeps the settings but sends nothing">
                      Interface {i + 1}
                    </span>
                  </span>
                  <span className="flex items-center gap-3">
                    <StatusDot ok={st ? st.connected : null} label={st ? (st.connected ? 'connected' : 'not connected') : 'off'} error={st?.error} tip="Whether this interface is open and receiving frames (after Save)" />
                    <Button onClick={() => update((s) => s.outputs.enttec.splice(i, 1))} tip="Remove this interface; the ones below move up (written with Save)">
                      Remove
                    </Button>
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[13px]">
                  <span className="text-dim">Device</span>
                  <div className="min-w-0 flex-1">
                    <DevicePicker value={e.device} devices={devices} onChange={(d) => update((s) => (s.outputs.enttec[i].device = d))} />
                  </div>
                  <span className="text-dim">Universe</span>
                  <UniverseSelect value={e.universe} tip="The universe this interface sends: fixtures with this universe on the Rig page are on its cable" onChange={(v) => update((s) => (s.outputs.enttec[i].universe = v))} />
                </div>
                {/* what the app found out about the device, and the way in to the unusual settings */}
                {(() => {
                  const found = devices.find((d) => deviceKey(d) === deviceKey(e.device))?.dmx_type ?? null
                  const kind = st?.kind ?? (e.type === 'auto' ? found ?? 'pro' : e.type)
                  const custom = e.type !== 'auto' || e.break_method !== 'baud' || e.log_timing
                  return (
                    <>
                      <div className="flex items-center justify-between gap-2 text-[12px] text-dim">
                        <span data-tip="How the app talks to this interface, found out from the USB device. The Enttec DMX USB Pro and compatible ones (DMXKing ultraDMX …) take packets; a bare FTDI interface such as the Enttec Open DMX USB needs the app to make the DMX signal itself">
                          {e.type === 'auto' ? 'Detected: ' : 'Set to: '}
                          <span className="text-ink">{KIND_NAMES[kind]}</span>
                        </span>
                        <button
                          type="button"
                          className="lbl border border-edge px-2 py-0.5 text-[10px] text-ink hover:border-dim"
                          data-tip="Unusual interfaces: choose the interface type by hand, and how the break is made"
                          onClick={() => setAdvanced((a) => ({ ...a, [i]: !a[i] }))}
                        >
                          Advanced {advanced[i] ? '▾' : '▸'}
                          {custom && <span className="ml-1 text-glow">·</span>}
                        </button>
                      </div>
                      {advanced[i] && (
                        <div className="flex flex-col gap-1.5 border-t border-seam pt-1.5 text-[12px]">
                          <div className="flex items-center gap-2">
                            <span className="w-28 text-dim">Interface type</span>
                            <select
                              className="w-auto"
                              value={e.type}
                              data-tip="Detect automatically (recommended), or force one: the Enttec DMX USB Pro protocol (also DMXKing ultraDMX …), or a bare FTDI interface such as the Enttec Open DMX USB, where the app makes the DMX signal"
                              onChange={(ev) => update((s) => (s.outputs.enttec[i].type = ev.target.value as 'auto' | 'pro' | 'open'))}
                            >
                              <option value="auto">Detect automatically</option>
                              <option value="pro">Enttec DMX USB Pro or compatible</option>
                              <option value="open">Enttec Open DMX USB (bare FTDI)</option>
                            </select>
                          </div>
                          {kind === 'open' && (
                            <div className="flex items-center gap-2">
                              <span className="w-28 text-dim">Break made by</span>
                              <select
                                className="w-auto"
                                value={e.break_method}
                                data-tip="How the 88 µs break before each frame is made: one byte at a lower baud rate (default, works with the macOS driver), or the port's break line (the macOS driver can get stuck after it until the interface is unplugged)"
                                onChange={(ev) => update((s) => (s.outputs.enttec[i].break_method = ev.target.value as 'break' | 'baud'))}
                              >
                                <option value="baud">one byte at a lower baud rate (default)</option>
                                <option value="break">the port's break line</option>
                              </select>
                            </div>
                          )}
                          {kind === 'open' && (
                            <div className="flex items-center gap-2">
                              <span className="w-28 text-dim">Log frame timing</span>
                              <Toggle
                                checked={e.log_timing}
                                tip="Writes the timing of every frame to the log file: a summary every 10 seconds (frames per second, longest write, largest gap, dropped frames) and one line for each frame that came more than twice the frame time after the one before. For finding out why a frame is lost now and then. Open the log with Settings → Open logs folder. Leave it off otherwise"
                                onChange={(v) => update((s) => (s.outputs.enttec[i].log_timing = v))}
                              />
                              <span className="text-dim">{e.log_timing ? 'on: writing to the log file' : 'off'}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )
                })()}
                {sameAs[i] !== null && <p className="text-[12px] text-glow">Same device as interface {sameAs[i]! + 1}: this one is not started.</p>}
              </div>
            )
          })}
        </div>
      </Section>

      <Section
        index="02"
        title="Art-Net"
        right={<StatusDot ok={io?.artnet?.connected ?? null} label={io?.artnet ? 'sending' : 'off'} error={io?.artnet?.error} tip="Whether Art-Net packets are being sent" />}
        tip="DMX over the network (Art-Net): each target sends one universe to one node, or to a broadcast address"
      >
        <Row label="Enabled" hint="Send Art-Net to the targets below; off keeps them but sends nothing">
          <Toggle checked={o.artnet.enabled} onChange={(v) => update((s) => (s.outputs.artnet.enabled = v))} />
        </Row>
        <div className="mt-2 flex flex-col gap-2">
          {o.artnet.targets.map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-[13px]">
              <span className="text-dim">Universe</span>
              <UniverseSelect value={t.universe} tip="Universe of this app (as on the Rig page) to send to this target" onChange={(v) => update((s) => (s.outputs.artnet.targets[i].universe = v))} />
              <span className="text-dim">→ IP</span>
              <input
                type="text"
                className="w-40"
                data-tip="IP address of the Art-Net node; 255 in the last numbers (e.g. 2.255.255.255) broadcasts to a whole network"
                value={t.ip}
                onChange={(e) => update((s) => (s.outputs.artnet.targets[i].ip = e.target.value))}
              />
              <span className="text-dim">Art-Net universe</span>
              <UniverseSelect
                value={t.artnet_universe ?? t.universe}
                options={ARTNET_UNIVERSES}
                tip="Art-Net universe on the wire (what the node listens to), 0–15; by default the same number as the universe"
                onChange={(v) => update((s) => (s.outputs.artnet.targets[i].artnet_universe = v))}
              />
              <Button onClick={() => update((s) => s.outputs.artnet.targets.splice(i, 1))} tip="Remove this Art-Net target (written with Save)">
                ✕
              </Button>
            </div>
          ))}
          <div>
            <Button
              onClick={() => update((s) => s.outputs.artnet.targets.push({ universe: 0, ip: '127.255.255.255' }))}
              tip="Add a target: one universe sent to one IP address"
            >
              Add target
            </Button>
          </div>
        </div>
      </Section>

      <Section
        index="03"
        title="PitchPlease v2 (serial)"
        tip="The PitchPlease v2 strips take RGB bytes over a USB serial line instead of DMX (fixture type output: v2 serial)"
        right={<StatusDot ok={io?.pitchpls_v2?.connected ?? null} label={io?.pitchpls_v2 ? (io.pitchpls_v2.connected ? 'connected' : 'not connected') : 'off'} error={io?.pitchpls_v2?.error} />}
      >
        <Row label="Enabled" hint="Send to the v2 strips; off keeps the settings but sends nothing">
          <Toggle checked={o.pitchpls_v2.enabled} onChange={(v) => update((s) => (s.outputs.pitchpls_v2.enabled = v))} />
        </Row>
        <Row label="Device" hint="USB serial device of the v2 controller board">
          <DevicePicker value={o.pitchpls_v2.device} devices={devices} onChange={(d) => update((s) => (s.outputs.pitchpls_v2.device = d))} />
        </Row>
        <Row label="Baudrate" hint="Serial speed; must match the v2 firmware (921600 by default)">
          <select value={o.pitchpls_v2.baudrate} onChange={(e) => update((s) => (s.outputs.pitchpls_v2.baudrate = Number(e.target.value)))}>
            {[57600, 115200, 230400, 460800, 921600].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </Row>
        <Row label="Mirror mode byte" hint="Mode byte sent after the pixels: how the firmware mirrors the 19 pixels onto its 38 LEDs (0–254)">
          <NumberInput value={o.pitchpls_v2.mode} integer min={0} max={254} onChange={(v) => update((s) => (s.outputs.pitchpls_v2.mode = v))} />
        </Row>
      </Section>

      <Section
        index="04"
        title="OSC"
        right={(() => {
          const dot = oscDot(io?.osc, o.osc.file)
          return <StatusDot ok={dot.ok} label={dot.label} error={dot.error} tip="Whether OSC messages are being sent" />
        })()}
        tip="OSC over the network (UDP): the base colours A and B, as the file below describes, to one IP address and port"
      >
        <Row label="Enabled" hint="Send the messages below; off keeps the settings but sends nothing">
          <Toggle checked={o.osc.enabled} onChange={(v) => update((s) => (s.outputs.osc.enabled = v))} />
        </Row>
        <Row label="IP address" hint="Where to send: the IP address (or name) of the computer or device that receives OSC; a broadcast address works too">
          <input type="text" className="w-40" value={o.osc.host} onChange={(e) => update((s) => (s.outputs.osc.host = e.target.value))} />
        </Row>
        <Row label="Port" hint="The UDP port the receiver listens on (1–65535)">
          <NumberInput value={o.osc.port} integer min={1} max={65535} onChange={(v) => update((s) => (s.outputs.osc.port = v))} />
        </Row>
        <Row
          label="Messages"
          hint={`The file that says what to send, to which address and in which format. The app ships examples; your own files go in ${oscFiles.folder || 'the osc folder of your data folder'}. A file is read again within a second when you edit it`}
        >
          <select className="w-full" value={o.osc.file} onChange={(e) => update((s) => (s.outputs.osc.file = e.target.value))}>
            <option value="">— no file —</option>
            {o.osc.file && !oscFiles.available.includes(o.osc.file) && <option value={o.osc.file}>{o.osc.file} (not found)</option>}
            {oscFiles.available.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </Row>
        {io?.osc && (
          <div className="mt-1 text-[11px] text-dim" data-hint="info" data-tip="What the file makes: entries that don't fit (an unknown 'what', a format that doesn't suit it, a bad address) are ignored">
            {io.osc.messages} message{io.osc.messages === 1 ? '' : 's'} from the file
            {io.osc.ignored.length > 0 && ` · ${io.osc.ignored.length} ignored: ${io.osc.ignored[0]}${io.osc.ignored.length > 1 ? ' …' : ''}`}
            {io.osc.file_error && ` · ${io.osc.file_error}`}
          </div>
        )}
      </Section>
      </div>

      <div className="min-w-0">
        <Section index="05" title="Live output" tip="What the fixtures send right now, after gamma: the DMX and serial data that leaves this app">
          <OutputMonitor state={engine.state} />
        </Section>
      </div>
    </div>
  )
}
