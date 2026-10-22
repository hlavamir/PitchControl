import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type MacroDef, type Settings as SettingsData } from './api'
import { showLogPanel } from './logView'
import { menuTarget, showDrawnMenu, type MenuDef } from './appMenu'
import { AppMenu } from './components/AppMenu'
import { Button, StatusDot } from './components/forms'
import { LeaveGuardContext, type Guard } from './leaveGuard'
import { HINT_KEYS, MOD, hintAt, rigFieldKeys, type HintKind } from './hints'
import { Dimmers } from './pages/Dimmers'
import { Fixtures } from './pages/Fixtures'
import { Fog } from './pages/Fog'
import { General } from './pages/General'
import { Inputs } from './pages/Inputs'
import { Output } from './pages/Output'
import { Rig } from './pages/Rig'
import { ControlDesk } from './pages/ControlDesk'
import { Help } from './pages/Help'
import { Settings } from './pages/Settings'
import { requestImport } from './fixtureImport'
import { clientOf, issueUrl } from './reportProblem'
import { DEFAULT_UI, applyScale, applyTheme, clampScale, type UiSettings } from './theme'
import { useEngine } from './useEngine'
import { SelectionContext, isTyping, isTypingTarget, type FooterSelection } from './useGridNav'

// the keys 1 to 9, then 0 (Help)
const PAGES = ['General', 'Dimmers', 'Fixtures', 'Rig', 'Inputs', 'Outputs', 'Fog', 'Settings', 'Control Desk', 'Help'] as const
type Page = (typeof PAGES)[number]

/** The page of a number key (0 = Help, the tenth), and the key of a page. */
const pageOfKey = (n: number): Page => PAGES[(n + 9) % 10]
const keyOfPage = (p: Page) => (PAGES.indexOf(p) + 1) % 10

/** Footer tip of each page tab. */
const PAGE_TIPS: Record<Page, string> = {
  General: 'Macros, functions, masks, scenes, the scene preview and the audio meters: the live page',
  Dimmers: 'The sixteen dimmer faders: the brightness of the fixtures assigned to each',
  Fixtures: 'Fixture types: pixels, channel layout, gamma and defaults of each kind of light',
  Rig: 'The rig: which lights exist, where they are, their DMX address and per-fixture settings',
  Inputs: 'Audio input and MIDI controller: devices, gain and live meters',
  Outputs: 'DMX output: Enttec USB interfaces, Art-Net, and the PitchPlease v2 serial strips',
  Fog: 'Fog machines: DMX channel, timer and manual trigger',
  Settings: 'Look of the UI (ink, glow, brightness, scale), the engine frame rate, other devices on the network, the app window',
  'Control Desk': 'Every DMX channel as a fader: override channels by hand, e.g. to test a light',
  Help: 'Every key of the UI, the version, Report a problem, the Discord and the project links, support',
}

function initialPage(): Page {
  let hash = decodeURIComponent(location.hash.slice(1))
  if (hash === 'Output') hash = 'Outputs' // old bookmark
  return (PAGES as readonly string[]).includes(hash) ? (hash as Page) : 'General'
}

const KEYS: [string, string][] = [
  ['W S', 'row'],
  ['A D', 'column'],
  ['↑ ↓', 'value'],
  ['SHIFT', 'fine'],
  ['⏎', 'press'],
  ['ESC', 'cancel'],
  ['0–9', 'page'],
  ['F', 'full screen'],
  [`${MOD} + −`, 'UI scale'],
]

/** The general keys on the Rig and Fixtures pages: the list moves like a file list, the details field by field (rigKeys.ts). */
/** The general keys on the pages that are forms (Inputs, Outputs, Fog, Settings, Help): W S A D move over the controls, ⏎ edits. */
const FORM_KEYS: [string, string][] = [
  ['W S A D', 'control'],
  ['⏎', 'edit'],
  ['ESC', 'stop'],
  ['0–9', 'page'],
  ['F', 'full screen'],
  [`${MOD} + −`, 'UI scale'],
]

const LIST_PAGES: string[] = ['Fixtures', 'Rig']
const FORM_PAGES: string[] = ['Inputs', 'Outputs', 'Fog', 'Settings', 'Help']

const RIG_KEYS: [string, string][] = [
  ['W S ↑ ↓', 'fixture'],
  ['SHIFT', 'range'],
  ['SPACE', 'add / remove'],
  ['D →', 'details'],
  ['ESC A', 'list'],
  ['0–9', 'page'],
  ['F', 'full screen'],
  [`${MOD} + −`, 'UI scale'],
]

/** A field the Edit menu works on: text, not a slider, a select or a checkbox. */
function textField(el: Element | null): HTMLInputElement | HTMLTextAreaElement | null {
  if (el instanceof HTMLTextAreaElement) return el
  return el instanceof HTMLInputElement && ['text', 'search', 'number', 'url', 'email', 'password', 'tel'].includes(el.type) ? el : null
}

function hasSelection(field: HTMLInputElement | HTMLTextAreaElement): boolean {
  try {
    return field.selectionStart === null || field.selectionStart !== field.selectionEnd // null: a number field can't say
  } catch {
    return true
  }
}

/** The 3×3 pixel mark next to the wordmark. */
export function Glyph() {
  return (
    <span className="grid grid-cols-3 gap-px">
      {[1, 0, 1, 0, 1, 0, 1, 0, 1].map((on, i) => (
        <span key={i} className={`size-1 ${on ? 'bg-ink' : ''}`} />
      ))}
    </span>
  )
}

export default function App() {
  const engine = useEngine()
  const [page, setPage] = useState<Page>(initialPage)
  const [defs, setDefs] = useState<Record<string, MacroDef>>({})
  const [desktop, setDesktop] = useState(false)
  const [local, setLocal] = useState(false) // this computer's own window or browser: not a device on the network (Settings → Log is only here)
  const [version, setVersion] = useState('')
  const [fullscreen, setFullscreen] = useState<{ supported: boolean; on: boolean }>({ supported: false, on: false })
  const [ui, setUi] = useState<UiSettings>(DEFAULT_UI)
  const [footer, setFooter] = useState<FooterSelection | null>(null)
  // problems found while loading the configuration (broken files, missing items, the 1.4 migration)
  const [notices, setNotices] = useState<string[]>([])
  // footer context: the control under the mouse, or the keyboard selection, whichever was used last
  const [hover, setHover] = useState<{ kind: HintKind; tip?: string } | null>(null)
  const [inputMode, setInputMode] = useState<'mouse' | 'keys'>('mouse')
  // the menu bar the Windows app draws in the header (item 52; null: none, e.g. macOS, a browser, a phone)
  const [menus, setMenus] = useState<MenuDef[] | null>(null)
  const uiRef = useRef(ui)
  uiRef.current = ui

  useEffect(() => {
    api.get<MacroDef[]>('/api/macros/defs').then((list) => setDefs(Object.fromEntries(list.map((d) => [d.name, d]))))
    api
      .get<{ desktop: boolean; local: boolean; platform: string; fullscreen_supported: boolean; fullscreen: boolean; version: string }>('/api/app-info')
      .then((info) => {
        setDesktop(info.desktop)
        setLocal(showLogPanel(info))
        setVersion(info.version)
        setFullscreen({ supported: info.fullscreen_supported, on: info.fullscreen })
        if (showDrawnMenu(location.search, info)) api.get<{ menus: MenuDef[] }>('/api/menu').then((r) => setMenus(r.menus))
      })
      .catch(() => undefined)
    api.get<SettingsData>('/api/settings').then((s) => s.ui && setUi({ ...DEFAULT_UI, ...s.ui }))
    api.get<string[]>('/api/notices').then(setNotices).catch(() => undefined)
    const onHash = () => setPage(initialPage())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => applyTheme(ui), [ui])
  useEffect(() => {
    applyScale(ui.scale)
    const onResize = () => applyScale(ui.scale) // the column layouts depend on the scaled width
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [ui.scale])

  const pageRef = useRef(page)
  useEffect(() => {
    pageRef.current = page
  })
  const guards = useRef(new Set<Guard>())
  const [guardApi] = useState(() => ({
    register: (g: Guard) => {
      guards.current.add(g)
      return () => void guards.current.delete(g)
    },
  }))
  // the pages with unsaved edits are reported to the engine every second, so the desktop app can ask before it quits (it
  // can't ask the page itself while it closes). Every page load has its own id: the engine combines the reports of the
  // windows and tabs that are open, so one of them saying "nothing" doesn't hide the edits in another
  useEffect(() => {
    const client = Math.random().toString(36).slice(2) + Date.now().toString(36)
    const report = () => {
      const pages = [...guards.current].filter((g) => g.leave !== false && g.dirty()).map((g) => g.label)
      api.post('/api/ui/unsaved', { client, pages }).catch(() => undefined)
    }
    report()
    const timer = window.setInterval(report, 1000)
    return () => window.clearInterval(timer)
  }, [])
  // closing the browser tab or window with unsaved edits asks first (the desktop app asks through the report above)
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if ([...guards.current].some((g) => g.leave !== false && g.dirty())) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [])
  // a page change that waits for the answer to "unsaved changes: save, discard or stay?"
  const [leave, setLeave] = useState<{ to: Page; dirty: Guard[]; error?: string } | null>(null)

  const navigate = useCallback((p: Page) => {
    setLeave(null)
    setPage(p)
    history.replaceState(null, '', `#${p}`)
  }, [])
  const go = useCallback(
    (p: Page) => {
      if (p === pageRef.current) return
      const dirty = [...guards.current].filter((g) => g.leave !== false && g.dirty())
      if (dirty.length) setLeave({ to: p, dirty })
      else navigate(p)
    },
    [navigate],
  )
  const saveAndLeave = async () => {
    if (!leave) return
    for (const g of leave.dirty) {
      const ok = await g.save().catch(() => false)
      if (ok === false) return setLeave({ ...leave, error: `Could not save the ${g.label}: see the message on the page.` })
    }
    navigate(leave.to)
  }

  const toggleFullscreen = useCallback(async () => {
    const res = await api.post<{ fullscreen: boolean }>('/api/fullscreen').catch(() => null)
    if (res) setFullscreen((f) => ({ ...f, on: res.fullscreen }))
  }, [])

  // ---- the menu bar's actions (item 52): the Windows menu calls runMenu, the macOS menu bar window.pitchMenu (menu.py)
  // Save: what the page's Save button does, nothing on a page without one; a field being typed in is left first, so
  // its value is committed like when the Save button is clicked
  const saving = useRef(false)
  const save = useCallback(async () => {
    if (saving.current || ![...guards.current].some((g) => g.dirty())) return
    saving.current = true
    try {
      const field = document.activeElement as HTMLElement | null
      if (isTypingTarget(field)) {
        field?.blur()
        await new Promise((r) => window.setTimeout(r, 0))
      }
      for (const g of [...guards.current].filter((g) => g.dirty())) if ((await g.save().catch(() => false)) === false) break
    } finally {
      saving.current = false
    }
  }, [])
  // a page, scrolled to one of its sections (Help → Keyboard shortcuts, About)
  const scrollTo = useRef<string | null>(null)
  const showPage = useCallback(
    (p: Page, section?: string) => {
      scrollTo.current = section ?? null
      if (pageRef.current === p) document.getElementById(section ?? '')?.scrollIntoView({ block: 'nearest' })
      else go(p)
    },
    [go],
  )
  useEffect(() => {
    if (!scrollTo.current) return
    document.getElementById(scrollTo.current)?.scrollIntoView({ block: 'nearest' })
    scrollTo.current = null
  }, [page])
  const runMenu = useCallback(
    async (id: string) => {
      if (id.startsWith('view.page.')) go(pageOfKey(Number(id.slice('view.page.'.length))))
      else if (id === 'file.save') save()
      else if (id === 'file.import.ofl' || id === 'file.import.qlc') {
        // the Fixtures page has the dialog (it opens it when it is shown; this computer only, like the endpoints)
        requestImport(id === 'file.import.qlc' ? 'qlc' : 'ofl')
        showPage('Fixtures')
      }
      else if (id === 'view.fullscreen') toggleFullscreen()
      else if (menuTarget(id)) showPage(menuTarget(id)!.page as Page, menuTarget(id)!.section) // Settings, Help → Keyboard shortcuts, About, Show log
      else if (id === 'help.report') {
        const info = await api.get<{ version: string; system: string; desktop: boolean; local: boolean }>('/api/app-info')
        const url = issueUrl({ version: info.version, system: info.system, client: clientOf(info), userAgent: navigator.userAgent })
        api.post('/api/open-url', { url }).catch(() => window.open(url, '_blank'))
      } else if (id.startsWith('edit.')) {
        // Windows: the drawn menu's Edit acts on the focused text field (macOS: the native Edit menu)
        if (!textField(document.activeElement)) return
        if (id === 'edit.paste') document.execCommand('insertText', false, await navigator.clipboard.readText())
        else document.execCommand(id === 'edit.cut' ? 'cut' : id === 'edit.copy' ? 'copy' : 'selectAll')
      } else api.post(`/api/menu/${id}`).catch(() => undefined) // Python's: the folders, the links, the window, Quit
    },
    [go, save, toggleFullscreen, showPage],
  )
  useEffect(() => {
    ;(window as { pitchMenu?: (id: string) => void }).pitchMenu = runMenu
  }, [runMenu])
  // what the drawn menu offers, asked while it is open
  const menuEnabled = (id: string) => {
    const field = textField(document.activeElement)
    if (id === 'file.save') return [...guards.current].some((g) => g.dirty())
    if (id === 'edit.cut' || id === 'edit.copy') return Boolean(field) && hasSelection(field!)
    if (id === 'edit.paste' || id === 'edit.select_all') return Boolean(field)
    if (id === 'view.fullscreen') return fullscreen.supported
    return true
  }
  // Ctrl+S (⌘S on macOS): the menu's Save, also while typing in a field
  useEffect(() => {
    const mac = navigator.userAgent.includes('Mac')
    const onKey = (e: KeyboardEvent) => {
      if (!(mac ? e.metaKey : e.ctrlKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== 's') return
      e.preventDefault() // not the browser's "Save page as"
      save()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [save])

  // ⌘ (macOS) / Ctrl (Windows) with + or = (same key without Shift), − and 0: UI scale, like a
  // browser's zoom; saved like the Settings slider. Works while typing too (it needs the modifier).
  const saveTimer = useRef<number | undefined>(undefined)
  useEffect(() => {
    const mac = navigator.userAgent.includes('Mac')
    const onKey = (e: KeyboardEvent) => {
      if (!(mac ? e.metaKey : e.ctrlKey) || e.altKey) return
      let scale: number
      const cur = uiRef.current.scale
      if (e.key === '+' || e.key === '=' || e.code === 'NumpadAdd') scale = Math.round(cur * 20 + 1) / 20
      else if (e.key === '-' || e.key === '_' || e.code === 'NumpadSubtract') scale = Math.round(cur * 20 - 1) / 20
      else if (e.key === '0' || e.code === 'Numpad0') scale = 1
      else return
      e.preventDefault()
      const next = { ...uiRef.current, scale: clampScale(scale) }
      setUi(next)
      window.clearTimeout(saveTimer.current)
      saveTimer.current = window.setTimeout(async () => {
        const current = await api.get<SettingsData>('/api/settings')
        await api.put('/api/settings', { ...current, ui: next })
      }, 400)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // footer: follow the mouse until the navigation keys are used, then the keyboard selection
  useEffect(() => {
    const onOver = (e: PointerEvent) => setHover(hintAt(e.target))
    // Tab / click focus: the footer describes the focused control, like under the mouse
    const onFocus = (e: FocusEvent) => {
      setHover(hintAt(e.target))
      // a field got the focus (a click, Tab, or D on the Rig page): the footer describes it
      if (e.target instanceof HTMLElement && isTypingTarget(e.target)) setInputMode('mouse')
    }
    const onMove = () => setInputMode('mouse')
    const onLeave = () => setHover(null)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Tab') setInputMode('mouse') // focus moves: the footer follows the focused control
      // asked after the page's own key handling: Esc has left a field (a number field blurs, the Rig page goes back
      // to its list) and D on the Rig page has entered one, so the focus now says whether the keys are in use
      if (isTypingTarget(document.activeElement as HTMLElement | null) || e.metaKey || e.ctrlKey || e.altKey) return
      if (['w', 'a', 's', 'd', 'q', 'e'].includes(e.key.toLowerCase()) || ['ArrowUp', 'ArrowDown', 'Enter', 'Escape'].includes(e.key)) setInputMode('keys')
    }
    document.addEventListener('pointerover', onOver)
    document.addEventListener('pointermove', onMove)
    document.addEventListener('focusin', onFocus)
    document.documentElement.addEventListener('pointerleave', onLeave)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerover', onOver)
      document.removeEventListener('focusin', onFocus)
      document.removeEventListener('pointermove', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  // 1–9 and 0 switch pages, F full screen (not while typing in a field)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e) || e.metaKey || e.ctrlKey || e.altKey) return
      if (/^[0-9]$/.test(e.key)) {
        e.preventDefault()
        go(pageOfKey(Number(e.key)))
      }
      if (e.key.toLowerCase() === 'f' && fullscreen.supported) {
        e.preventDefault()
        toggleFullscreen()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, fullscreen.supported, toggleFullscreen])

  // The MIDI controller drives the faders of the active control page (General or Dimmers), like the
  // vvvv tabs: opening one of those pages selects it on the controller ...
  const { connected, setMacro } = engine
  useEffect(() => {
    if (connected && (page === 'General' || page === 'Dimmers')) setMacro(`Page ${page}`, 1)
  }, [page, connected, setMacro])

  // ... and turning the controller's page knob switches the UI between them.
  const enginePage = engine.state ? ((engine.state.macros['Page Dimmers'] ?? 0) > 0.5 ? 'Dimmers' : 'General') : null
  const lastEnginePage = useRef<string | null>(null)
  useEffect(() => {
    const last = lastEnginePage.current
    lastEnginePage.current = enginePage
    if (enginePage && last && enginePage !== last && (page === 'General' || page === 'Dimmers') && enginePage !== page) {
      go(enginePage)
    }
  }, [enginePage, page, go])

  const s = engine.state
  const out = s?.io.outputs
  // footer keys: for the hovered / keyboard-selected control, or the general ones
  const context = inputMode === 'keys' ? (footer?.hint ? { kind: footer.hint, tip: footer.tip } : null) : hover
  const footerKeys = context
    ? LIST_PAGES.includes(page) || FORM_PAGES.includes(page)
      ? rigFieldKeys(context.kind, HINT_KEYS[context.kind])
      : HINT_KEYS[context.kind]
    : [...(LIST_PAGES.includes(page) ? RIG_KEYS : FORM_PAGES.includes(page) ? FORM_KEYS : KEYS).filter(([cap]) => cap !== 'F' || fullscreen.supported), ...(page === 'Control Desk' ? ([['Q E', 'subpage']] as [string, string][]) : [])]
  const overrideCount = Object.values(s?.overrides ?? {}).reduce((n, chans) => n + Object.keys(chans).length, 0)
  // In full screen on a MacBook the camera notch covers the top 32 pt; below 100 % UI scale the top
  // row grows so that it still measures 38 pt on screen.
  const topRow = fullscreen.on && navigator.userAgent.includes('Mac') ? Math.max(38, Math.ceil(38 / clampScale(ui.scale))) : 38
  return (
    <LeaveGuardContext.Provider value={guardApi}>
    <SelectionContext.Provider value={setFooter}>
      <div className="flex h-full flex-col">
        {/* Two rows: the top one keeps its middle free, so in full screen on a MacBook the camera notch
            (32 px) sits in empty space between the logo and the indicators. */}
        {/* same 6 px side margin as the page content; the top row is 38 px (notch 32 px + 6) so
            the line below it clears the camera island */}
        <header className="flex-none px-1.5">
          <div className="flex items-center justify-between border-b border-edge" style={{ height: topRow }}>
            <div className="flex flex-none items-center gap-2.5 px-2.5">
              <Glyph />
              <h1 className="lbl text-glow text-[15px] font-semibold tracking-[0.14em]">PitchControl!</h1>
            </div>
            {menus && (
              <div className="ml-1 flex h-full min-w-0 flex-1 items-stretch">
                <AppMenu
                  menus={menus}
                  run={runMenu}
                  enabled={menuEnabled}
                  checked={(id) => id === `view.page.${keyOfPage(page)}` || (id === 'view.fullscreen' && fullscreen.on)}
                  label={(id, l) => (id === 'view.fullscreen' && fullscreen.on ? 'Exit full screen' : l)}
                />
              </div>
            )}
            <div className="flex flex-none items-center gap-4 px-2.5 whitespace-nowrap">
              {/* fixed width: a changing FPS value never shifts the indicators */}
              <span
                data-hint="info"
                data-tip={engine.connected ? 'Frames per second the engine computes and sends (target 40)' : 'The browser has no connection to the engine: is the app still running?'}
                className={`inline-block w-[7.5rem] text-right font-mono text-[13px] tabular-nums ${engine.connected ? 'text-ink' : 'text-dim'}`}
              >
                {engine.connected ? `${(s?.fps ?? 0).toFixed(1).padStart(4, '\u2007')} FPS` : 'ENGINE OFFLINE'}
              </span>
              {overrideCount > 0 && (
                // manual DMX overrides are saved across restarts: never let them go unnoticed
                <button onClick={() => go('Control Desk')} className="lbl glow-on bg-ink px-2 text-[11px] leading-[18px] text-ground" data-tip="Manual DMX overrides are active: these channels ignore the fixtures. Click to open the Control Desk">
                  {overrideCount} override{overrideCount === 1 ? '' : 's'}
                </button>
              )}
              <StatusDot ok={s?.io.audio ? s.io.audio.running : null} label="audio" error={s?.io.audio?.error} tip="Audio input: filled = running, hollow = off, crossed = error (see Inputs)" />
              <StatusDot ok={s?.io.midi ? Boolean(s.io.midi.port) : null} label="midi" error={s?.io.midi?.error} tip="MIDI controller: filled = connected, hollow = off (see Inputs)" />
              {/* one dot per configured USB DMX interface */}
              {out?.enttec?.length ? (
                out.enttec.map((e, i) => (
                  <StatusDot key={i} ok={e ? e.connected : null} label={out.enttec.length > 1 ? `dmx ${i + 1}` : 'dmx'} error={e?.error} tip={`USB DMX interface ${i + 1}: filled = connected, hollow = off, crossed = error (see Outputs)`} />
                ))
              ) : (
                <StatusDot ok={null} label="dmx" tip="No USB DMX interface configured (see Outputs)" />
              )}
              <StatusDot ok={out?.artnet ? out.artnet.connected : null} label="art-net" error={out?.artnet?.error} tip="Art-Net output: filled = sending, hollow = off (see Outputs)" />
              <StatusDot ok={out?.pitchpls_v2 ? out.pitchpls_v2.connected : null} label="v2" error={out?.pitchpls_v2?.error} tip="PitchPlease v2 serial output: filled = connected, hollow = off (see Outputs)" />
            </div>
          </div>
          <nav className="flex h-9 items-stretch border-x border-b border-edge">
            {PAGES.map((p, i) => (
              <button
                key={p}
                onClick={() => go(p)}
                data-hint="tab"
                data-tip={PAGE_TIPS[p]}
                className={`lbl flex flex-none items-center gap-2 border-r border-edge px-4 text-[12px] whitespace-nowrap ${
                  page === p ? 'glow-on bg-ink text-ground' : 'text-ink hover:bg-panel-2'
                }`}
              >
                <span className="font-mono text-[11px] opacity-60">{(i + 1) % 10}</span>
                {p}
              </button>
            ))}
            {fullscreen.supported && (
              <button
                onClick={toggleFullscreen}
                data-tip="Full screen hides the menu bar and the Dock, and covers the camera notch strip"
                className={`lbl ml-auto flex items-center gap-2 border-l border-edge px-4 text-[12px] ${fullscreen.on ? 'text-ink' : 'text-dim'} hover:bg-panel-2`}
              >
                <span className="font-mono text-[11px] opacity-60">F</span>
                {fullscreen.on ? 'Exit full screen' : 'Full screen'}
              </button>
            )}
          </nav>
        </header>

        {notices.length > 0 && (
          <div className="mx-1.5 mt-1.5 flex flex-none items-start gap-3 border border-ink px-3 py-2 text-[12px]" data-hint="info" data-tip="Found while loading your configuration; details are in the log (Settings → App → Open logs folder)">
            <ul className="flex min-w-0 flex-1 flex-col gap-1 leading-snug">
              {notices.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
            <button className="lbl glow-hover h-[18px] flex-none border border-edge px-2 text-[10px]" onClick={() => api.delete('/api/notices').then(() => setNotices([]))}>
              Dismiss
            </button>
          </div>
        )}

        {/* side margins instead of padding: the scrollbar ends 6 px from the window edge, like the header */}
        <main className="page-scroll mx-1.5 min-h-0 flex-1 overflow-auto py-1.5">
          {page === 'General' && <General engine={engine} defs={defs} />}
          {page === 'Dimmers' && <Dimmers engine={engine} defs={defs} />}
          {page === 'Fixtures' && <Fixtures defs={defs} />}
          {page === 'Rig' && <Rig engine={engine} defs={defs} />}
          {page === 'Outputs' && <Output engine={engine} />}
          {page === 'Inputs' && <Inputs engine={engine} />}
          {page === 'Fog' && <Fog engine={engine} />}
          {page === 'Settings' && <Settings ui={ui} onChange={setUi} desktop={desktop} local={local} engine={engine} />}
          {page === 'Control Desk' && <ControlDesk engine={engine} />}
          {page === 'Help' && <Help desktop={desktop} version={version} />}
        </main>

        {ui.key_hints && (
          <footer className="mx-1.5 flex h-7 flex-none items-center gap-5 border-t border-edge px-2.5 text-[11px]">
            {footerKeys.map(([cap, what]) => (
              <span key={cap} className="lbl inline-flex flex-none items-center gap-1.5">
                <span className="border border-ink px-1 font-mono text-[11px] leading-[14px]">{cap}</span>
                <span className="text-dim">{what}</span>
              </span>
            ))}
            {context?.tip && <span className="min-w-0 truncate text-[12px] text-dim" title={context.tip}>{context.tip}</span>}
            {footer && (
              <span className="lbl ml-auto flex-none whitespace-nowrap">
                Sel{' '}
                <span className="font-mono text-[13px]">
                  · {footer.label}
                  {footer.value !== undefined && ` ${footer.value}`}
                </span>
              </span>
            )}
          </footer>
        )}
        {leave && (
          <div className="fixed inset-x-0 top-14 z-50 flex justify-center px-3" role="alertdialog" aria-label="Unsaved changes">
            <div className="flex max-w-full flex-wrap items-center gap-2 border border-ink bg-panel p-3 shadow-[0_0_30px_rgb(0_0_0/0.6)]">
              <span className="text-[12px]">
                Unsaved changes in {leave.dirty.map((g) => g.label).join(' and ')} on {page}. Save them before leaving?
                {leave.error && <span className="ml-2 text-ink"> {leave.error}</span>}
              </span>
              <Button primary onClick={saveAndLeave} tip="Write the changes, then go to the other page">
                Save and leave
              </Button>
              <Button onClick={() => navigate(leave.to)} tip="Throw the changes away and go to the other page">
                Discard
              </Button>
              <Button onClick={() => setLeave(null)} tip="Stay on this page">
                Stay
              </Button>
            </div>
          </div>
        )}
      </div>
    </SelectionContext.Provider>
    </LeaveGuardContext.Provider>
  )
}
