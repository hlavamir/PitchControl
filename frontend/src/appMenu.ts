// The menu bar of the Windows app (item 52), drawn in the header next to the logo. The menus come from the backend
// (menu.py, GET /api/menu), the same definition as the native macOS menu bar; this file is the keyboard logic, kept
// free of React so it can be tested.

export interface MenuItemDef {
  id: string
  label: string
  kind: 'ui' | 'app' | 'native'
  key: string // shown next to the item: "Ctrl+S", "3"
}

export interface MenuDef {
  title: string
  items: (MenuItemDef | null)[] // null: a separator
}

/** Whether to draw the menu: in the Windows desktop app's own window only (``?window=app``, set by desktop.py), never
 * in a browser (here or on another device on the network) and never on macOS (the native menu bar). */
export function showDrawnMenu(search: string, info: { local?: boolean; platform?: string } | null): boolean {
  return new URLSearchParams(search).get('window') === 'app' && info?.local === true && info.platform === 'win32'
}

export interface MenuState {
  active: boolean // the menu bar has the keyboard (Alt, F10, Alt+letter) or a menu is open
  menu: number // the highlighted menu title
  open: boolean // its drop-down is open
  item: number | null // the highlighted item of the open menu
  keys: boolean // opened from the keyboard: the titles show their access letter
}

export const CLOSED: MenuState = { active: false, menu: 0, open: false, item: null, keys: false }

/** The access letter of a menu: its first letter (File, Edit, View, Window, Help: all different). */
export const accessKey = (title: string) => title[0].toLowerCase()

/** The next enabled item from ``from`` in ``direction`` (wrapping), or null when none is enabled. */
export function nextItem(menu: MenuDef, from: number | null, direction: 1 | -1, enabled: (id: string) => boolean): number | null {
  const n = menu.items.length
  let i = from ?? (direction === 1 ? -1 : n)
  for (let step = 0; step < n; step++) {
    i = (i + direction + n) % n
    const item = menu.items[i]
    if (item && enabled(item.id)) return i
  }
  return null
}

const openMenu = (menus: MenuDef[], index: number, enabled: (id: string) => boolean, keys: boolean, last = false): MenuState => ({
  active: true,
  menu: index,
  open: true,
  item: keys ? nextItem(menus[index], null, last ? -1 : 1, enabled) : null,
  keys,
})

/** The menu bar takes the keyboard: Alt or F10 (Windows: the first title highlighted, nothing open yet). */
export const activate = (): MenuState => ({ active: true, menu: 0, open: false, item: null, keys: true })

/** Alt+letter: open that menu with its first item highlighted; null when no menu has that letter. */
export function openByLetter(menus: MenuDef[], letter: string, enabled: (id: string) => boolean): MenuState | null {
  const index = menus.findIndex((m) => accessKey(m.title) === letter.toLowerCase())
  return index < 0 ? null : openMenu(menus, index, enabled, true)
}

/**
 * A key while the menu bar is active (Windows' convention): ← → move between the menus (an open one stays open), ↓ ↑ open
 * a menu and move through it, ⏎ (or Space) runs the highlighted item, Esc closes the drop-down and then the bar, a letter
 * opens its menu. Every key is the menu's while it is active (``handled``), so none reaches the page or a field.
 */
export function menuKey(state: MenuState, key: string, menus: MenuDef[], enabled: (id: string) => boolean): { state: MenuState; run?: string } {
  if (!state.active || !menus.length) return { state }
  const menu = menus[state.menu]
  const n = menus.length
  switch (key) {
    case 'Escape':
      return { state: state.open ? { ...state, open: false, item: null } : CLOSED }
    case 'ArrowLeft':
    case 'ArrowRight': {
      const index = (state.menu + (key === 'ArrowRight' ? 1 : -1) + n) % n
      return { state: state.open ? openMenu(menus, index, enabled, true) : { ...state, menu: index } }
    }
    case 'ArrowDown':
    case 'ArrowUp':
      if (!state.open) return { state: openMenu(menus, state.menu, enabled, true, key === 'ArrowUp') }
      return { state: { ...state, keys: true, item: nextItem(menu, state.item, key === 'ArrowDown' ? 1 : -1, enabled) ?? state.item } }
    case 'Enter':
    case ' ': {
      if (!state.open) return { state: openMenu(menus, state.menu, enabled, true) }
      const item = state.item === null ? null : menu.items[state.item]
      if (!item || !enabled(item.id)) return { state }
      return { state: CLOSED, run: item.id }
    }
    default:
      if (key.length === 1) {
        const opened = openByLetter(menus, key, enabled)
        if (opened) return { state: opened }
      }
      return { state }
  }
}

/**
 * Alt pressed and released on its own toggles the menu bar (Windows). Not AltGr (``AltGraph``, or Alt with Ctrl: typing
 * @ { [ on a German keyboard), not Alt held with another key or a click (Alt+Tab, Alt+Shift switching the layout).
 */
export class AltTap {
  private armed = false

  down(e: { key: string; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; repeat: boolean }): void {
    this.armed = e.key === 'Alt' && !e.ctrlKey && !e.metaKey && !e.shiftKey && (this.armed || !e.repeat)
  }

  /** true: that was a tap of Alt alone. */
  up(e: { key: string }): boolean {
    const tap = this.armed && e.key === 'Alt'
    this.armed = false
    return tap
  }

  cancel(): void {
    this.armed = false
  }
}
