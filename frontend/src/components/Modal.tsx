import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { focusablesIn, judgeKey, pushModal, returnFocus } from '../modal'

/** The layout of a dialog that is a panel in the upper middle of the window, dimming the page. */
export const DEFAULT_LAYOUT = 'fixed inset-0 z-[60] flex items-start justify-center overflow-auto bg-black/60 px-3 pt-14 pb-6'

/**
 * Every modal dialog of the app is drawn inside this one (item 63): a backdrop over the whole window that takes the clicks,
 * the focus kept inside (Tab goes round the dialog's controls), **Esc** cancels, nothing typed reaches the page underneath
 * (the page keys, W A S D, Ctrl+S, the menu bar's keys: modal.ts), and when it closes the focus goes back to where it was.
 * ``onCancel`` is what Esc does, usually the same as the Cancel button. A dialog puts its own panel inside; the first
 * control marked ``data-first`` (or else the first one) gets the focus when it opens.
 */
export function Modal({ label, onCancel, className = DEFAULT_LAYOUT, children }: { label: string; onCancel: () => void; className?: string; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null)
  const cancel = useRef(onCancel)
  cancel.current = onCancel

  // before the first paint and before any effect of the dialog's own: where the focus was
  useLayoutEffect(() => {
    const before = document.activeElement as HTMLElement | null
    const el = root.current!
    const close = pushModal({
      contains: (n) => n instanceof Node && el.contains(n),
      cancel: () => cancel.current(),
      focusables: () => focusablesIn(el),
      focusIn: () => (el.querySelector<HTMLElement>('[data-first]') ?? focusablesIn(el)[0] ?? el).focus(),
    })
    return () => {
      close()
      returnFocus(before, document.body)
    }
  }, [])
  // after the dialog's own effects (a dialog may put the focus on a control of its own): if nothing inside has it, take it
  useEffect(() => {
    const el = root.current!
    if (!el.contains(document.activeElement)) (el.querySelector<HTMLElement>('[data-first]') ?? focusablesIn(el)[0] ?? el).focus()
  }, [])

  const contain = (e: React.KeyboardEvent) => {
    if (judgeKey(e.nativeEvent, true) !== 'pass') e.stopPropagation() // a key of the dialog's controls: not the page's
  }
  return (
    <div ref={root} className={`${className} outline-none`} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} onKeyDown={contain} onKeyUp={contain}>
      {children}
    </div>
  )
}
