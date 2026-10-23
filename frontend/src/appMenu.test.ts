import { describe, expect, it } from 'vitest'
import { AltTap, CLOSED, LOG_SECTION, actsOnPage, activate, menuKey, menuTarget, nextItem, openByLetter, showDrawnMenu, type MenuDef, type MenuState } from './appMenu'

const item = (id: string, label = id) => ({ id, label, kind: 'ui' as const, key: '' })
const MENUS: MenuDef[] = [
  { title: 'File', items: [item('file.save'), null, item('file.data_folder'), item('file.quit')] },
  { title: 'Edit', items: [item('edit.cut'), item('edit.copy'), item('edit.paste'), null, item('edit.select_all')] },
  { title: 'View', items: [item('view.page.1'), item('view.page.2'), null, item('view.fullscreen')] },
  { title: 'Window', items: [item('window.minimize')] },
  { title: 'Help', items: [item('help.docs'), item('help.keys')] },
]
const all = (_id?: string) => true
const press = (state: MenuState, ...keys: string[]) => keys.reduce<{ state: MenuState; run?: string }>((r, k) => menuKey(r.state, k, MENUS, all), { state })

describe('showDrawnMenu: only in the Windows app window', () => {
  const win = { local: true, platform: 'win32' }
  it('the desktop window on Windows', () => expect(showDrawnMenu('?window=app', win)).toBe(true))
  it('not in a browser, here or on the network', () => {
    expect(showDrawnMenu('', win)).toBe(false) // a browser on this computer ("Open in browser")
    expect(showDrawnMenu('?window=app', { local: false, platform: 'win32' })).toBe(false) // a phone, even with the parameter typed in
  })
  it('not on macOS (the native menu bar)', () => expect(showDrawnMenu('?window=app', { local: true, platform: 'darwin' })).toBe(false))
  it('not before the app info is known', () => expect(showDrawnMenu('?window=app', null)).toBe(false))
})

describe('menuKey: Windows menu conventions', () => {
  it('Alt / F10 highlights the first title, nothing open yet', () => {
    expect(activate()).toEqual({ active: true, menu: 0, open: false, item: null, subOpen: false, sub: null, keys: true })
  })
  it('← → move between the titles, wrapping', () => {
    expect(press(activate(), 'ArrowRight', 'ArrowRight').state.menu).toBe(2)
    expect(press(activate(), 'ArrowLeft').state.menu).toBe(4)
  })
  it('↓ opens the menu on its first item, ↑ on its last', () => {
    expect(press(activate(), 'ArrowDown').state).toMatchObject({ open: true, item: 0 })
    expect(press(activate(), 'ArrowUp').state).toMatchObject({ open: true, item: 3 })
  })
  it('↓ ↑ skip the separators and wrap', () => {
    expect(press(activate(), 'ArrowDown', 'ArrowDown').state.item).toBe(2) // past the separator after Save
    expect(press(activate(), 'ArrowDown', 'ArrowUp').state.item).toBe(3) // from Save up to the last item
  })
  it('← → with a menu open open the neighbour', () => {
    expect(press(activate(), 'ArrowDown', 'ArrowRight').state).toMatchObject({ menu: 1, open: true, item: 0 })
  })
  it('⏎ runs the highlighted item and closes the bar', () => {
    const r = press(activate(), 'ArrowRight', 'ArrowRight', 'ArrowDown', 'ArrowDown', 'Enter')
    expect(r.run).toBe('view.page.2')
    expect(r.state).toEqual(CLOSED)
  })
  it('Esc closes the drop-down first, then the bar', () => {
    const open = press(activate(), 'ArrowDown').state
    expect(press(open, 'Escape').state).toMatchObject({ active: true, open: false })
    expect(press(open, 'Escape', 'Escape').state).toEqual(CLOSED)
  })
  it('a letter opens its menu (Alt+V, or V while the bar is active)', () => {
    expect(openByLetter(MENUS, 'v', all)).toMatchObject({ menu: 2, open: true, item: 0 })
    expect(openByLetter(MENUS, 'x', all)).toBeNull()
    expect(press(activate(), 'h').state).toMatchObject({ menu: 4, open: true })
  })
  it('the page keys do nothing while the bar is active: W, 3, F are not runs', () => {
    for (const k of ['w', '3', 'Tab']) expect(press(activate(), k).run).toBeUndefined()
  })
  it('nothing happens while the bar is not active', () => expect(press(CLOSED, 'ArrowDown', 'Enter')).toEqual({ state: CLOSED }))
  it('disabled items are skipped and never run', () => {
    const noCut = (id: string) => id !== 'edit.cut' && id !== 'edit.copy'
    const opened = openByLetter(MENUS, 'e', noCut)!
    expect(opened.item).toBe(2) // Paste: Cut and Copy without a selection
    expect(nextItem(MENUS[0], null, 1, () => false)).toBeNull()
    const none = openByLetter(MENUS, 'w', () => false)!
    expect(menuKey(none, 'Enter', MENUS, () => false).run).toBeUndefined()
  })
})

describe('menuKey: a submenu (File → Import Fixture ▸)', () => {
  const FILE: MenuDef[] = [
    { title: 'File', items: [item('file.save'), null, { submenu: 'Import Fixture', items: [item('file.import.ofl'), item('file.import.qlc')] }, null, item('file.quit')] },
    { title: 'Edit', items: [item('edit.copy')] },
  ]
  const keys = (state: MenuState, enabled: (id: string) => boolean, ...ks: string[]) => ks.reduce<{ state: MenuState; run?: string }>((r, k) => menuKey(r.state, k, FILE, enabled), { state })
  const onSub = (enabled: (id: string) => boolean = all) => keys(activate(), enabled, 'ArrowDown', 'ArrowDown') // the submenu row, past Save and the separator

  it('↓ lands on the submenu row like on any item', () => expect(onSub().state).toMatchObject({ open: true, item: 2, subOpen: false }))
  it('→ opens the flyout on its first item, ⏎ too', () => {
    expect(keys(onSub().state, all, 'ArrowRight').state).toMatchObject({ item: 2, subOpen: true, sub: 0 })
    expect(keys(onSub().state, all, 'Enter').state).toMatchObject({ subOpen: true, sub: 0 })
    expect(keys(onSub().state, all, 'Enter').run).toBeUndefined() // opening is not running
  })
  it('↓ ↑ move in the flyout, ⏎ runs the item and closes everything', () => {
    const open = keys(onSub().state, all, 'ArrowRight', 'ArrowDown')
    expect(open.state.sub).toBe(1)
    expect(keys(open.state, all, 'ArrowDown').state.sub).toBe(0) // wraps
    const run = keys(open.state, all, 'Enter')
    expect(run.run).toBe('file.import.qlc')
    expect(run.state).toEqual(CLOSED)
  })
  it('← and Esc close the flyout only; Esc again the drop-down', () => {
    const open = keys(onSub().state, all, 'ArrowRight').state
    for (const k of ['ArrowLeft', 'Escape']) expect(keys(open, all, k).state).toMatchObject({ active: true, open: true, item: 2, subOpen: false, sub: null })
    expect(keys(open, all, 'Escape', 'Escape').state).toMatchObject({ open: false, active: true })
  })
  it('in the flyout the other keys do nothing: no jump to another menu, no letters', () => {
    const open = keys(onSub().state, all, 'ArrowRight').state
    expect(keys(open, all, 'e').state).toEqual(open)
    expect(keys(open, all, 'ArrowRight').state).toEqual(open)
  })
  it('a disabled item of the flyout is skipped and never runs', () => {
    const noOfl = (id: string) => id !== 'file.import.ofl'
    expect(keys(onSub(noOfl).state, noOfl, 'ArrowRight').state.sub).toBe(1)
    expect(keys(onSub(noOfl).state, () => false, 'ArrowRight', 'Enter').run).toBeUndefined()
  })
  it('moving to another item closes the flyout; → on a plain item still goes to the next menu', () => {
    const open = keys(onSub().state, all, 'ArrowRight').state
    expect(menuKey({ ...open, subOpen: false, sub: null }, 'ArrowDown', FILE, all).state).toMatchObject({ item: 4, subOpen: false })
    expect(keys(activate(), all, 'ArrowDown', 'ArrowRight').state).toMatchObject({ menu: 1, open: true })
  })
})

describe('AltTap: Alt alone toggles the bar', () => {
  const k = (key: string, extra: Partial<{ ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; repeat: boolean }> = {}) => ({ key, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, ...extra })
  it('Alt down and up is a tap', () => {
    const t = new AltTap()
    t.down(k('Alt'))
    expect(t.up(k('Alt'))).toBe(true)
  })
  it('held Alt (repeats) is still a tap when released alone', () => {
    const t = new AltTap()
    t.down(k('Alt'))
    t.down(k('Alt', { repeat: true }))
    expect(t.up(k('Alt'))).toBe(true)
  })
  it('Alt with another key is not (Alt+F, Alt+Tab, Alt+Shift)', () => {
    for (const other of [k('f'), k('Tab'), k('Shift', { shiftKey: true })]) {
      const t = new AltTap()
      t.down(k('Alt'))
      t.down(other)
      expect(t.up(k('Alt'))).toBe(false)
    }
  })
  it('AltGr is not (typing @ { [ on a German keyboard)', () => {
    const t = new AltTap()
    t.down(k('Control', { ctrlKey: true }))
    t.down(k('AltGraph', { ctrlKey: true }))
    expect(t.up(k('AltGraph'))).toBe(false)
    t.down(k('Alt', { ctrlKey: true })) // Ctrl+Alt reported as Alt
    expect(t.up(k('Alt'))).toBe(false)
  })
  it('a click in between cancels', () => {
    const t = new AltTap()
    t.down(k('Alt'))
    t.cancel()
    expect(t.up(k('Alt'))).toBe(false)
  })
})

describe('the items that show a page', () => {
  it('Help → Show log opens Settings at the log panel', () => {
    expect(menuTarget('help.log')).toEqual({ page: 'Settings', section: LOG_SECTION })
    expect(LOG_SECTION).toBe('settings-log') // the id of the panel (LogSection.tsx)
  })
  it('keeps the others: Settings…, Keyboard shortcuts, About', () => {
    expect(menuTarget('app.settings')).toEqual({ page: 'Settings' })
    expect(menuTarget('help.keys')).toEqual({ page: 'Help', section: 'help-keyboard' })
    expect(menuTarget('app.about')).toEqual({ page: 'Help', section: 'help-about' })
  })
  it('leaves the items that do something else to their own actions', () => {
    for (const id of ['file.save', 'view.page.3', 'help.report', 'help.docs', 'file.logs_folder']) expect(menuTarget(id)).toBeNull()
  })
})

describe('the items that wait while a dialog is open (item 63)', () => {
  it('the ones that change, save or open something on the page', () => {
    for (const id of ['view.page.3', 'file.save', 'file.import.ofl', 'file.import.qlc', 'app.settings', 'help.keys', 'app.about', 'help.log']) expect(actsOnPage(id)).toBe(true)
  })
  it('not the ones that leave the page alone', () => {
    for (const id of ['help.report', 'help.docs', 'file.logs_folder', 'file.quit', 'edit.copy', 'view.fullscreen']) expect(actsOnPage(id)).toBe(false)
  })
})
