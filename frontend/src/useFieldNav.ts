import { useContext, useEffect, useRef, useState, type RefObject } from 'react'
import { moveField, type FieldBox } from './fieldNav'
import { hintAt, type HintKind } from './hints'
import { editKind, navStep, rigKeyAction, type NavState, type RigKeyAction } from './rigKeys'
import { SelectionContext, isTypingTarget, type FooterSelection } from './useGridNav'

/** The controls of a page that the keys move over, in the order of the page. */
export const NAV_CONTROLS = 'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [role="slider"]'

/** ⏎ on a highlighted control: a text or number field takes the caret, a select opens, a switch or button is pressed. */
export function editField(el: HTMLElement | undefined) {
  if (!el) return
  const kind = editKind({ tagName: el.tagName, type: (el as HTMLInputElement).type, role: el.getAttribute('role') })
  if (kind === 'press') return el.click()
  el.focus()
  if (kind === 'open') {
    try {
      ;(el as HTMLSelectElement).showPicker()
    } catch {
      /* the focused select still changes with the arrow keys */
    }
  } else if (kind === 'caret') {
    const input = el as HTMLInputElement
    try {
      input.setSelectionRange(input.value.length, input.value.length)
    } catch {
      /* no caret to place */
    }
  }
}

/** The footer keys of a highlighted control: what ⏎ does to it. */
export function navHint(el: HTMLElement): HintKind {
  const kind = editKind({ tagName: el.tagName, type: (el as HTMLInputElement).type, role: el.getAttribute('role') })
  if (kind === 'caret' || kind === 'adjust') return 'nav-edit'
  if (kind === 'open') return 'nav-open'
  return el.getAttribute('role') === 'switch' || el.getAttribute('role') === 'checkbox' ? 'nav-toggle' : 'nav-press'
}

export interface FieldNavOptions {
  /** The part of the page whose controls the keys move over. */
  root: RefObject<HTMLElement | null>
  /** A list on the page that the keys select in first (the Rig page's fixtures); without it the page is the controls only. */
  list?: RefObject<HTMLElement | null>
  /**
   * The part of ``root`` the keys enter first (D from the list), and that A leaves for the list at its left edge;
   * the rest of the page (a panel beside or around the list) is reached from the ends of the list.
   */
  entry?: RefObject<HTMLElement | null>
  /** W / S / ↑ / ↓ and Space on the list; false when a plain move found no fixture further on (the keys then leave the list). */
  onListAction?: (action: Extract<RigKeyAction, { kind: 'move' | 'toggle' }>) => boolean | void
  /** What the footer says while the keys are on the list. */
  listFooter?: FooterSelection | null
}

/**
 * Keyboard navigation of a page's controls, field by field (see rigKeys.ts for the keys): W S ↑ ↓ A D / arrows move
 * a highlight (an attribute, not the focus) over the controls of ``root``, ⏎ starts editing the highlighted one and
 * ⏎ / Esc stops. Never a key press changes a value without ⏎ first. With a ``list`` the keys start on the list.
 */
export function useFieldNav({ root, list, entry, onListAction, listFooter }: FieldNavOptions) {
  const hasList = !!list
  const [nav, setNav] = useState<NavState>({ zone: 'list', index: 0 })
  const controlsOf = () =>
    [...(root.current?.querySelectorAll<HTMLElement>(NAV_CONTROLS) ?? [])].filter((el) => el.getClientRects().length > 0 && !list?.current?.contains(el))
  const boxesOf = (els: HTMLElement[]): FieldBox[] =>
    els.map((el) => {
      const r = el.getBoundingClientRect()
      return { l: r.left, r: r.right, cy: r.top + r.height / 2, h: r.height }
    })

  const onKey = useRef<(e: KeyboardEvent) => void>(() => undefined)
  onKey.current = (e) => {
    const t = e.target as HTMLElement | null
    const onList = !t || t === document.body || !!list?.current?.contains(t)
    const typing = isTypingTarget(t)
    // ⏎ does nothing on the list: on a focused list button it would select that one alone (the browser's click),
    // which throws away a range the keys just made
    if (e.key === 'Enter' && !typing && list?.current?.contains(t)) return e.preventDefault()
    const action = rigKeyAction(e, {
      typing,
      onList,
      zone: nav.zone,
      hasList,
      inDetails: !!t && !!root.current?.contains(t) && !list?.current?.contains(t),
      multiline: t?.tagName === 'TEXTAREA',
    })
    if (!action) return
    e.preventDefault()
    const els = controlsOf()
    if (action.kind === 'move' || action.kind === 'toggle') {
      if (onListAction?.(action) !== false || action.kind !== 'move' || action.shift || !list?.current) return
      // the end of the list: carry on to the nearest control above / below it
      const boxes = [...boxesOf(els), boxesOf([list.current])[0]]
      const to = moveField(boxes, els.length, action.step < 0 ? 'up' : 'down')
      if (to != null && to < els.length) setNav({ zone: 'details', index: to })
      return
    }
    if (entry?.current && (action.kind === 'details' || (action.kind === 'field' && action.dir === 'left'))) {
      const inEntry = els.map((el) => entry.current!.contains(el))
      if (action.kind === 'details') {
        const first = inEntry.indexOf(true)
        if (first >= 0) setNav({ zone: 'details', index: first })
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
        return
      }
      const cur = Math.min(nav.index, els.length - 1)
      if (inEntry[cur]) {
        // A stays in the entry part, and leaves it for the list at its left edge
        const idx = els.map((_, i) => i).filter((i) => inEntry[i])
        const to = moveField(boxesOf(idx.map((i) => els[i])), idx.indexOf(cur), 'left')
        setNav(to == null ? { zone: 'list', index: cur } : { zone: 'details', index: idx[to] })
        if (to == null && document.activeElement instanceof HTMLElement) document.activeElement.blur()
        return
      }
    }
    const at = action.kind === 'stop' && t ? els.indexOf(t) : -1 // stopping editing leaves the field highlighted
    const { state, effect } = navStep(at >= 0 ? { zone: 'details', index: at } : nav, action, boxesOf(els))
    setNav(state)
    if (effect === 'blur' && document.activeElement instanceof HTMLElement) document.activeElement.blur()
    if (effect === 'edit') editField(els[Math.min(state.index, els.length - 1)])
  }
  useEffect(() => {
    const down = (e: KeyboardEvent) => onKey.current(e)
    // a focused list button would also take Space as a click (a plain select) when the key comes up
    const up = (e: KeyboardEvent) => {
      if (e.key === ' ' && list?.current?.contains(e.target as Node)) e.preventDefault()
    }
    // a click outside gives the keys back to the list; a field that gets the focus (a click, Tab, ⏎) is the highlighted one
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node) || list?.current?.contains(e.target as Node)) setNav((n) => (n.zone === 'list' ? n : { ...n, zone: 'list' }))
    }
    const focus = (e: FocusEvent) => {
      const t = e.target as HTMLElement
      if (!root.current?.contains(t) || list?.current?.contains(t)) return
      // Chromium (the Windows app) also focuses a button that is clicked, WebKit doesn't: a click on a button, tab or
      // link is not a keyboard selection, so only a focus the keys gave it (Tab, :focus-visible) takes the highlight
      if (t.matches('button, a[href], [role="tab"], [role="switch"], [role="slider"]') && !t.matches(':focus-visible')) return
      const i = controlsOf().indexOf(t)
      if (i >= 0) setNav({ zone: 'details', index: i })
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('pointerdown', away)
    document.addEventListener('focusin', focus)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('pointerdown', away)
      document.removeEventListener('focusin', focus)
    }
  }, [])

  // the highlight is an attribute on the control (styled like the selection on the other pages), not the focus:
  // a focused field would take the keys as text
  useEffect(() => {
    root.current?.querySelectorAll('[data-nav]').forEach((el) => el.removeAttribute('data-nav'))
    if (nav.zone !== 'details') return
    const els = controlsOf()
    els[Math.min(nav.index, els.length - 1)]?.setAttribute('data-nav', '')
  })
  useEffect(() => {
    if (nav.zone !== 'details') return
    const els = controlsOf()
    els[Math.min(nav.index, els.length - 1)]?.scrollIntoView({ block: 'nearest' })
  }, [nav.zone, nav.index])

  // the footer names the keys of the highlighted control while they are in use
  const setFooter = useContext(SelectionContext)
  const listKey = listFooter ? `${listFooter.label}|${listFooter.hint}|${listFooter.tip}` : ''
  useEffect(() => {
    const els = nav.zone === 'details' ? controlsOf() : []
    const el = els[Math.min(nav.index, els.length - 1)]
    if (el) {
      const label = el.closest('[data-row]')?.querySelector('.lbl')?.textContent || el.getAttribute('aria-label') || el.textContent?.replace('›', '').trim() || 'field'
      setFooter({ label, hint: navHint(el), tip: hintAt(el)?.tip })
    } else setFooter(listFooter ?? null)
  }, [listKey, nav.zone, nav.index, setFooter])
  useEffect(() => () => setFooter(null), [setFooter])

  return nav
}
