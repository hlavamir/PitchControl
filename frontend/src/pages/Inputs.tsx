import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type AudioDevice } from '../api'
import { BandMeter } from '../components/BandMeter'
import { LiveInputSection } from '../components/LiveInputSection'
import { MidiMappingSection } from '../components/MidiMapping'
import { NumberInput, Row, SaveBar, Section, StatusDot, useSettings } from '../components/forms'
import { reconnectLine } from '../reconnect'
import { savedPortState } from '../savedPort'
import { unchanged, usePolling } from '../usePolling'
import { midiNotice } from '../midiNotice'
import type { EngineConnection } from '../useEngine'
import { useFieldNav } from '../useFieldNav'

interface BandInfo {
  edges: number[]
  centres: number[]
  trigger_weights: number[]
}

export function Inputs({ engine }: { engine: EngineConnection }) {
  // keys (rigKeys.ts, useFieldNav.ts): W S A D move over the controls, ⏎ edits the highlighted one
  const pageRef = useRef<HTMLDivElement>(null)
  useFieldNav({ root: pageRef })

  const { settings, update, applySaved, save, dirty, reload, message } = useSettings()
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([])
  const [midiPorts, setMidiPorts] = useState<string[]>([])
  const [controllerLabels, setControllerLabels] = useState<Record<string, string>>({})
  const [bands, setBands] = useState<BandInfo | null>(null)

  // the three lists, as they are right now (item 34: no button to look again; the page reads them every few seconds)
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
  useEffect(() => {
    refresh()
    api.get<BandInfo>('/api/audio/bands').then(setBands)
  }, [])
  usePolling(loadLists)
  // a device that came back by itself is in the lists now: read them again, so the fields stop saying "(not found)"
  const audioBack = engine.state?.io?.audio?.reconnect?.back
  const midiBack = engine.state?.io?.midi?.reconnect?.back
  useEffect(() => {
    if (audioBack != null || midiBack != null) refresh()
  }, [audioBack, midiBack])
  if (!settings) return null
  const a = settings.audio
  const io = engine.state?.io
  const selected = audioDevices.find((d) => a.device && d.label.toLowerCase().includes(a.device.toLowerCase()))
  const defaultDevice = audioDevices.find((d) => d.default)
  // what the running input really listens to (a device with fewer inputs than set runs on the channels it has)
  const live = io?.audio?.running && io.audio.device_inputs ? io.audio : null
  const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`
  const midiNote = midiNotice(io?.midi)
  const saved = savedPortState(settings.midi_input ?? '', midiPorts, io?.midi)
  const audioLine = reconnectLine(io?.audio)
  // no blocks arrive: the lights hold the look they had (item 30), so the bands below are the held ones, not live
  const bandsHeld = !!io?.audio && !io.audio.running
  const midiLine = reconnectLine(io?.midi)
  const inputsNote = live
    ? `device has ${plural(live.device_inputs ?? 0, 'input')} · using ${live.channels?.length === 1 ? 'channel ' : ''}${live.channels?.join(', ')}`
    : selected
      ? `device has ${plural(selected.channels, 'input')}`
      : null

  return (
    // sections take half the page width side by side, or the full width under each other
    <div ref={pageRef} className="grid gap-1.5 wide:grid-cols-2">
      <div className="flex justify-end wide:col-span-2">
        <SaveBar dirty={dirty} save={save} reload={reload} message={message} />
      </div>

      <Section
        index="01"
        title="Audio input"
        right={
          <StatusDot
            ok={io?.audio ? io.audio.running : null}
            label={io?.audio?.running ? 'running' : 'stopped'}
            error={io?.audio?.error}
            tip="Whether the audio input is open and being analysed"
          />
        }
        tip="The sound that drives the strobo and the idle mask: it is split into 32 frequency bands"
      >
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
        <Row label="Gain" hint="Input gain before the analysis: raise it for a quiet signal. The bar shows the input level">
          <NumberInput value={a.gain} min={0} onChange={(v) => update((s) => (s.audio.gain = v))} />
          <div className="h-2 w-40 bg-panel-2" data-hint="info" data-tip="Input level after the gain; if it hits the right end on loud music, lower the gain or the source">
            <div className="h-2 dot-on" style={{ width: `${Math.min(1, io?.audio?.level ?? 0) * 100}%` }} />
          </div>
        </Row>
        <div className="mt-3" data-tip="Level of each frequency band, low to high. Dotted line: how much a band counts for the strobo trigger (bass most)">
          <div className="mb-1 flex justify-between text-[11px] text-dim">
            <span>{bands ? `${bands.edges[0]} Hz` : ''}</span>
            <span>{bandsHeld ? 'input stopped · lights hold the last look' : '32 bands · dotted line = strobo trigger weight'}</span>
            <span>{bands ? `${bands.edges[bands.edges.length - 1]} Hz` : ''}</span>
          </div>
          <div style={{ opacity: bandsHeld ? 0.35 : 1 }}>
            <BandMeter bands={engine.state?.bands ?? []} peaks={engine.state?.band_peaks} weights={bands?.trigger_weights} height={100} />
          </div>
        </div>
      </Section>

      <Section
        index="02"
        title="MIDI controller"
        right={
          <StatusDot
            ok={io?.midi ? Boolean(io.midi.port) : null}
            label={io?.midi?.port ?? 'not connected'}
            error={io?.midi?.error}
            tip="The MIDI port the controller is connected to"
          />
        }
        tip="The hardware controller (e.g. Launch Control XL 3) that drives the macros: faders, knobs and buttons"
      >
        <Row label="Controller mapping" hint="The controller file in use. It is chosen in section 03 below (Use this controller / Stop using it); controller files are shipped with the app or live in controllers/ in your data folder" plain>
          <span className="truncate">{settings.active_controller ? controllerLabels[settings.active_controller] ?? settings.active_controller : 'none'}</span>
          <span className="text-[11px] text-dim">change it in section 03 below</span>
        </Row>
        <Row label="MIDI port" hint="MIDI input to listen to; 'from controller file' picks the port by the name stored in the mapping">
          <select value={settings.midi_input ?? ''} onChange={(e) => update((s) => (s.midi_input = e.target.value || null))}>
            <option value="">from controller file</option>
            {settings.midi_input && saved.state === 'renamed' && (
              <option value={settings.midi_input}>
                {settings.midi_input} (now {saved.now})
              </option>
            )}
            {settings.midi_input && saved.state === 'missing' && <option value={settings.midi_input}>{settings.midi_input} (not found)</option>}
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
        <div className="mt-3" data-tip="Every MIDI message that arrives and the macro it moves; use it to check cables and the mapping">
          <div className="mb-1 flex justify-between text-[11px] text-dim">
            <span>MIDI monitor — last messages (newest first)</span>
            <span>
              {io?.midi?.received ?? 0} received · mapping on channel {io?.midi?.channel ?? '–'}
            </span>
          </div>
          <div className="h-56 overflow-x-hidden overflow-y-auto bg-panel-2 p-2 font-mono text-[11px]">
            {(io?.midi?.recent ?? []).length === 0 && (
              <div className="text-dim">Nothing received yet — move a fader or knob on the controller.</div>
            )}
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

      <MidiMappingSection engine={engine} midiPorts={midiPorts} onActiveChanged={(name) => {
          applySaved((s) => (s.active_controller = name))
          refresh() // the labels section 02 shows (the controller's name) may not know a file created in section 03 yet
        }}
      />

      <LiveInputSection index="04" engine={engine} />
    </div>
  )
}
