import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type DeviceRef, type IoStatus, type Settings } from '../api'
import { deviceState, midiDot } from '../midiDevices'
import { IoTracker, PERF_WINDOW_MS, addPerf, midiRow, perfColumns, perfScale, perfSummary, type IoLive, type PerfFrame } from '../bubbles'
import type { ConnectionTab } from '../pages'
import { artnetDot, dmxDots } from '../headerDots'
import { currentInk } from '../theme'
import type { EngineConnection } from '../useEngine'
import { LiveBandMeter } from './LiveBandMeter'
import { StatusDot } from './forms'
import type { IconName } from '../icons'
import { Icon } from './Icon'

// The header's status indicators (item 60: a click opens their Connections tab) and their detail bubbles (item 66): the
// mouse over an indicator, or the keyboard focus on it, shows a small panel below it with what is behind the light. A
// bubble only reads: it has no controls, so the pointer may cross it and the keys pass on. Touch screens get none
// (a tap is the click).

const OPEN_MS = 120 // the pointer rests this long before a bubble opens: passing over the header opens nothing
const CLOSE_MS = 160 // and may leave this long (to cross the gap into the bubble) before it closes

/** One indicator (or a group of them, the DMX interfaces) with its bubble. */
function Indicator({ children, bubble, label }: { children: ReactNode; bubble: () => ReactNode; label: string }) {
  const [open, setOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const later = (next: boolean, ms: number) => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setOpen(next), ms)
  }
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return (
    <span
      className="relative inline-flex items-center gap-4"
      onPointerEnter={(e) => e.pointerType === 'mouse' && later(true, open ? 0 : OPEN_MS)}
      onPointerLeave={(e) => e.pointerType === 'mouse' && later(false, CLOSE_MS)}
      // the keyboard focus (Tab) opens it, a click's focus doesn't: the pointer has it already
      onFocus={(e) => e.target.matches(':focus-visible') && later(true, 0)}
      onBlur={() => later(false, 0)}
      onKeyDown={(e) => e.key === 'Escape' && open && (e.stopPropagation(), setOpen(false))}
    >
      {children}
      {open && (
        <div role="tooltip" aria-label={label} className="absolute top-full right-0 z-50 pt-2 whitespace-normal" onClick={(e) => e.stopPropagation()}>
          {bubble()}
        </div>
      )}
    </span>
  )
}

/** The bubble's frame: a header strip like a Section's, the body, and what a click on the indicator does. */
function Bubble({ title, right, children, click, width = 320 }: { title: string; right?: ReactNode; children: ReactNode; click: string; width?: number }) {
  return (
    <div className="border border-edge bg-panel text-left shadow-[0_0_30px_rgb(0_0_0/0.6)]" style={{ width }}>
      <div className="flex h-[24px] items-center justify-between gap-2 border-b border-edge px-2.5 text-[11px]">
        <span className="lbl font-medium">{title}</span>
        <span className="lbl flex items-center gap-2 text-dim">{right}</span>
      </div>
      <div className="flex flex-col gap-2 p-2.5">{children}</div>
      <div className="lbl border-t border-seam px-2.5 py-1 text-[10px] text-dim">click: {click}</div>
    </div>
  )
}

/** A row of a bubble: the direction, a light, the name, the details on the right; an error below it. */
function IoRow({ icon, ok, name, detail, error, active }: { icon: IconName; ok: boolean | null; name: ReactNode; detail?: ReactNode; error?: string | null; active?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2 text-[12px]">
        <Icon name={icon} label className={ok ? 'text-ink' : 'text-dim'} />
        <span className={`inline-block size-[7px] flex-none ${active ? 'dot-on' : ok ? 'bg-ink/60' : 'border border-dim'}`} />
        <span className={`min-w-0 flex-1 truncate ${ok ? 'text-ink' : 'text-dim'}`}>{name}</span>
        {detail && <span className="flex-none font-mono text-[12px] text-dim tabular-nums">{detail}</span>}
      </div>
      {error && <span className="pl-[35px] text-[11px] leading-snug text-dim">{error}</span>}
    </div>
  )
}

function deviceLabel(d: DeviceRef | undefined): string {
  if (!d) return 'no device'
  const name = d.description || d.port || 'device'
  return d.serial_number && !name.includes(d.serial_number) ? `${name} ${d.serial_number}` : name
}

const fmtRate = (r: number | null | undefined, unit = 'fps') => (r == null ? '–' : `${r.toFixed(r >= 10 ? 0 : 1)} ${unit}`)

/** The saved output settings, read when a bubble opens: the devices, universes and IP addresses of the rows. */
function useOutputSettings(): Settings['outputs'] | null {
  const [outputs, setOutputs] = useState<Settings['outputs'] | null>(null)
  useEffect(() => {
    api.get<Settings>('/api/settings').then((s) => setOutputs(s.outputs)).catch(() => undefined)
  }, [])
  return outputs
}

// ---------------------------------------------------------------- FPS: the perf meter

const GRAPH_W = 298
const GRAPH_H = 72

function PerfGraph({ frames, target }: { frames: PerfFrame[]; target: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useLayoutEffect(() => {
    const c = canvas.current
    const ctx = c?.getContext('2d')
    if (!c || !ctx) return
    const dpr = window.devicePixelRatio || 1
    c.width = GRAPH_W * dpr
    c.height = GRAPH_H * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, GRAPH_W, GRAPH_H)
    const ink = currentInk().split(/\s+/).join(',')
    const top = perfScale(frames, target)
    const period = 1000 / Math.max(target, 1)
    const y = (ms: number) => GRAPH_H - Math.min(1, ms / top) * GRAPH_H
    const cols = perfColumns(frames, GRAPH_W / 2)
    cols.forEach((col, i) => {
      if (!col) return
      const x = i * 2
      const drop = col.interval > 1.5 * period
      // the frame time (what the lights see) as a line with a faint fill, a drop as a full bar; the engine's
      // compute time brighter at the bottom
      ctx.fillStyle = `rgba(${ink},${drop ? 1 : 0.13})`
      ctx.fillRect(x, y(col.interval), 2, GRAPH_H - y(col.interval))
      ctx.fillStyle = `rgba(${ink},0.8)`
      ctx.fillRect(x, Math.min(GRAPH_H - 1, Math.round(y(col.interval))), 2, 1)
      ctx.fillStyle = `rgba(${ink},0.55)`
      ctx.fillRect(x, y(col.tick), 2, GRAPH_H - y(col.tick))
    })
    // the target frame time
    ctx.strokeStyle = `rgba(${ink},0.9)`
    ctx.setLineDash([3, 3])
    ctx.beginPath()
    ctx.moveTo(0, Math.round(y(period)) + 0.5)
    ctx.lineTo(GRAPH_W, Math.round(y(period)) + 0.5)
    ctx.stroke()
  }, [frames, target])
  const top = perfScale(frames, target)
  const period = 1000 / Math.max(target, 1)
  return (
    <div className="relative border border-seam bg-ground" style={{ width: GRAPH_W + 2 }}>
      <canvas ref={canvas} style={{ width: GRAPH_W, height: GRAPH_H, display: 'block' }} />
      <span className="absolute top-0.5 left-1 font-mono text-[10px] text-dim">{Math.round(top)} ms</span>
      <span className="absolute right-1 font-mono text-[10px] text-ink" style={{ top: GRAPH_H - (period / top) * GRAPH_H - 13 }}>
        {period.toFixed(1)} ms = {target} fps
      </span>
    </div>
  )
}

function PerfAxis() {
  return (
    <div className="-mt-1.5 flex justify-between font-mono text-[10px] text-dim">
      <span>−{PERF_WINDOW_MS / 1000} s</span>
      <span>now</span>
    </div>
  )
}

function FpsBubble({ engine }: { engine: EngineConnection }) {
  const [frames, setFrames] = useState<PerfFrame[]>([])
  const [target, setTarget] = useState(40)
  const { subscribePerf } = engine
  useEffect(
    () =>
      subscribePerf((batch) => {
        setTarget(batch.fps)
        setFrames((f) => addPerf(f, batch))
      }),
    [subscribePerf],
  )
  const p = perfSummary(frames, target)
  return (
    <Bubble title="Engine frame rate" right={`target ${target} fps`} click="Settings → Engine" width={322}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[18px] text-ink tabular-nums">
          {p.fps.toFixed(1)} <span className="text-dim">/ {target} fps</span>
        </span>
        <span className={`lbl text-[11px] ${p.drops ? 'text-ink' : 'text-dim'}`}>
          {p.drops} drop{p.drops === 1 ? '' : 's'} in {Math.min(10, Math.round(p.seconds))} s
        </span>
      </div>
      <PerfGraph frames={frames} target={target} />
      <PerfAxis />
      <div className="grid grid-cols-2 gap-x-3 font-mono text-[11px] text-dim">
        <span>longest frame {p.worst.toFixed(1)} ms</span>
        <span className="text-right">
          engine {p.tick.toFixed(1)} ms · {Math.round(p.load * 100)} %
        </span>
      </div>
      <p className="text-[11px] leading-snug text-dim">Bars: the time between frames, the bright part what the engine computed. A drop: a frame over 1.5 × the target time.</p>
    </Bubble>
  )
}

// ---------------------------------------------------------------- the other bubbles

function AudioBubble({ engine }: { engine: EngineConnection }) {
  const s = engine.state
  const a = s?.io.audio
  return (
    <Bubble title="Audio input" right={a ? (a.running ? 'running' : a.error ? 'error' : 'stopped') : 'off'} click="Connections → Audio">
      <IoRow icon="in" ok={a ? Boolean(a.running) : null} active={Boolean(a?.running)} name={a?.device ?? (a ? 'system default' : 'no audio input')} detail={a?.channels?.length ? `ch ${a.channels.join(' + ')}` : undefined} error={a?.error ?? a?.warning} />
      <div className="flex items-center gap-2">
        <span className="lbl w-10 text-[10px] text-dim">level</span>
        <div className="h-1.5 flex-1 bg-panel-2">
          <div className="dot-on h-1.5" style={{ width: `${Math.min(1, a?.level ?? 0) * 100}%` }} />
        </div>
      </div>
      <LiveBandMeter engine={engine} height={64} />
      <div className="lbl flex justify-between text-[10px] text-dim">
        <span>low</span>
        <span>{s?.bands.length ?? 0} bands</span>
        <span>high</span>
      </div>
    </Bubble>
  )
}

function MidiBubble({ engine, live }: { engine: EngineConnection; live: IoLive }) {
  const io = engine.state?.io
  const m = io?.midi
  const devices = m?.devices ?? []
  const recent = (m?.recent ?? []).slice(0, 3)
  return (
    <Bubble title="MIDI" right={m?.received != null ? `${m.received} received` : undefined} click="Connections → MIDI">
      {devices.length === 0 && <IoRow icon="in" ok={null} name="no MIDI device" detail="plug one in" />}
      {devices.map((d) => {
        const st = deviceState(d)
        return (
          <IoRow key={d.key} icon="in" ok={d.state === 'connected' ? true : d.state === 'error' ? false : null} active={live.active[`device:${d.key}`]} name={d.name} detail={d.state === 'error' ? undefined : st.text} error={d.state === 'error' ? d.error : null} />
        )
      })}
      <IoRow icon="out" ok={null} name="MIDI out" detail="the app sends none" />
      <div className="flex flex-col border-t border-seam pt-1.5">
        <span className="lbl pb-1 text-[10px] text-dim">last messages</span>
        {recent.length === 0 && <span className="text-[12px] text-dim">none yet</span>}
        {recent.map((e) => {
          const r = midiRow(e)
          return (
            <div key={e.seq} className="grid grid-cols-[4.5rem_2.5rem_2rem_2rem_minmax(0,1fr)] gap-1.5 font-mono text-[12px] tabular-nums">
              <span className="text-ink">{r.type}</span>
              <span className="text-dim">{r.channel}</span>
              <span className="text-right">{r.number}</span>
              <span className="text-right">{r.value}</span>
              <span className="truncate font-sans text-[11px] text-dim">{r.macro}</span>
            </div>
          )
        })}
      </div>
    </Bubble>
  )
}

function DmxBubble({ engine, live: { rates } }: { engine: EngineConnection; live: IoLive }) {
  const outputs = useOutputSettings()
  const io = engine.state?.io
  const live = io?.live_input?.dmx
  const v2 = io?.outputs.pitchpls_v2
  const enttec = io?.outputs.enttec ?? []
  const configured = outputs?.enttec ?? []
  return (
    <Bubble title="DMX over USB" right={`${configured.filter((e) => e.enabled).length} out · ${live?.enabled ? 1 : 0} in`} click="Connections → DMX & Art-Net">
      {configured.length === 0 && <span className="text-[12px] text-dim">No USB DMX interface set up</span>}
      {configured.map((e, i) => {
        const st: IoStatus | null = enttec[i] ?? null
        return (
          <IoRow
            key={i}
            icon="out"
            ok={e.enabled ? Boolean(st?.connected) : null}
            active={Boolean(st?.connected)}
            name={`${i + 1} · ${deviceLabel(e.device)}`}
            detail={e.enabled ? `U${e.universe}${st?.connected ? ` · ${fmtRate(rates[`enttec${i}`])}` : ''}` : 'off'}
            error={st?.error}
          />
        )
      })}
      {live?.enabled && <IoRow icon="in" ok={Boolean(live.connected)} active={Boolean(live.connected && (live.age ?? 99) < 2)} name={`input · ${live.port ?? 'no device'}`} detail={fmtRate(live.pps, 'pps')} error={live.error} />}
      {outputs?.pitchpls_v2.enabled && (
        <IoRow icon="out" ok={Boolean(v2?.connected)} active={Boolean(v2?.connected)} name={`PitchPlease v2 · ${deviceLabel(outputs.pitchpls_v2.device)}`} detail={fmtRate(rates.v2)} error={v2?.error} />
      )}
    </Bubble>
  )
}

function ArtnetBubble({ engine, live: { rates } }: { engine: EngineConnection; live: IoLive }) {
  const outputs = useOutputSettings()
  const io = engine.state?.io
  const out = io?.outputs.artnet
  const input = io?.live_input?.artnet
  const targets = outputs?.artnet.enabled ? outputs.artnet.targets : []
  const rate = fmtRate(rates.artnet)
  const universes = input?.universes ?? []
  return (
    <Bubble title="Art-Net" right={`${targets.length} out · ${universes.length} in`} click="Connections → DMX & Art-Net">
      {outputs && !outputs.artnet.enabled && <IoRow icon="out" ok={null} name="output off" />}
      {targets.map((t, i) => (
        <IoRow key={i} icon="out" ok={Boolean(out?.connected)} active={Boolean(out?.connected)} name={`${t.ip} · U${t.universe}${t.artnet_universe != null && t.artnet_universe !== t.universe ? ` → Art-Net ${t.artnet_universe}` : ''}`} detail={rate} error={i === 0 ? out?.error : null} />
      ))}
      {!input?.enabled && <IoRow icon="in" ok={null} name="input off" />}
      {input?.enabled && universes.length === 0 && <IoRow icon="in" ok={Boolean(input.listening)} name={input.listening ? `listening on port ${input.port} · nothing yet` : 'not listening'} error={input.error} />}
      {universes.map((u) => (
        <IoRow key={u.key} icon="in" ok={u.age < 2} active={u.age < 2} name={`${u.sender} · Art-Net ${u.universe}`} detail={u.age < 2 ? fmtRate(u.pps, 'pps') : 'quiet'} />
      ))}
    </Bubble>
  )
}

// ---------------------------------------------------------------- the header's row

/** The indicators of the header's top row: FPS, audio, MIDI, DMX, Art-Net. The v2 serial output has no light of its own
 * any more: it is a row of the DMX bubble. */
export function HeaderIndicators({ engine, openTab, openEngine, overrides }: { engine: EngineConnection; openTab: (tab: ConnectionTab) => void; openEngine: () => void; overrides: ReactNode }) {
  const s = engine.state
  const artnet = artnetDot(s?.io) // the dots of DMX and Art-Net are lit by the outputs and the inputs (item 86)
  // kept for the header's life, so a bubble shows the rates and lights at once, not a second after it opened
  const [tracker] = useState(() => new IoTracker())
  const live = useMemo(() => tracker.update(s?.io, s?.received_at ?? 0), [tracker, s])
  return (
    <div className="flex flex-none items-center gap-4 px-2.5 whitespace-nowrap">
      <Indicator label="Engine frame rate" bubble={() => <FpsBubble engine={engine} />}>
        {/* fixed width: a changing FPS value never shifts the indicators */}
        <button
          onClick={openEngine}
          data-hint="button"
          data-tip={engine.connected ? 'Frames per second the engine computes and sends. Click: Settings → Engine, the target frame rate' : 'The browser has no connection to the engine: is the app still running?'}
          className={`inline-block w-[7.5rem] text-right font-mono text-[13px] tabular-nums hover:text-glow ${engine.connected ? 'text-ink' : 'text-dim'}`}
        >
          {engine.connected ? `${(s?.fps ?? 0).toFixed(1).padStart(4, ' ')} FPS` : 'ENGINE OFFLINE'}
        </button>
      </Indicator>
      {overrides}
      <Indicator label="Audio input" bubble={() => <AudioBubble engine={engine} />}>
        <StatusDot ok={s?.io.audio ? s.io.audio.running : null} label="audio" error={s?.io.audio?.error} tip="Audio input: filled = running, hollow = off, crossed = error. Click: Connections → Audio" onClick={() => openTab('audio')} />
      </Indicator>
      <Indicator label="MIDI" bubble={() => <MidiBubble engine={engine} live={live} />}>
        <StatusDot ok={midiDot(s?.io.midi).ok} label="midi" error={midiDot(s?.io.midi).error} tip="MIDI devices: filled = at least one device that is switched on is connected, hollow = none. Click: Connections → MIDI" onClick={() => openTab('midi')} />
      </Indicator>
      <Indicator label="DMX over USB" bubble={() => <DmxBubble engine={engine} live={live} />}>
        {/* one dot per USB DMX output interface, the first also for the DMX input; one dot for the input alone */}
        {dmxDots(s?.io).map((d, i) => (
          <StatusDot key={i} ok={d.ok} label={d.label} error={d.error} tip={d.tip} onClick={() => openTab('dmx')} />
        ))}
      </Indicator>
      <Indicator label="Art-Net" bubble={() => <ArtnetBubble engine={engine} live={live} />}>
        <StatusDot ok={artnet.ok} label={artnet.label} error={artnet.error} tip={artnet.tip} onClick={() => openTab('dmx')} />
      </Indicator>
    </div>
  )
}
