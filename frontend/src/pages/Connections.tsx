import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { api, type AudioDevice, type OscStatus, type SerialDevice } from '../api'
import { LiveBandMeter } from '../components/LiveBandMeter'
import { ArtnetInputSection, DmxInputSection, useLiveInput } from '../components/LiveInputSection'
import { MidiMappingSection } from '../components/MidiMapping'
import { OutputMonitor } from '../components/OutputMonitor'
import { SubTabs, useSubTab, type SubTab } from '../components/SubTabs'
import { ARTNET_UNIVERSES, Button, DevicePicker, NumberInput, Row, SaveBar, Section, StatusDot, Toggle, UniverseSelect, deviceKey, useSettings } from '../components/forms'
import { CONNECTION_TABS, type ConnectionTab } from '../pages'
import { reconnectLine } from '../reconnect'
import { savedPortState } from '../savedPort'
import { unchanged, usePolling } from '../usePolling'
import { midiNotice } from '../midiNotice'
import type { EngineConnection } from '../useEngine'
import { useFieldNav } from '../useFieldNav'

const MAX_ENTTEC = 4 // as in the backend (config/models.py)

interface BandInfo {
  edges: number[]
  centres: number[]
  trigger_weights: number[]
}

/** The OSC section's dot: off, nothing to send (no file, or only entries that are ignored), a problem, or sending. */
function oscDot(osc: OscStatus | null | undefined, file: string): { ok: boolean | null; label: string; error?: string | null } {
  if (!osc) return { ok: null, label: 'off' }
  if (osc.error) return { ok: false, label: 'not sending', error: osc.error }
  if (osc.file_error) return { ok: false, label: osc.messages ? 'file problem' : 'no messages', error: osc.file_error }
  if (osc.messages === 0) return { ok: null, label: file ? 'nothing to send' : 'no file', error: osc.ignored[0] }
  return { ok: osc.connected ?? null, label: 'sending' }
}

const KIND_NAMES = { pro: 'Enttec DMX USB Pro or compatible', open: 'Enttec Open DMX USB (bare FTDI)' } as const

const TABS: SubTab<ConnectionTab>[] = [
  { id: 'audio', label: 'Audio', tip: 'Audio input: the device, its channels and gain, and the 32 frequency bands' },
  { id: 'midi', label: 'MIDI', tip: 'MIDI controller: its port, the MIDI monitor and the mapping of its controls to the macros' },
  { id: 'dmx', label: 'DMX & Art-Net', tip: 'DMX out and in, side by side: Art-Net over the network and the USB DMX interfaces; and the live output of every fixture' },
  { id: 'osc', label: 'OSC', tip: 'OSC output: the base colours to another program or device on the network' },
  { id: 'serial', label: 'Serial', tip: 'The PitchPlease v2 strips on a USB serial line' },
]

/**
 * Connections (item 60): what goes in and out of the app, one subpage tab per topic (Q / E step through them). The
 * settings of all tabs are one draft with one Save; the live input and the MIDI mapping save on their own.
 */
export function Connections({ engine }: { engine: EngineConnection }) {
  // keys (rigKeys.ts, useFieldNav.ts): W S A D move over the controls, ⏎ edits the highlighted one
  const pageRef = useRef<HTMLDivElement>(null)
  useFieldNav({ root: pageRef })
  const [tab, setTab] = useSubTab('Connections', CONNECTION_TABS, 'audio')

  const settingsApi = useSettings()
  const { settings, dirty, save, reload, message } = settingsApi
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([])
  const [midiPorts, setMidiPorts] = useState<string[]>([])
  const [controllerLabels, setControllerLabels] = useState<Record<string, string>>({})
  const [serialDevices, setSerialDevices] = useState<SerialDevice[]>([])
  const liveInput = useLiveInput()

  // the input lists, as they are right now (item 34: no button to look again; the page reads them every few seconds)
  const loadLists = useCallback(
    () =>
      Promise.all([
        api.get<AudioDevice[]>('/api/devices/audio').then((d) => setAudioDevices((prev) => unchanged(prev, d))),
        api.get<string[]>('/api/devices/midi').then((p) => setMidiPorts((prev) => unchanged(prev, p))),
        api
          .get<{ available: string[]; labels: Record<string, string> }>('/api/controllers')
          .then((c) => setControllerLabels((prev) => unchanged(prev, c.labels))),
      ]),
    [],
  )
  const refresh = () => {
    loadLists().catch(() => {})
  }
  const rescanSerial = () => api.get<SerialDevice[]>('/api/devices/serial').then(setSerialDevices)
  useEffect(() => {
    refresh()
    rescanSerial()
  }, [])
  usePolling(loadLists)
  // a device that came back by itself is in the lists now: read them again, so the fields stop saying "(not found)"
  const audioBack = engine.state?.io?.audio?.reconnect?.back
  const midiBack = engine.state?.io?.midi?.reconnect?.back
  useEffect(() => {
    if (audioBack != null || midiBack != null) refresh()
  }, [audioBack, midiBack])

  return (
    <div ref={pageRef} className="flex flex-col gap-1.5 wide:h-full">
      <div className="flex flex-none flex-wrap items-center gap-1.5">
        <SubTabs tabs={TABS} value={tab} onChange={setTab} />
        <span className="flex-1" />
        {(tab === 'dmx' || tab === 'serial') && (
          <Button onClick={rescanSerial} tip="Look for newly plugged-in USB devices; unplugged ones stay selected and show as not connected">
            Rescan USB devices
          </Button>
        )}
        <SaveBar dirty={dirty} save={save} reload={reload} message={message} />
      </div>
      {settings && (
        <div className="flex min-h-0 flex-1 flex-col">
          {tab === 'audio' && <AudioTab engine={engine} settingsApi={settingsApi} audioDevices={audioDevices} />}
          {tab === 'midi' && <MidiTab engine={engine} settingsApi={settingsApi} midiPorts={midiPorts} controllerLabels={controllerLabels} refresh={refresh} />}
          {tab === 'dmx' && <DmxTab engine={engine} settingsApi={settingsApi} devices={serialDevices} liveInput={liveInput} />}
          {tab === 'osc' && <OscTab engine={engine} settingsApi={settingsApi} />}
          {tab === 'serial' && <SerialTab engine={engine} settingsApi={settingsApi} devices={serialDevices} />}
        </div>
      )}
    </div>
  )
}

type SettingsApi = ReturnType<typeof useSettings>

function AudioTab({ engine, settingsApi, audioDevices }: { engine: EngineConnection; settingsApi: SettingsApi; audioDevices: AudioDevice[] }) {
  const { settings, update } = settingsApi
  const [bands, setBands] = useState<BandInfo | null>(null)
  useEffect(() => {
    api.get<BandInfo>('/api/audio/bands').then(setBands)
  }, [])
  const a = settings!.audio
  const io = engine.state?.io
  const selected = audioDevices.find((d) => a.device && d.label.toLowerCase().includes(a.device.toLowerCase()))
  const defaultDevice = audioDevices.find((d) => d.default)
  // what the running input really listens to (a device with fewer inputs than set runs on the channels it has)
  const live = io?.audio?.running && io.audio.device_inputs ? io.audio : null
  const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`
  const audioLine = reconnectLine(io?.audio)
  // no blocks arrive: the lights hold the look they had (item 30), so the bands below are the held ones, not live
  const bandsHeld = !!io?.audio && !io.audio.running
  const inputsNote = live
    ? `device has ${plural(live.device_inputs ?? 0, 'input')} · using ${live.channels?.length === 1 ? 'channel ' : ''}${live.channels?.join(', ')}`
    : selected
      ? `device has ${plural(selected.channels, 'input')}`
      : null

  return (
    <Section
      index="01"
      title="Audio input" icon="in"
      right={<StatusDot ok={io?.audio ? io.audio.running : null} label={io?.audio?.running ? 'running' : 'stopped'} error={io?.audio?.error} tip="Whether the audio input is open and being analysed" />}
      tip="The sound that drives the strobo and the idle mask: it is split into 32 frequency bands"
    >
      <div className="grid gap-x-6 wide:grid-cols-2">
        <div>
          <Row label="Device" hint="Audio input device (a mixer's master out, a line input or a microphone); Save restarts the input">
            <select className="w-full" value={selected?.label ?? a.device ?? ''} onChange={(e) => update((s) => (s.audio.device = e.target.value || null))}>
              <option value="">System default{defaultDevice ? ` (${defaultDevice.name})` : ''}</option>
              {a.device && !selected && <option value={a.device}>{a.device} (not found)</option>}
              {audioDevices.map((d) => (
                <option key={d.index} value={d.label}>
                  {d.label} — {d.channels} in
                </option>
              ))}
            </select>
          </Row>
          <Row label="Input channels" hint="Numbers of the device inputs to listen to, 1-based, comma separated; they are summed to mono">
            <input
              type="text"
              className="w-32"
              value={a.channels.join(', ')}
              onChange={(e) =>
                update(
                  (s) =>
                    (s.audio.channels = e.target.value
                      .split(',')
                      .map((x) => parseInt(x.trim(), 10))
                      .filter((x) => x > 0)),
                )
              }
            />
            {inputsNote && <span className="text-[11px] text-dim">{inputsNote}</span>}
          </Row>
          <Row label="Gain" hint="Input gain before the analysis: raise it for a quiet signal. The bar shows the input level">
            <NumberInput value={a.gain} min={0} onChange={(v) => update((s) => (s.audio.gain = v))} />
            <div className="h-2 w-40 bg-panel-2" data-hint="info" data-tip="Input level after the gain; if it hits the right end on loud music, lower the gain or the source">
              <div className="h-2 dot-on" style={{ width: `${Math.min(1, io?.audio?.level ?? 0) * 100}%` }} />
            </div>
          </Row>
        </div>
        <div>
          {io?.audio?.error ? (
            <div className="my-1 border border-edge px-2 py-1.5 text-[12px]" role="alert">
              ✕ Audio input stopped: {io.audio.error}
            </div>
          ) : io?.audio?.warning ? (
            <div className="my-1 px-2 py-1 text-[11px]" role="status">
              ! {io.audio.warning}
            </div>
          ) : null}
          {audioLine && (
            <div className="my-1 px-2 text-[11px] text-dim" role="status">
              {audioLine}
            </div>
          )}
        </div>
      </div>
      <div className="mt-3" data-tip="Level of each frequency band, low to high. Dotted line: how much a band counts for the strobo trigger (bass most)">
        <div className="mb-1 flex justify-between text-[11px] text-dim">
          <span>{bands ? `${bands.edges[0]} Hz` : ''}</span>
          <span>{bandsHeld ? 'input stopped · lights hold the last look' : '32 bands · faint = band maximum, medium = live, bright = band minimum · dotted line = strobo trigger weight'}</span>
          <span>{bands ? `${bands.edges[bands.edges.length - 1]} Hz` : ''}</span>
        </div>
        <div style={{ opacity: bandsHeld ? 0.35 : 1 }}>
          <LiveBandMeter engine={engine} weights={bands?.trigger_weights} height={420} />
        </div>
      </div>
    </Section>
  )
}

function MidiTab({
  engine,
  settingsApi,
  midiPorts,
  controllerLabels,
  refresh,
}: {
  engine: EngineConnection
  settingsApi: SettingsApi
  midiPorts: string[]
  controllerLabels: Record<string, string>
  refresh: () => void
}) {
  const { settings, update, applySaved } = settingsApi
  const io = engine.state?.io
  const midiNote = midiNotice(io?.midi)
  const saved = savedPortState(settings!.midi_input ?? '', midiPorts, io?.midi)
  const midiLine = reconnectLine(io?.midi)
  return (
    <div className="grid gap-1.5 wide:h-full wide:min-h-0 wide:grid-cols-[25rem_minmax(0,1fr)]">
      <Section
        index="01"
        title="MIDI controller" icon="in"
        className="wide:min-h-0"
        right={<StatusDot ok={io?.midi ? Boolean(io.midi.port) : null} label={io?.midi?.port ?? 'not connected'} error={io?.midi?.error} tip="The MIDI port the controller is connected to" />}
        tip="The hardware controller (e.g. Launch Control XL 3) that drives the macros: faders, knobs and buttons"
      >
        <Row label="Controller mapping" hint="The controller file in use. It is chosen in the MIDI mapping (Use this controller / Stop using it); controller files are shipped with the app or live in controllers/ in your data folder" plain>
          <span className="truncate">{settings!.active_controller ? controllerLabels[settings!.active_controller] ?? settings!.active_controller : 'none'}</span>
        </Row>
        <Row label="MIDI port" hint="MIDI input to listen to; 'from controller file' picks the port by the name stored in the mapping">
          <select value={settings!.midi_input ?? ''} onChange={(e) => update((s) => (s.midi_input = e.target.value || null))}>
            <option value="">from controller file</option>
            {settings!.midi_input && saved.state === 'renamed' && (
              <option value={settings!.midi_input}>
                {settings!.midi_input} (now {saved.now})
              </option>
            )}
            {settings!.midi_input && saved.state === 'missing' && <option value={settings!.midi_input}>{settings!.midi_input} (not found)</option>}
            {midiPorts.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </Row>
        {midiNote?.level === 'error' && (
          <div className="my-1 border border-edge px-2 py-1.5 text-[12px]" role="alert">
            ✕ {midiNote.text}
          </div>
        )}
        {midiNote?.level === 'warning' && (
          <div className="my-1 px-2 py-1 text-[11px]" role="status">
            ! {midiNote.text}
          </div>
        )}
        {midiLine && (
          <div className="my-1 px-2 text-[11px] text-dim" role="status">
            {midiLine}
          </div>
        )}
        <div className="mt-3 flex min-h-0 flex-1 flex-col" data-tip="Every MIDI message that arrives and the macro it moves; use it to check cables and the mapping">
          <div className="mb-1 flex flex-none justify-between gap-2 text-[11px] text-dim">
            <span>MIDI monitor, newest first</span>
            <span className="truncate">
              {io?.midi?.received ?? 0} received · mapping on channel {io?.midi?.channel ?? '–'}
            </span>
          </div>
          <div className="h-56 overflow-x-hidden overflow-y-auto bg-panel-2 p-2 font-mono text-[11px] wide:h-auto wide:min-h-0 wide:flex-1">
            {(io?.midi?.recent ?? []).length === 0 && <div className="text-dim">Nothing received yet — move a fader or knob on the controller.</div>}
            {(io?.midi?.recent ?? []).map((m, i) => (
              <div key={`${m.t}-${i}`} className="flex gap-3">
                <span className="flex-1 truncate text-ink" title={`raw message: ${m.text} (the raw message counts channels from 0)`}>
                  {/* the channel as on the controller (1-16), not the 0-15 of the raw message */}
                  {m.kind ? `ch ${m.channel} · ${m.kind === 'cc' ? 'CC' : 'note'} ${m.number} · ${m.value}` : m.text}
                </span>
                {m.macro ? <span className="text-ink">→ {m.macro}</span> : <span className="text-ink">{m.note}</span>}
              </div>
            ))}
          </div>
        </div>
      </Section>

      <MidiMappingSection
        index="02"
        className="wide:min-h-0"
        engine={engine}
        midiPorts={midiPorts}
        onActiveChanged={(name) => {
          applySaved((s) => (s.active_controller = name))
          refresh() // the labels the controller section shows (the controller's name) may not know a file created here yet
        }}
      />
    </div>
  )
}

function DmxTab({ engine, settingsApi, devices, liveInput }: { engine: EngineConnection; settingsApi: SettingsApi; devices: SerialDevice[]; liveInput: ReturnType<typeof useLiveInput> }) {
  const { settings, update } = settingsApi
  const [advanced, setAdvanced] = useState<Record<number, boolean>>({}) // interface index -> the unusual settings are open
  const o = settings!.outputs
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
    // inputs on the left, outputs in the middle (Art-Net above, USB below), the live output on the right (item 70)
    <div className="grid gap-1.5 wide:h-full wide:min-h-0 wide:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.85fr)] wide:grid-rows-[minmax(0,auto)_minmax(0,1fr)]">
      <ArtnetInputSection index="01" input={liveInput} engine={engine} className="wide:min-h-0" />

      <Section
        index="03"
        title="Art-Net output" icon="out"
        className="wide:min-h-0"
        bodyClassName="p-3 pt-3.5 overflow-y-auto"
        right={<StatusDot ok={io?.artnet?.connected ?? null} label={io?.artnet ? 'sending' : 'off'} error={io?.artnet?.error} tip="Whether Art-Net packets are being sent" />}
        tip="DMX over the network (Art-Net): each target sends one universe to one node, or to a broadcast address"
      >
        <div className="flex items-center gap-2.5">
          <Toggle checked={o.artnet.enabled} tip="Send Art-Net to the targets below; off keeps them but sends nothing" onChange={(v) => update((s) => (s.outputs.artnet.enabled = v))} />
          <span className="lbl text-[12px]">Send Art-Net</span>
        </div>
        {/* the targets as a small table: one universe to one IP address each */}
        <div className="mt-2 grid grid-cols-[4.5rem_minmax(0,1fr)_4.5rem_auto] items-center gap-x-2 gap-y-1.5 text-[13px]">
          {o.artnet.targets.length > 0 && (
            <>
              <span className="lbl text-[10px] text-dim">Universe</span>
              <span className="lbl text-[10px] text-dim">→ IP address</span>
              <span className="lbl text-[10px] text-dim">Art-Net</span>
              <span />
            </>
          )}
          {o.artnet.targets.map((t, i) => (
            <Fragment key={i}>
              <UniverseSelect className="w-full" value={t.universe} tip="Universe of this app (as on the Rig page) to send to this target" onChange={(v) => update((s) => (s.outputs.artnet.targets[i].universe = v))} />
              <input
                type="text"
                className="w-full"
                data-tip="IP address of the Art-Net node; 255 in the last numbers (e.g. 2.255.255.255) broadcasts to a whole network"
                value={t.ip}
                onChange={(e) => update((s) => (s.outputs.artnet.targets[i].ip = e.target.value))}
              />
              <UniverseSelect
                className="w-full"
                value={t.artnet_universe ?? t.universe}
                options={ARTNET_UNIVERSES}
                tip="Art-Net universe on the wire (what the node listens to), 0–15; by default the same number as the universe"
                onChange={(v) => update((s) => (s.outputs.artnet.targets[i].artnet_universe = v))}
              />
              <Button onClick={() => update((s) => s.outputs.artnet.targets.splice(i, 1))} tip="Remove this Art-Net target (written with Save)">
                ✕
              </Button>
            </Fragment>
          ))}
        </div>
        <div className="mt-2">
          <Button onClick={() => update((s) => s.outputs.artnet.targets.push({ universe: 0, ip: '127.255.255.255' }))} tip="Add a target: one universe sent to one IP address">
            Add target
          </Button>
        </div>
      </Section>

      <Section index="05" title="Live output" icon="out" className="wide:row-span-2 wide:min-h-0" bodyClassName="p-3 overflow-y-auto" tip="What the fixtures send right now, after gamma: the DMX and serial data that leaves this app">
        <OutputMonitor state={engine.state} />
      </Section>

      <DmxInputSection index="02" input={liveInput} engine={engine} className="wide:min-h-0" />

      <Section
        index="04"
        title="USB DMX output" icon="out"
        className="wide:min-h-0"
        bodyClassName="p-3 overflow-y-auto"
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
                      {kind === 'open' && settings!.fps > (st?.max_fps ?? 30) && (
                        <p
                          className="text-[12px] text-dim"
                          data-tip="A bare FTDI interface needs about 31 ms for a frame and its break; started sooner, the break cuts into the end of the last frame and the lights flash. So this interface sends at most 30 frames per second, while the Pro, Art-Net and the rest keep the app's frame rate"
                        >
                          Sends at most {st?.max_fps ?? 30} fps (the app runs at {settings!.fps}): an Open DMX can't keep up with more.
                        </p>
                      )}
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
                                tip="Writes the timing of every frame to the log file: a summary every 10 seconds (frames per second, longest write, largest gap, dropped frames) and one line for each frame that came more than twice the frame time after the one before. For finding out why a frame is lost now and then. Open the log with File → Open logs folder. Leave it off otherwise"
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
    </div>
  )
}

function OscTab({ engine, settingsApi }: { engine: EngineConnection; settingsApi: SettingsApi }) {
  const { settings, update } = settingsApi
  const [oscFiles, setOscFiles] = useState<{ available: string[]; folder: string }>({ available: [], folder: '' })
  const loadOscFiles = () => api.get<{ available: string[]; folder: string }>('/api/osc/files').then(setOscFiles)
  useEffect(() => {
    loadOscFiles().catch(() => undefined)
  }, [])
  usePolling(loadOscFiles) // a file put into the osc folder shows up in the list
  const o = settings!.outputs
  const osc = engine.state?.io.outputs?.osc
  const dot = oscDot(osc, o.osc.file)
  return (
    <div className="grid gap-1.5 wide:grid-cols-2">
      <Section
        index="01"
        title="OSC output" icon="out"
        right={<StatusDot ok={dot.ok} label={dot.label} error={dot.error} tip="Whether OSC messages are being sent" />}
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
        <Row label="Messages" hint={`The file that says what to send, to which address and in which format. The app ships examples; your own files go in ${oscFiles.folder || 'the osc folder of your data folder'}. A file is read again within a second when you edit it`}>
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
        {osc && (
          <div className="mt-1 text-[11px] text-dim" data-hint="info" data-tip="What the file makes: entries that don't fit (an unknown 'what', a format that doesn't suit it, a bad address) are ignored">
            {osc.messages} message{osc.messages === 1 ? '' : 's'} from the file
            {osc.ignored.length > 0 && ` · ${osc.ignored.length} ignored: ${osc.ignored[0]}${osc.ignored.length > 1 ? ' …' : ''}`}
            {osc.file_error && ` · ${osc.file_error}`}
          </div>
        )}
      </Section>
    </div>
  )
}

function SerialTab({ engine, settingsApi, devices }: { engine: EngineConnection; settingsApi: SettingsApi; devices: SerialDevice[] }) {
  const { settings, update } = settingsApi
  const o = settings!.outputs
  const v2 = engine.state?.io.outputs?.pitchpls_v2
  return (
    <div className="grid gap-1.5 wide:grid-cols-2">
      <Section
        index="01"
        title="PitchPlease v2 (serial)" icon="out"
        tip="The PitchPlease v2 strips take RGB bytes over a USB serial line instead of DMX (fixture type output: v2 serial)"
        right={<StatusDot ok={v2?.connected ?? null} label={v2 ? (v2.connected ? 'connected' : 'not connected') : 'off'} error={v2?.error} />}
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
    </div>
  )
}
