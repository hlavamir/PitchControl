import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'
import { api, type Settings as SettingsData } from '../api'
import { Button, Row, Section } from '../components/forms'
import { NetworkSection } from '../components/NetworkSection'
import { clientOf, issueUrl } from '../reportProblem'
import { DESIGN_SIZE, INKS, clampScale, fitScale, type InkName, type UiSettings } from '../theme'
import { useFieldNav } from '../useFieldNav'

const INK_NAMES: [InkName, string][] = [
  ['grey', 'Grey'],
  ['amber', 'Amber'],
  ['phosphor', 'Phosphor'],
]

const KEYMAP: [string, string][] = [
  ['W  S', 'Up / down a row, or to the control above / below'],
  ['A  D', 'Left / right, or along a row'],
  ['↑  ↓', 'Change the selected value; in an edited field: the number'],
  ['SHIFT', 'Fine steps; on the Rig page: extends the selection'],
  ['⏎', 'Press the button, load the scene; edit the control (⏎ / Esc stops)'],
  ['SHIFT ⏎', 'Save the selected scene'],
  ['SPACE', 'Rig page: add / remove the current fixture'],
  ['D  →', 'Fixtures and Rig: from the list into the details'],
  ['ESC', 'Cancel a pending change, stop editing, back to the list'],
  ['1 – 9', 'Switch page'],
  ['Q  E', 'Previous / next subpage (Control Desk)'],
  ['F', 'Full screen on / off (desktop app)'],
  ['⌘ / CTRL  + −', 'UI scale up / down (= works as +); 0 = 100 %'],
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
 * Settings: appearance (ink colour, glow, brightness, key hints) and the keyboard reference.
 * Changes apply immediately and are saved to settings.json, so they are restored next session.
 */
export function Settings({ ui, onChange, desktop, version }: { ui: UiSettings; onChange: (ui: UiSettings) => void; desktop?: boolean; version?: string }) {
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
  const [folders, setFolders] = useState<{ data_dir?: string; machine_dir?: string; local?: boolean; system?: string }>({})
  useEffect(() => {
    api.get<{ data_dir?: string; machine_dir?: string; local?: boolean; system?: string }>('/api/app-info').then(setFolders).catch(() => undefined)
  }, [])

  const [fps, setFpsState] = useState<number | null>(null)
  useEffect(() => {
    api.get<SettingsData>('/api/settings').then((s) => setFpsState(s.fps))
  }, [])
  const setFps = async (value: number) => {
    setFpsState(value)
    const current = await api.get<SettingsData>('/api/settings')
    await api.put('/api/settings', { ...current, fps: value })
  }

  // links of the project: the desktop app opens them in the default browser through the backend
  const openLink = (e: MouseEvent, url: string) => {
    if (!desktop || folders.local === false) return // a browser follows the link itself (a phone opens it on the phone)
    e.preventDefault()
    api.post('/api/open-url', { url }).catch(() => window.open(url, '_blank'))
  }

  // Report a problem: a new GitHub issue with the version and this computer's system filled in (reportProblem.ts)
  const reportUrl = issueUrl({ version: version ?? '', system: folders.system ?? '', client: clientOf({ desktop, local: folders.local }), userAgent: navigator.userAgent })

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
      <Section
        index="03"
        title="Support"
        right="free and open source"
        tip="PitchControl is free (MIT licence). If it helps your shows, you can support its development with a donation"
      >
        <p className="text-[12px] leading-snug text-dim">
          PitchControl is free and open source. If it is useful to you, you can support the work on it and on the PitchPlease lights with a
          donation.
        </p>
        <div className="mt-3">
          <a
            href="https://ko-fi.com/zeys_hlvmr"
            target="_blank"
            rel="noreferrer"
            onClick={(e) => openLink(e, 'https://ko-fi.com/zeys_hlvmr')}
            data-hint="button"
            data-tip="Open the Ko-fi page of the project in the browser: one-off or monthly donations"
            className="lbl glow-hover inline-flex h-8 items-center border border-edge bg-panel px-3 text-[11px] font-medium text-ink"
          >
            Donate on Ko-fi ›
          </a>
        </div>
      </Section>
      </div>

      <div className="flex min-w-0 flex-col gap-1.5">
      <NetworkSection index="04" desktop={desktop} />
      <Section index="05" title="Keyboard" right="no mouse needed" bodyClassName="px-3.5 pb-2.5 pt-1.5" tip="All keys of the UI. Every page can be used with the keys alone: General, Dimmers and Control Desk like a hardware device, the others control by control">
        {KEYMAP.map(([cap, what]) => (
          <div key={cap} className="flex min-h-[25px] items-center gap-3.5 border-b border-[#1d1f21] py-0.5">
            <span className="min-w-16 border border-ink px-1.5 text-center font-mono text-[12px]">{cap}</span>
            <span className="lbl text-[12px]">{what}</span>
          </div>
        ))}
      </Section>
      {desktop && (
        <Section index="06" title="App" right="desktop app" tip="Desktop app only: the app is a window around the same UI that a browser can show">
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
          <span className="lbl mt-3 text-[10px] text-dim">The browser view can also be used on a second screen, or on a phone or iPad (Network, above)</span>
        </Section>
      )}
      <Section index={desktop ? '07' : '06'} title="About" right="version" tip="Which PitchControl this is, where its source and releases are, and where to report a problem">
        <div className="flex items-baseline justify-between gap-3">
          <span className="lbl text-[12px]">PitchControl</span>
          <span className="text-glow font-mono text-[16px]" data-hint="info" data-tip="Version; +N = commits after that release, (abc1234) = the commit, modified = unsaved changes in the source">
            {version || '…'}
          </span>
        </div>
        {folders.data_dir && (
          <div className="mt-3 flex flex-col gap-1 border-t border-seam pt-3 text-[11px]">
            <span className="flex gap-2" data-hint="info" data-tip="Your rigs, fixture types, scenes and settings: what you made or changed (the app's own defaults are never changed)">
              <span className="lbl w-20 flex-none text-[10px] text-dim">Data</span>
              <span className="truncate font-mono">{folders.data_dir}</span>
            </span>
            <span className="flex gap-2" data-hint="info" data-tip="This computer's settings (audio input, MIDI port, outputs, appearance), the macro autosave and the logs">
              <span className="lbl w-20 flex-none text-[10px] text-dim">Computer</span>
              <span className="truncate font-mono">{folders.machine_dir}</span>
            </span>
          </div>
        )}
        <div className="mt-3 flex items-center gap-3 border-t border-seam pt-3">
          <a
            href={reportUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => openLink(e, reportUrl)}
            data-hint="button"
            data-tip="Open a new issue on GitHub in the browser, with the version and the system filled in: you see and edit everything before you send it. Attach the newest log file (Open logs folder)"
            className="lbl glow-hover inline-flex h-8 flex-none items-center border border-edge bg-panel px-3 text-[11px] font-medium text-ink"
          >
            Report a problem ›
          </a>
          <span className="lbl text-[10px] leading-snug text-dim">A GitHub issue, filled in with the version and the system; attach the newest log</span>
        </div>
        <span className="lbl mt-3 flex gap-4 text-[10px] text-dim">
          <a className="hover:text-ink" href="https://github.com/hlavamir/PitchControl" target="_blank" rel="noreferrer" onClick={(e) => openLink(e, 'https://github.com/hlavamir/PitchControl')} data-hint="button" data-tip="Open the project page on GitHub in the browser">
            Project on GitHub ›
          </a>
          <a className="hover:text-ink" href="https://github.com/hlavamir/PitchControl/releases" target="_blank" rel="noreferrer" onClick={(e) => openLink(e, 'https://github.com/hlavamir/PitchControl/releases')} data-hint="button" data-tip="Open the list of releases (downloads for macOS and Windows) on GitHub">
            Releases ›
          </a>
        </span>
      </Section>

      </div>
    </div>
  )
}
