import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ModalHandle } from './modal'

type Listener = (e: unknown) => void

/** modal.ts installs its guard on ``window`` when it is loaded: a window that only records its listeners, so the guard can be run by hand. */
async function load() {
  vi.resetModules()
  const listeners: Record<string, Listener[]> = {}
  vi.stubGlobal('window', { addEventListener: (type: string, fn: Listener) => (listeners[type] ??= []).push(fn) })
  const body = {}
  vi.stubGlobal('document', { body, activeElement: body })
  const m = await import('./modal')
  return { m, listeners, body }
}

/** A key event as the browser makes it: ``target`` is what has the focus. */
function key(type: 'keydown' | 'keyup', k: string, target: unknown, extra: Record<string, unknown> = {}) {
  const e = { type, key: k, code: '', target, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, prevented: false, stopped: false, ...extra }
  return Object.assign(e, { preventDefault: () => (e.prevented = true), stopImmediatePropagation: () => (e.stopped = true) })
}

function fakeDialog(inside: unknown[], controls: { focus: () => void }[] = []) {
  const calls = { cancel: 0, focusIn: 0 }
  const handle: ModalHandle = {
    contains: (n) => inside.includes(n),
    cancel: () => calls.cancel++,
    focusables: () => controls as never,
    focusIn: () => calls.focusIn++,
  }
  return { handle, calls }
}

beforeEach(() => vi.unstubAllGlobals())
afterEach(() => vi.unstubAllGlobals())

describe('judgeKey: what a key does while a dialog is open', () => {
  const k = (key: string, extra: object = {}) => ({ key, ctrlKey: false, metaKey: false, altKey: false, ...extra })
  it('Esc cancels, Tab stays in the dialog', async () => {
    const { m } = await load()
    expect(m.judgeKey(k('Escape'), true)).toBe('cancel')
    expect(m.judgeKey(k('Escape'), false)).toBe('cancel')
    expect(m.judgeKey(k('Tab'), true)).toBe('tab')
    expect(m.judgeKey(k('Tab'), false)).toBe('tab')
  })
  it('a key typed in the dialog is its own, one typed outside is dropped (page keys, W A S D, Enter, Ctrl+S)', async () => {
    const { m } = await load()
    for (const x of ['1', '9', '0', 'w', 'a', 's', 'd', 'f', 'Enter', ' ', 'ArrowUp', 'F10', 'Alt']) {
      expect(m.judgeKey(k(x), true)).toBe('contain')
      expect(m.judgeKey(k(x), false)).toBe('swallow')
    }
    expect(m.judgeKey(k('s', { ctrlKey: true }), true)).toBe('contain')
    expect(m.judgeKey(k('s', { metaKey: true }), false)).toBe('swallow')
  })
  it('the UI scale keys work everywhere', async () => {
    const { m } = await load()
    for (const x of ['+', '=', '-', '_', '0']) expect(m.judgeKey(k(x, { ctrlKey: true }), false)).toBe('pass')
    expect(m.judgeKey(k('+', { metaKey: true }), true)).toBe('pass')
    expect(m.judgeKey(k('0'), false)).toBe('swallow') // the page-0 key without the modifier is not scale
  })
})

describe('tabTo: Tab goes round the dialog', () => {
  it('wraps at both ends and starts at an end when the focus is outside', async () => {
    const { m } = await load()
    expect(m.tabTo(3, 0, false)).toBe(1)
    expect(m.tabTo(3, 2, false)).toBe(0)
    expect(m.tabTo(3, 0, true)).toBe(2)
    expect(m.tabTo(3, -1, false)).toBe(0)
    expect(m.tabTo(3, -1, true)).toBe(2)
    expect(m.tabTo(0, -1, false)).toBe(-1)
  })
})

describe('the guard of an open dialog', () => {
  it('does nothing without a dialog', async () => {
    const { m, listeners } = await load()
    const e = key('keydown', '3', {})
    listeners.keydown.forEach((l) => l(e))
    expect(e.stopped).toBe(false)
    expect(e.prevented).toBe(false)
    expect(m.modalOpen()).toBe(false)
  })

  it('page keys and W A S D typed outside the dialog never reach the page; the focus is pulled into the dialog', async () => {
    const { m, listeners, body } = await load()
    const { handle, calls } = fakeDialog([{}])
    const close = m.pushModal(handle)
    expect(m.modalOpen()).toBe(true)
    const keys = ['1', '5', '0', 'w', 'a', 's', 'd', 'Enter', 'F10']
    for (const k of keys) {
      for (const type of ['keydown', 'keyup'] as const) {
        const e = key(type, k, body)
        listeners[type].forEach((l) => l(e))
        expect(e.stopped, `${type} ${k}`).toBe(true)
        expect(e.prevented).toBe(true)
      }
    }
    expect(calls.focusIn).toBe(keys.length) // once per keydown
    expect(calls.cancel).toBe(0)
    close()
    expect(m.modalOpen()).toBe(false)
  })

  it('a key typed in the dialog is left to the dialog (it stops it before the page), Ctrl+S outside is dropped', async () => {
    const { m, listeners, body } = await load()
    const field = {}
    const { handle } = fakeDialog([field])
    m.pushModal(handle)
    const typed = key('keydown', 'w', field)
    listeners.keydown.forEach((l) => l(typed))
    expect(typed.stopped).toBe(false)
    expect(typed.prevented).toBe(false)
    const save = key('keydown', 's', body, { ctrlKey: true })
    listeners.keydown.forEach((l) => l(save))
    expect(save.stopped).toBe(true)
  })

  it('Esc cancels the top dialog, wherever the focus is, once per press', async () => {
    const { m, listeners, body } = await load()
    const a = fakeDialog([body])
    const b = fakeDialog([{}])
    m.pushModal(a.handle)
    const closeB = m.pushModal(b.handle)
    listeners.keydown.forEach((l) => l(key('keydown', 'Escape', body)))
    listeners.keydown.forEach((l) => l(key('keydown', 'Escape', body, { repeat: true })))
    expect(b.calls.cancel).toBe(1)
    expect(a.calls.cancel).toBe(0)
    closeB()
    listeners.keydown.forEach((l) => l(key('keydown', 'Escape', body)))
    expect(a.calls.cancel).toBe(1)
  })

  it('Tab stays inside: from the last control to the first, from the first back to the last, from outside to the first', async () => {
    const { m, listeners, body } = await load()
    const log: string[] = []
    const first = { focus: () => log.push('first') }
    const last = { focus: () => log.push('last') }
    const d = fakeDialog([first, last], [first, last])
    m.pushModal(d.handle)
    const active = document as unknown as { activeElement: unknown }
    active.activeElement = last
    listeners.keydown.forEach((l) => l(key('keydown', 'Tab', last)))
    active.activeElement = first
    listeners.keydown.forEach((l) => l(key('keydown', 'Tab', first, { shiftKey: true })))
    listeners.keydown.forEach((l) => l(key('keydown', 'Tab', body)))
    expect(log).toEqual(['first', 'last', 'first'])
  })

  it('the focus is given back when the page takes it', async () => {
    const { m, listeners, body } = await load()
    const d = fakeDialog([{}])
    m.pushModal(d.handle)
    listeners.focusin.forEach((l) => l({ target: body }))
    expect(d.calls.focusIn).toBe(1)
  })
})

describe('returnFocus: the focus goes back to where it was', () => {
  it('to the control that had it, if it is still on the page', async () => {
    const { m, body } = await load()
    const focus = vi.fn()
    expect(m.returnFocus({ isConnected: true, focus }, body)).toBe(true)
    expect(focus).toHaveBeenCalledOnce()
  })
  it('nowhere when it had none, or it has gone', async () => {
    const { m, body } = await load()
    const focus = vi.fn()
    expect(m.returnFocus(null, body)).toBe(false)
    expect(m.returnFocus(body as never, body)).toBe(false)
    expect(m.returnFocus({ isConnected: false, focus }, body)).toBe(false)
    expect(focus).not.toHaveBeenCalled()
  })
})
