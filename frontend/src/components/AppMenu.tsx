import { useEffect, useRef, useState } from 'react'
import { AltTap, CLOSED, accessKey, activate, isSub, menuKey, openByLetter, type MenuDef, type MenuItemDef, type MenuState } from '../appMenu'

/**
 * The Windows app's menu bar, in the header row next to the logo (item 52; macOS has the native menu bar). The items
 * never take the focus: a text field keeps its caret and selection, so Cut, Copy and Paste act on it. Keyboard: Alt
 * (or F10) gives the bar the keys, Alt+letter opens a menu, ← → ↓ ↑ move, ⏎ runs, Esc closes (appMenu.ts); an item with ▸
 * opens a submenu to its right (→ or ⏎).
 */
export function AppMenu({
  menus,
  run,
  enabled,
  checked,
  label,
}: {
  menus: MenuDef[]
  run: (id: string) => void
  enabled: (id: string) => boolean
  checked: (id: string) => boolean // a small mark: the current page, full screen on
  label: (id: string, label: string) => string // e.g. "Exit full screen"
}) {
  const [state, setState] = useState<MenuState>(CLOSED)
  const root = useRef<HTMLDivElement>(null)
  const latest = useRef({ state, menus, run, enabled })
  useEffect(() => {
    latest.current = { state, menus, run, enabled }
  })

  useEffect(() => {
    const alt = new AltTap()
    const choose = (s: MenuState, id?: string) => {
      setState(s)
      if (id) latest.current.run(id)
    }
    const onDown = (e: KeyboardEvent) => {
      alt.down(e)
      const { state: s, menus: ms, enabled: en } = latest.current
      const plain = !e.altKey && !e.ctrlKey && !e.shiftKey && !e.metaKey
      if (e.key === 'F10' && plain) {
        e.preventDefault()
        e.stopPropagation()
        return choose(s.active ? CLOSED : activate())
      }
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.length === 1) {
        const opened = openByLetter(ms, e.key, en) // Alt+F, Alt+E, Alt+V, Alt+W, Alt+H
        if (opened) {
          e.preventDefault()
          e.stopPropagation()
          return choose(opened)
        }
      }
      if (!s.active || e.key === 'Alt') return
      if (e.ctrlKey || e.metaKey) return choose(CLOSED) // Ctrl+C and the like: the bar lets go, the key does its job
      // every other key is the menu's while it is active: none reaches the page's navigation or a field
      e.preventDefault()
      e.stopPropagation()
      const r = menuKey(s, e.key, ms, en)
      choose(r.state, r.run)
    }
    const onUp = (e: KeyboardEvent) => {
      if (!alt.up(e)) return
      e.preventDefault()
      choose(latest.current.state.active ? CLOSED : activate())
    }
    const onPointer = (e: PointerEvent) => {
      alt.cancel()
      if (latest.current.state.active && !root.current?.contains(e.target as Node)) choose(CLOSED)
    }
    const onBlur = () => {
      alt.cancel()
      choose(CLOSED)
    }
    window.addEventListener('keydown', onDown, true)
    window.addEventListener('keyup', onUp, true)
    document.addEventListener('pointerdown', onPointer, true)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onDown, true)
      window.removeEventListener('keyup', onUp, true)
      document.removeEventListener('pointerdown', onPointer, true)
      window.removeEventListener('blur', onBlur)
    }
  }, [])

  /** One item of a drop-down or a flyout. */
  const row = (item: MenuItemDef, lit: boolean, enter: () => void, leave: () => void) => (
    <div
      key={item.id}
      role="menuitem"
      aria-disabled={!enabled(item.id)}
      onMouseDown={(e) => e.preventDefault()}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onClick={() => {
        if (!enabled(item.id)) return
        setState(CLOSED)
        run(item.id)
      }}
      className={`flex h-7 cursor-default items-center gap-2.5 pr-3 pl-2 text-[12px] ${!enabled(item.id) ? 'text-dim opacity-50' : lit ? 'glow-on bg-ink text-ground' : 'text-ink'}`}
    >
      <span className="flex w-2 flex-none justify-center">{checked(item.id) && <span className={`size-[6px] ${lit && enabled(item.id) ? 'bg-ground' : 'dot-on'}`} />}</span>
      <span className="lbl flex-1 whitespace-nowrap">{label(item.id, item.label)}</span>
      {item.key && <span className="ml-6 font-mono text-[11px] opacity-60">{item.key}</span>}
    </div>
  )

  const openAt = (index: number): MenuState => ({ ...CLOSED, active: true, menu: index, open: true })

  return (
    <div ref={root} role="menubar" className="flex h-full items-stretch" data-hint="info" data-tip="Menu bar: Alt or F10 gives it the keys, Alt + the underlined letter opens a menu">
      {menus.map((m, i) => {
        const lit = state.active && state.menu === i
        return (
          <div key={m.title} className="relative flex">
            <button
              type="button"
              tabIndex={-1}
              role="menuitem"
              aria-haspopup="menu"
              aria-expanded={lit && state.open}
              // mouse down, not click: the focus stays where it is (a text field keeps its selection)
              onMouseDown={(e) => {
                e.preventDefault()
                setState(lit && state.open ? CLOSED : openAt(i))
              }}
              onMouseEnter={() => state.open && !lit && setState(openAt(i))}
              className={`lbl flex items-center px-2.5 text-[12px] ${lit ? 'glow-on bg-ink text-ground' : 'text-ink hover:bg-panel-2'}`}
            >
              {state.keys && state.active ? (
                <>
                  <span className="underline underline-offset-[3px]">{m.title[0]}</span>
                  {m.title.slice(1)}
                </>
              ) : (
                m.title
              )}
              <span className="sr-only">{` (Alt+${accessKey(m.title).toUpperCase()})`}</span>
            </button>
            {lit && state.open && (
              <div role="menu" aria-label={m.title} className="absolute top-full left-0 z-50 min-w-[16rem] border border-ink bg-panel py-1 shadow-[0_0_30px_rgb(0_0_0/0.6)]">
                {m.items.map((item, j) =>
                  item === null ? (
                    <div key={`sep${j}`} role="separator" className="mx-2 my-1 border-t border-seam" />
                  ) : isSub(item) ? (
                    <div
                      key={item.submenu}
                      className="relative"
                      onMouseEnter={() => setState((s) => ({ ...s, item: j, subOpen: true, sub: null }))}
                    >
                      <div
                        role="menuitem"
                        aria-haspopup="menu"
                        aria-expanded={state.item === j && state.subOpen}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => setState((s) => ({ ...s, item: j, subOpen: !(s.item === j && s.subOpen), sub: null }))}
                        className={`flex h-7 cursor-default items-center gap-2.5 pr-3 pl-2 text-[12px] ${state.item === j ? 'glow-on bg-ink text-ground' : 'text-ink'}`}
                      >
                        <span className="w-2 flex-none" />
                        <span className="lbl flex-1 whitespace-nowrap">{item.submenu}</span>
                        <span className="ml-6 text-[10px]">▸</span>
                      </div>
                      {state.item === j && state.subOpen && (
                        <div role="menu" aria-label={item.submenu} className="absolute top-0 left-full z-50 min-w-[14rem] border border-ink bg-panel py-1 shadow-[0_0_30px_rgb(0_0_0/0.6)]">
                          {item.items.map((sub, k) =>
                            sub === null ? (
                              <div key={`sep${k}`} role="separator" className="mx-2 my-1 border-t border-seam" />
                            ) : (
                              row(sub, state.sub === k, () => setState((s) => ({ ...s, sub: k })), () => setState((s) => (s.sub === k ? { ...s, sub: null } : s)))
                            ),
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    row(
                      item,
                      state.item === j,
                      () => setState((s) => ({ ...s, item: j, subOpen: false, sub: null })),
                      () => setState((s) => (s.item === j ? { ...s, item: null } : s)),
                    )
                  ),
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
