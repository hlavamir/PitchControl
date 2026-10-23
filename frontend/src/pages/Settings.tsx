import { useEffect, useRef, useState } from 'react'
import { api, type Settings as SettingsData } from '../api'
import { Button, Row, Section } from '../components/forms'
import { LogSection } from '../components/LogSection'
import { NetworkSection } from '../components/NetworkSection'
import { DESIGN_SIZE, INKS, clampScale, fitScale, type InkName, type UiSettings } from '../theme'
import type { EngineConnection } from '../useEngine'
import { useFieldNav } from '../useFieldNav'

const INK_NAMES: [InkName, string][] = [
  ['grey', 'Grey'],
  ['amber', 'Amber'],
  ['phosphor', 'Phosphor'],
]

/**
 * Settings: appearance (ink colour, UI scale, key hints, start in full screen), the engine, the network and the log of this
 * run (the keyboard reference, About and Support are on the Help page).
 * Changes apply immediately and are saved to settings.json, so they are restored next session.
 */
export function Settings({ ui, onChange, desktop, local, engine }: { ui: UiSettings; onChange: (ui: UiSettings) => void; desktop?: boolean; local: boolean; engine: EngineConnection }) {
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
    <div ref={pageRef} className="grid h-full gap-1.5 wide:grid-cols-2 wide:grid-rows-[minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-1.5">
      <Section
        index="01"
        title="Appearance"
        right="saved · restored next session"
        bodyClassName="p-3.5 gap-[18px]"
        tip="How the UI looks: ink colour and size. Changes apply at once and are remembered"
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
        {desktop && (
          <div className="flex items-center justify-between border-t border-seam pt-3.5">
            <span className="flex flex-col gap-1">
              <span className="lbl text-[12px]">Start in full screen</span>
              <span className="lbl text-[10px] text-dim">F toggles full screen any time · covers the notch strip; on a Mac the menu bar and Dock slide in at the screen's edge</span>
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
        )}
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
      {local && <LogSection index="04" engine={engine} />}

      </div>

    </div>
  )
}
