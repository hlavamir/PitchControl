import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { api, type Settings as SettingsData } from '../api'
import { Button, Row, Section } from '../components/forms'
import { NetworkSection } from '../components/NetworkSection'
import { DESIGN_SIZE, INKS, clampScale, fitScale, type InkName, type UiSettings } from '../theme'
import { useFieldNav } from '../useFieldNav'

const INK_NAMES: [InkName, string][] = [
  ['grey', 'Grey'],
  ['amber', 'Amber'],
  ['phosphor', 'Phosphor'],
]

/**
 * Horizontal segmented slider: click or drag anywhere. With the focus (⏎ on it when the keys have highlighted it,
 * or Tab) ← ↓ / → ↑ change it by ``step`` (Shift = ``fine``).
 */
function HSlider({ value, min, max, onChange, step, fine, label, tip }: { value: number; min: number; max: number; onChange: (v: number) => void; step: number; fine: number; label: string; tip?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const t = (value - min) / (max - min)
  const set = (e: PointerEvent<HTMLDivElement>) => {
    const r = ref.current!.getBoundingClientRect()
    onChange(min + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (max - min))
  }
  const cells = 24
  const level = t * cells
  return (
    <div
      ref={ref}
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Number(value.toFixed(2))}
      data-hint="slider"
      data-tip={tip}
      className="flex h-[22px] cursor-ew-resize touch-none"
      onKeyDown={(e) => {
        const dir = e.key === 'ArrowUp' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowDown' || e.key === 'ArrowLeft' ? -1 : 0
        if (!dir) return
        e.preventDefault()
        onChange(Math.min(max, Math.max(min, value + dir * (e.shiftKey ? fine : step))))
      }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        set(e)
      }}
      onPointerMove={(e) => e.buttons && set(e)}
    >
      {Array.from({ length: cells }, (_, i) => {
        const fill = Math.max(0, Math.min(1, level - i))
        const top = i === Math.ceil(level) - 1
        return (
          <div
            key={i}
            className="relative flex-1"
            style={{
              background: `rgb(var(--ink-rgb) / ${(0.06 + 0.94 * fill).toFixed(3)})`,
              boxShadow:
                'inset -1px 0 0 rgba(15,16,17,.6)' + (top && fill > 0.5 ? ', 0 0 calc(10px * var(--glow)) rgb(var(--ink-rgb) / calc(0.4 * var(--glow)))' : ''),
              zIndex: top ? 1 : undefined,
            }}
          />
        )
      })}
    </div>
  )
}

/**
 * Settings: appearance (ink colour, glow, brightness, key hints), the engine, the network and the app (the keyboard
 * reference, About and Support are on the Help page).
 * Changes apply immediately and are saved to settings.json, so they are restored next session.
 */
export function Settings({ ui, onChange, desktop }: { ui: UiSettings; onChange: (ui: UiSettings) => void; desktop?: boolean }) {
  const saveTimer = useRef<number | undefined>(undefined)

  const change = (patch: Partial<UiSettings>) => {
    const next = { ...ui, ...patch }
    onChange(next)
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      const current = await api.get<SettingsData>('/api/settings')
      await api.put('/api/settings', { ...current, ui: next })
    }, 300)
  }
  useEffect(() => () => window.clearTimeout(saveTimer.current), [])

  // engine frame rate: stored in settings.json next to the UI settings, applied by the engine at once
  const [fps, setFpsState] = useState<number | null>(null)
  useEffect(() => {
    api.get<SettingsData>('/api/settings').then((s) => setFpsState(s.fps))
  }, [])
  const setFps = async (value: number) => {
    setFpsState(value)
    const current = await api.get<SettingsData>('/api/settings')
    await api.put('/api/settings', { ...current, fps: value })
  }

  const pct = (v: number) => `${Math.round(v * 100)}%`

  // window size in real px (not affected by the UI scale), for "Fit window"
  const [win, setWin] = useState({ width: window.innerWidth, height: window.innerHeight })
  useEffect(() => {
    const onResize = () => setWin({ width: window.innerWidth, height: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const setScale = (v: number) => change({ scale: clampScale(v) })

  // keys (rigKeys.ts, useFieldNav.ts): W S A D move over the controls, ⏎ presses, toggles or starts editing the highlighted one
  const pageRef = useRef<HTMLDivElement>(null)
  useFieldNav({ root: pageRef })

  return (
    <div ref={pageRef} className="grid gap-1.5 wide:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-1.5">
      <Section
        index="01"
        title="Appearance"
        right="saved · restored next session"
        bodyClassName="p-3.5 gap-[18px]"
        tip="How the UI looks: ink colour, glow, brightness and size. Changes apply at once and are remembered"
      >
        <div className="flex flex-col gap-2">
          <span className="lbl text-[11px] text-dim">Ink colour</span>
          <div className="grid grid-cols-3 gap-px border border-edge bg-edge">
            {INK_NAMES.map(([name, label]) => {
              const on = ui.ink === name
              return (
                <button
                  key={name}
                  data-hint="press"
                  data-tip={`${label} ink: colour of all text, lines and lit elements`}
                  onClick={() => change({ ink: name })}
                  className={`flex h-[92px] flex-col justify-between bg-panel p-3 text-left ${on ? 'glow-sel' : 'glow-hover'}`}
                  style={{ color: on ? INKS[name] : '#8a8c87' }}
                >
                  <span className="flex items-center justify-between">
                    <span className="lbl text-[12px]">{label}</span>
                    <span className="font-mono text-[11px] opacity-70">{INKS[name]}</span>
                  </span>
                  <span className="flex items-baseline gap-2.5" style={{ color: INKS[name] }}>
                    <span className="font-mono text-[26px]" style={{ textShadow: `0 0 8px ${INKS[name]}88` }}>
                      0.56
                    </span>
                    <span className="lbl text-[11px]">Strobo</span>
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {[
          { id: 'glow', label: 'Glow', tip: 'Bloom under selected and active elements', value: ui.glow, min: 0, max: 1, note: 'Bloom under selected and active elements', key: 'glow' as const },
          { id: 'brightness', label: 'UI brightness', tip: 'Dims the ink: less light on the DJ at the booth', value: ui.brightness, min: 0.4, max: 1, note: 'Dims the ink — less light on the DJ at the booth (40–100 %)', key: 'brightness' as const },
        ].map(({ id, label, tip, value, min, max, note, key }) => (
          <div key={id} className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <span className="lbl text-[12px]">{label}</span>
              <span className="text-glow font-mono text-[16px]">{pct(value)}</span>
            </div>
            <HSlider value={value} min={min} max={max} onChange={(v) => change({ [key]: v })} step={0.05} fine={0.01} label={label} tip={tip} />
            <span className="lbl text-[10px] text-dim">{note}</span>
          </div>
        ))}

        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className="lbl text-[12px]">UI scale</span>
            <span className="text-glow font-mono text-[16px]">{pct(ui.scale)}</span>
          </div>
          <div className="flex gap-1.5">
            <Button onClick={() => setScale(ui.scale - 0.05)} disabled={ui.scale <= 0.6} tip="Smaller UI by 5 % (minimum 60 %); ⌘ / Ctrl + − does the same">
              −
            </Button>
            <Button onClick={() => setScale(ui.scale + 0.05)} disabled={ui.scale >= 1.5} tip="Larger UI by 5 % (maximum 150 %); ⌘ / Ctrl + + or = does the same">
              +
            </Button>
            <Button onClick={() => setScale(fitScale())} tip="Scale so the whole layout fits this window without scrolling">
              Fit window
            </Button>
            <Button onClick={() => setScale(1)} disabled={ui.scale === 1} tip="Back to 100 %, the size the layout is designed for; ⌘ / Ctrl 0 does the same">
              100 %
            </Button>
          </div>
          <span className="lbl text-[10px] text-dim">
            Window {win.width} × {win.height} px · the layout is made for {DESIGN_SIZE.width} × {DESIGN_SIZE.height} at 100 % · fits at{' '}
            {pct(fitScale())} · 60–150 %
          </span>
        </div>

        <div className="flex items-center justify-between border-t border-seam pt-3.5">
          <span className="flex flex-col gap-1">
            <span className="lbl text-[12px]">Key hints</span>
            <span className="lbl text-[10px] text-dim">Show the keyboard legend at the bottom</span>
          </span>
          <button
            data-hint="toggle"
            data-tip="Show or hide this footer with the keys and tips for the control under the mouse"
            onClick={() => change({ key_hints: !ui.key_hints })}
            className={`lbl h-[34px] px-4 text-[12px] ${ui.key_hints ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge'}`}
          >
            {ui.key_hints ? 'On' : 'Off'}
          </button>
        </div>
      </Section>
      <Section
        index="02"
        title="Engine"
        right="applied at once"
        tip="How often the engine computes the show and sends it to the lights"
      >
        <Row
          label="Frame rate"
          hint="Frames per second sent to the lights. 40 is what the PitchPlease v3 firmware is built for; DMX512 itself allows about 44 with all 512 channels; slower interfaces or nodes may need less"
        >
          <select value={fps ?? 40} disabled={fps === null} onChange={(e) => setFps(Number(e.target.value))}>
            {[20, 25, 30, 40, 44].map((f) => (
              <option key={f} value={f}>
                {f} fps{f === 40 ? ' (default)' : f === 44 ? ' (DMX maximum)' : ''}
              </option>
            ))}
            {fps !== null && ![20, 25, 30, 40, 44].includes(fps) && <option value={fps}>{fps} fps (from the file)</option>}
          </select>
        </Row>
      </Section>
      </div>

      <div className="flex min-w-0 flex-col gap-1.5">
      <NetworkSection index="03" desktop={desktop} />
      {desktop && (
        <Section index="04" title="App" right="desktop app" tip="Desktop app only: the app is a window around the same UI that a browser can show">
          <div className="flex gap-1.5">
            <button className="lbl glow-hover h-8 border border-edge px-3 text-[11px]" data-tip="Open this UI in the default browser, e.g. for a second screen" onClick={() => api.post('/api/open-browser')}>
              Open in browser
            </button>
            <button className="lbl glow-hover h-8 border border-edge px-3 text-[11px]" data-tip="Show your data folder (your rigs, fixture types, scenes and settings) in Finder / Explorer" onClick={() => api.post('/api/open-data-folder')}>
              Open data folder
            </button>
            <button className="lbl glow-hover h-8 border border-edge px-3 text-[11px]" data-tip="Show the log files (one per start) in Finder / Explorer: attach the latest one to a bug report (About → Report a problem)" onClick={() => api.post('/api/open-logs-folder')}>
              Open logs folder
            </button>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-seam pt-3">
            <span className="flex flex-col gap-1">
              <span className="lbl text-[12px]">Start in full screen</span>
              <span className="lbl text-[10px] text-dim">F toggles full screen any time · covers the notch strip, hides menu bar and Dock</span>
            </span>
            <button
              data-hint="toggle"
              data-tip="Open the app in full screen next time; F toggles full screen at any time"
              onClick={() => change({ start_fullscreen: !ui.start_fullscreen })}
              className={`lbl h-[34px] px-4 text-[12px] ${ui.start_fullscreen ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge'}`}
            >
              {ui.start_fullscreen ? 'On' : 'Off'}
            </button>
          </div>
          <span className="lbl mt-3 text-[10px] text-dim">The browser view can also be used on a second screen, or on a phone or iPad (Network)</span>
        </Section>
      )}

      </div>
    </div>
  )
}
