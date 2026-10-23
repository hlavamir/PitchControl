import { useEffect, useState } from 'react'
import { api, type MacroDef, type Settings as SettingsData } from '../api'
import { Glyph } from '../App'
import { DEFAULT_UI, applyTheme } from '../theme'
import { useEngine } from '../useEngine'
import { PhoneDimmers } from './PhoneDimmers'
import { PhoneGeneral } from './PhoneGeneral'
import { FullUiContext } from '../phone'
import { LaptopNote, PhoneSection } from './parts'

const PHONE_PAGES = ['General', 'Dimmers'] as const
type PhonePage = (typeof PHONE_PAGES)[number]
// the laptop's other pages: a link to one of them (a bookmark, the hash) shows a note on the phone
const LAPTOP_PAGES = ['Fixtures', 'Rig', 'Inputs', 'Outputs', 'Fog', 'Settings', 'Control Desk']

function pageFromHash(): string {
  const hash = decodeURIComponent(location.hash.slice(1))
  return hash === 'Output' ? 'Outputs' : hash || 'General'
}

/**
 * The phone layout: General (without the scene preview and the audio meters) and Dimmers, a tab bar at the
 * bottom in thumb reach. The rest of the UI stays on the laptop; ``onFullUi`` switches this device to it.
 */
export function PhoneApp({ onFullUi }: { onFullUi: () => void }) {
  const engine = useEngine({ preview: false })
  const [page, setPage] = useState<string>(pageFromHash)
  const [defs, setDefs] = useState<Record<string, MacroDef>>({})

  useEffect(() => {
    api.get<MacroDef[]>('/api/macros/defs').then((list) => setDefs(Object.fromEntries(list.map((d) => [d.name, d]))))
    // the ink of Settings → Appearance; the UI scale is the laptop's and isn't used here
    api.get<SettingsData>('/api/settings').then((s) => applyTheme({ ...DEFAULT_UI, ...s.ui }))
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (p: PhonePage) => {
    setPage(p)
    history.replaceState(null, '', `#${p}`)
    document.querySelector('main')?.scrollTo(0, 0)
  }

  const tabs = (cls: string) =>
    PHONE_PAGES.map((p, i) => (
      <button
        key={p}
        onClick={() => go(p)}
        className={`lbl flex flex-1 items-center justify-center gap-2 text-[14px] [touch-action:manipulation] ${i > 0 ? 'border-l border-edge' : ''} ${page === p ? 'glow-on bg-ink text-ground' : 'text-ink'} ${cls}`}
      >
        <span className="font-mono text-[12px] opacity-60">{i + 1}</span>
        {p}
      </button>
    ))

  const s = engine.state
  const overrideCount = Object.values(s?.overrides ?? {}).reduce((n, chans) => n + Object.keys(chans).length, 0)
  const known = (PHONE_PAGES as readonly string[]).includes(page)

  return (
    <FullUiContext.Provider value={onFullUi}>
    <div className="flex h-full flex-col">
      <header className="flex h-11 flex-none items-center justify-between gap-3 border-b border-edge px-3">
        <div className="flex items-center gap-2.5">
          <Glyph />
          <h1 className="lbl text-glow text-[15px] font-semibold tracking-[0.14em]">PitchControl!</h1>
        </div>
        <nav className="hidden h-full max-w-[22rem] flex-1 border-x border-edge landscape:flex">{tabs('h-full')}</nav>
        <div className="flex items-center gap-3 whitespace-nowrap">
          {overrideCount > 0 && (
            // the manual DMX overrides are on the laptop's Control Desk; the phone only says that they are on
            <span className="lbl glow-on bg-ink px-2 text-[11px] leading-[20px] text-ground">
              {overrideCount} override{overrideCount === 1 ? '' : 's'}
            </span>
          )}
          <span className={`font-mono text-[14px] tabular-nums ${engine.connected ? 'text-ink' : 'text-dim'}`}>
            {engine.connected ? `${(s?.fps ?? 0).toFixed(0)} FPS` : 'OFFLINE'}
          </span>
        </div>
      </header>

      {!engine.connected && (
        <p className="lbl flex-none border-b border-ink px-3 py-2 text-[12px]">No connection to the laptop: reconnecting…</p>
      )}

      <main className={`min-h-0 flex-1 overflow-auto overscroll-contain px-1.5 py-1.5 ${page === 'General' ? 'landscape:overflow-hidden' : ''}`}>
        {page === 'General' && <PhoneGeneral engine={engine} defs={defs} />}
        {page === 'Dimmers' && <PhoneDimmers engine={engine} defs={defs} />}
        {!known && (
          <PhoneSection index="—" title={LAPTOP_PAGES.includes(page) ? page : 'Not on the phone'}>
            <p className="px-3 py-3 text-[14px] leading-snug">
              {LAPTOP_PAGES.includes(page) ? `${page} is on the laptop.` : 'This page is not part of the phone layout.'} The phone has General and Dimmers.
            </p>
          </PhoneSection>
        )}
        {!known && <LaptopNote className="mt-1.5" />}
      </main>

      {/* portrait: the tabs at the bottom, in thumb reach; landscape: in the top bar, to keep the height for the controls */}
      <nav className="flex flex-none border-t border-edge pb-[env(safe-area-inset-bottom)] landscape:hidden">{tabs('h-14')}</nav>
    </div>
    </FullUiContext.Provider>
  )
}
