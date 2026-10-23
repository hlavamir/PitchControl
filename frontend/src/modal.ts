// One mechanism for every modal dialog (item 63): while one is open, the page underneath gets no keys, no clicks and no
// focus. Kept free of React so the rules can be tested; components/Modal.tsx is the component that uses it.
//
// The page's keys (the number keys, W A S D, ⏎, Esc, Ctrl+S, the menu bar's Alt and F10) are listeners on ``window``.
// A key typed inside the dialog is stopped by the dialog before it gets there (``Modal``'s onKeyDown); a key whose
// target is outside the dialog (the focus is on the page, or nowhere) is caught here first, in the capture phase, and
// dropped. The guard is installed when this file is loaded, so it runs before the listeners that components add later.

export interface ModalHandle {
  contains(node: EventTarget | null): boolean
  cancel(): void // Esc: close the dialog as Cancel
  focusables(): HTMLElement[] // the dialog's controls in Tab order
  focusIn(): void // put the focus inside the dialog (its first control, or the dialog itself)
}

const stack: ModalHandle[] = []

/** Opens a modal: it is the top one until it is closed or another opens above it. Returns the close function. */
export function pushModal(h: ModalHandle): () => void {
  stack.push(h)
  return () => {
    const i = stack.indexOf(h)
    if (i >= 0) stack.splice(i, 1)
  }
}

/** Whether a modal dialog is open: the page's own handlers (the menu bar, its actions) hold back while it is. */
export const modalOpen = () => stack.length > 0

export type Verdict =
  | 'pass' // not the dialog's business: UI scale (Ctrl / ⌘ with + − 0) works everywhere
  | 'cancel' // Esc
  | 'tab' // Tab / Shift+Tab: the focus stays inside the dialog
  | 'contain' // typed inside the dialog: it goes to the control, the page doesn't see it
  | 'swallow' // typed outside the dialog: dropped

export interface KeyLike {
  key: string
  code?: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
}

/** What a key does while a modal is open; ``inside``: its target is inside the dialog. */
export function judgeKey(e: KeyLike, inside: boolean): Verdict {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && (['+', '=', '-', '_', '0'].includes(e.key) || e.code === 'NumpadAdd' || e.code === 'NumpadSubtract' || e.code === 'Numpad0')) return 'pass'
  if (e.key === 'Escape') return 'cancel'
  if (e.key === 'Tab' && !e.ctrlKey && !e.metaKey && !e.altKey) return 'tab'
  return inside ? 'contain' : 'swallow'
}

/** The control Tab goes to inside a dialog of ``count`` controls: wraps at both ends; ``at`` is the focused one (-1: none inside). */
export function tabTo(count: number, at: number, back: boolean): number {
  if (count <= 0) return -1
  if (at < 0) return back ? count - 1 : 0
  return (at + (back ? -1 : 1) + count) % count
}

/** When a dialog closes the focus goes back to the control that had it, if that control is still on the page (a dialog that
 * opened from a menu, or from a control that has since gone, has nothing to go back to). Returns whether it did. */
export function returnFocus(before: { isConnected: boolean; focus(): void } | null, body: unknown): boolean {
  if (!before || before === body || !before.isConnected) return false
  before.focus()
  return true
}

const FOCUSABLE = 'a[href],button,input,select,textarea,[tabindex]'

/** The controls of a dialog in Tab order: enabled, visible, not taken out of the order with tabindex -1. */
export function focusablesIn(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (el) => !(el as HTMLButtonElement).disabled && el.tabIndex >= 0 && el.getAttribute('type') !== 'hidden' && el.getClientRects().length > 0,
  )
}

function onKey(e: KeyboardEvent) {
  const top = stack[stack.length - 1]
  if (!top) return
  const inside = top.contains(e.target)
  const verdict = judgeKey(e, inside)
  if (verdict === 'pass' || verdict === 'contain') return // ``Modal`` stops what is typed inside before it reaches the page
  e.preventDefault()
  e.stopImmediatePropagation()
  if (e.type !== 'keydown') return
  if (verdict === 'swallow') return top.focusIn() // the focus was on the page: the next key goes to the dialog
  if (verdict === 'cancel') {
    if (!e.repeat) top.cancel()
    return
  }
  // Tab: round the dialog's own controls, never out of it
  const items = top.focusables()
  const next = items[tabTo(items.length, inside ? items.indexOf(document.activeElement as HTMLElement) : -1, e.shiftKey)]
  if (next) next.focus()
  else top.focusIn()
}

function onFocusIn(e: FocusEvent) {
  const top = stack[stack.length - 1]
  if (top && !top.contains(e.target)) top.focusIn() // the page took the focus (a script, the browser): give it back
}

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', onKey, true)
  window.addEventListener('keyup', onKey, true)
  window.addEventListener('focusin', onFocusIn, true)
}
