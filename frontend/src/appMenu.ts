// The menu bar of the Windows app (item 52), drawn in the header next to the logo. The menus come from the backend
// (menu.py, GET /api/menu), the same definition as the native macOS menu bar; this file is the keyboard logic, kept
// free of React so it can be tested.

export interface MenuItemDef {
  id: string
  label: string
  kind: 'ui' | 'app' | 'native'
  key: string // shown next to the item: "Ctrl+S", "3"
}

/** An item that opens a menu of its own (File → Import Fixture ▸); one level deep. */
export interface SubmenuDef {
  submenu: string
  items: (MenuItemDef | null)[]
}

export type MenuEntry = MenuItemDef | SubmenuDef | null // null: a separator

export interface MenuDef {
  title: string
  items: MenuEntry[]
}

export const isSub = (entry: MenuEntry): entry is SubmenuDef => entry !== null && 'submenu' in entry

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
  subOpen: boolean // the highlighted item is a submenu and its flyout is open
  sub: number | null // the highlighted item of the flyout
  keys: boolean // opened from the keyboard: the titles show their access letter
}

export const CLOSED: MenuState = { active: false, menu: 0, open: false, item: null, subOpen: false, sub: null, keys: false }

/** The access letter of a menu: its first letter (File, Edit, View, Window, Help: all different). */
export const accessKey = (title: string) => title[0].toLowerCase()

/** The next enabled item from ``from`` in ``direction`` (wrapping), or null when none is enabled. A submenu counts as enabled. */
export function nextItem(menu: { items: MenuEntry[] }, from: number | null, direction: 1 | -1, enabled: (id: string) => boolean): number | null {
  const n = menu.items.length
  let i = from ?? (direction === 1 ? -1 : n)
  for (let step = 0; step < n; step++) {
    i = (i + direction + n) % n
    const item = menu.items[i]
    if (item && (isSub(item) || enabled(item.id))) return i
  }
  return null
}

const openMenu = (menus: MenuDef[], index: number, enabled: (id: string) => boolean, keys: boolean, last = false): MenuState => ({
  active: true,
  menu: index,
  open: true,
  item: keys ? nextItem(menus[index], null, last ? -1 : 1, enabled) : null,
  subOpen: false,
  sub: null,
  keys,
})

/** The menu bar takes the keyboard: Alt or F10 (Windows: the first title highlighted, nothing open yet). */
export const activate = (): MenuState => ({ ...CLOSED, active: true, keys: true })

/** Alt+letter: open that menu with its first item highlighted; null when no menu has that letter. */
export function openByLetter(menus: MenuDef[], letter: string, enabled: (id: string) => boolean): MenuState | null {
  const index = menus.findIndex((m) => accessKey(m.title) === letter.toLowerCase())
  return index < 0 ? null : openMenu(menus, index, enabled, true)
}

/**
 * A key while the menu bar is active (Windows' convention): ← → move between the menus (an open one stays open), ↓ ↑ open
 * a menu and move through it, ⏎ (or Space) runs the highlighted item, Esc closes the drop-down and then the bar, a letter
 * opens its menu. On a submenu, → (or ⏎) opens its flyout, which ↓ ↑ ⏎ work in, and ← or Esc close again. Every key is
 * the menu's while it is active (``handled``), so none reaches the page or a field.
 */
export function menuKey(state: MenuState, key: string, menus: MenuDef[], enabled: (id: string) => boolean): { state: MenuState; run?: string } {
  if (!state.active || !menus.length) return { state }
  const menu = menus[state.menu]
  const n = menus.length
  const current = state.open && state.item !== null ? menu.items[state.item] : null
  if (state.subOpen && current && isSub(current)) {
    switch (key) {
      case 'Escape':
      case 'ArrowLeft':
        return { state: { ...state, subOpen: false, sub: null } }
      case 'ArrowDown':
      case 'ArrowUp':
        return { state: { ...state, keys: true, sub: nextItem(current, state.sub, key === 'ArrowDown' ? 1 : -1, enabled) ?? state.sub } }
      case 'Enter':
      case ' ': {
        const item = state.sub === null ? null : current.items[state.sub]
        return item && enabled(item.id) ? { state: CLOSED, run: item.id } : { state }
      }
      default:
        return { state }
    }
  }
  const openSub = (sub: SubmenuDef): MenuState => ({ ...state, keys: true, subOpen: true, sub: nextItem(sub, null, 1, enabled) })
  switch (key) {
    case 'Escape':
      return { state: state.open ? { ...state, open: false, item: null } : CLOSED }
    case 'ArrowLeft':
    case 'ArrowRight': {
      if (key === 'ArrowRight' && current && isSub(current)) return { state: openSub(current) }
      const index = (state.menu + (key === 'ArrowRight' ? 1 : -1) + n) % n
      return { state: state.open ? openMenu(menus, index, enabled, true) : { ...state, menu: index } }
    }
    case 'ArrowDown':
    case 'ArrowUp':
      if (!state.open) return { state: openMenu(menus, state.menu, enabled, true, key === 'ArrowUp') }
      return { state: { ...state, keys: true, item: nextItem(menu, state.item, key === 'ArrowDown' ? 1 : -1, enabled) ?? state.item, subOpen: false, sub: null } }
    case 'Enter':
    case ' ': {
      if (!state.open) return { state: openMenu(menus, state.menu, enabled, true) }
      const item = state.item === null ? null : menu.items[state.item]
      if (item && isSub(item)) return { state: openSub(item) }
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

/** The id of the Settings panel that shows the log (Help → Show log scrolls to it). */
export const LOG_SECTION = 'settings-log'

/** The items that act on the page underneath (change the page, save it, open its dialog): nothing while a dialog is open. */
export const actsOnPage = (id: string) => id.startsWith('view.page.') || id === 'file.save' || id.startsWith('file.import.') || menuTarget(id) !== null


/** The items that only show a page, and the section of it to scroll to (the rest of the menu's items do something). */
export function menuTarget(id: string): { page: string; section?: string } | null {
  switch (id) {
    case 'app.settings':
      return { page: 'Settings' }
    case 'help.keys':
      return { page: 'Help', section: 'help-keyboard' }
    case 'app.about':
      return { page: 'Help', section: 'help-about' }
    case 'help.log':
      return { page: 'Settings', section: LOG_SECTION }
    default:
      return null
  }
}
