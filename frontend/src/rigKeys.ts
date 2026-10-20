/** Keyboard on the Rig page: the fixture list like files in Finder / Explorer (the mouse side is listSelection.ts), and the details field by field. */
import { moveField, type FieldBox, type FieldDir, type Zone } from './fieldNav'
import { clickSelection, type ListSelection } from './listSelection'

export interface KeyInfo {
  key: string
  shiftKey: boolean
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  repeat?: boolean
}

export type RigKeyAction =
  | { kind: 'move'; step: 1 | -1; shift: boolean } // W / S, ↑ / ↓ (Shift: extend the range)
  | { kind: 'toggle' } // Space: add / remove the current fixture, without moving
  | { kind: 'details' } // D, →: go into the details (the first field is highlighted, not edited)
  | { kind: 'field'; dir: FieldDir } // in the details: W A S D / arrows move from field to field
  | { kind: 'edit' } // in the details: ⏎ starts editing the highlighted field
  | { kind: 'stop' } // in a field of the details: ⏎ / Esc stops editing
  | { kind: 'list' } // Esc (in the details, or out of a field elsewhere), A: back to the list

export interface KeyContext {
  typing: boolean // the focus is in a text field or a select, where keys are text
  onList: boolean // nothing but the list (or the page) has the focus: Space belongs to the list
  zone: Zone // where the keys navigate
  inDetails: boolean // the focus is in the details section
  multiline?: boolean // the field is a text area (⏎ is a line break)
}

/**
 * What a key does on the Rig page, or null when it is not ours.
 *
 * In the list the keys move like in a file list. In the details they only navigate (W S ↑ ↓ from field to field,
 * A D / ← → across a row) and never change a value: ⏎ starts editing the highlighted field, and while editing
 * the keys are text (↑ / ↓ change a number) until ⏎ or Esc stops it.
 */
export function rigKeyAction(e: KeyInfo, ctx: KeyContext): RigKeyAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  if (ctx.typing) {
    if (e.key === 'Escape') return { kind: ctx.inDetails ? 'stop' : 'list' }
    if (e.key === 'Enter' && ctx.inDetails && !ctx.multiline) return { kind: 'stop' }
    return null
  }
  if (e.key === 'Escape') return { kind: 'list' }
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
  if (ctx.zone === 'details') {
    if (key === 'w' || key === 'ArrowUp') return { kind: 'field', dir: 'up' }
    if (key === 's' || key === 'ArrowDown') return { kind: 'field', dir: 'down' }
    if (key === 'a' || key === 'ArrowLeft') return { kind: 'field', dir: 'left' }
    if (key === 'd' || key === 'ArrowRight') return { kind: 'field', dir: 'right' }
    if (key === 'Enter' && !e.repeat) return { kind: 'edit' }
    return null
  }
  if (key === 'w' || key === 'ArrowUp') return { kind: 'move', step: -1, shift: e.shiftKey }
  if (key === 's' || key === 'ArrowDown') return { kind: 'move', step: 1, shift: e.shiftKey }
  if (key === 'd' || key === 'ArrowRight') return { kind: 'details' }
  if (key === 'a') return { kind: 'list' }
  if (key === ' ' && ctx.onList && !e.repeat) return { kind: 'toggle' }
  return null
}

export interface NavState {
  zone: Zone
  index: number // the highlighted field of the details
}

export type NavEffect = 'none' | 'blur' | 'edit' // blur: take the focus off whatever has it; edit: start editing the highlighted field

/**
 * What an action does to the navigation: the zone and the highlighted field, and the one thing to do to the
 * page. Entering the details only highlights the first field (with a "blur", so nothing has the focus and no key
 * can change a value); only ``edit`` ever touches a field.
 */
export function navStep(s: NavState, a: RigKeyAction, boxes: FieldBox[]): { state: NavState; effect: NavEffect } {
  switch (a.kind) {
    case 'details':
      return boxes.length ? { state: { zone: 'details', index: 0 }, effect: 'blur' } : { state: s, effect: 'none' }
    case 'field': {
      if (s.zone !== 'details' || !boxes.length) return { state: s, effect: 'none' }
      const from = Math.min(s.index, boxes.length - 1)
      const to = moveField(boxes, from, a.dir)
      if (to == null) return a.dir === 'left' ? { state: { zone: 'list', index: from }, effect: 'blur' } : { state: { ...s, index: from }, effect: 'none' }
      return { state: { zone: 'details', index: to }, effect: 'none' }
    }
    case 'edit':
      return { state: s, effect: s.zone === 'details' && boxes.length ? 'edit' : 'none' }
    case 'stop':
      return { state: { ...s, zone: 'details' }, effect: 'blur' }
    case 'list':
      return { state: { ...s, zone: 'list' }, effect: 'blur' }
    default:
      return { state: s, effect: 'none' }
  }
}

/** What ⏎ does to a control: a text or number field takes the caret, a select opens, a switch / checkbox / button is pressed. */
export function editKind(el: { tagName: string; type?: string }): 'caret' | 'open' | 'press' {
  if (el.tagName === 'SELECT') return 'open'
  if (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !['checkbox', 'radio', 'button', 'submit'].includes(el.type ?? 'text'))) return 'caret'
  return 'press'
}

export interface ListCursor extends ListSelection {
  cursor: number | null // the current fixture: the one the keys move from and Space toggles
}

/** The cursor's place in the shown order; without a valid cursor the first selected fixture. */
function cursorAt(order: number[], at: ListCursor): number {
  const i = [at.cursor, ...at.selected].find((x) => x != null && order.includes(x))
  return i == null ? -1 : order.indexOf(i)
}

/**
 * W / S / ↑ / ↓: the cursor moves one fixture in the shown order (it stops at the ends). Plain: only that
 * fixture is selected and it is the anchor. Shift: the range from the anchor to it, by the rule of
 * Shift + click (clickSelection), and the anchor stays.
 */
export function stepSelection(order: number[], at: ListCursor, step: 1 | -1, shift: boolean): ListCursor {
  if (!order.length) return at
  const from = cursorAt(order, at)
  const to = order[Math.min(order.length - 1, Math.max(0, (from < 0 ? 0 : from) + step))]
  const next = clickSelection(order, at, to, { shift, toggle: false })
  return { ...next, cursor: to }
}

/** Space: the current fixture is added or removed (the last one can't be removed), the cursor stays. */
export function toggleCurrent(order: number[], at: ListCursor): ListCursor {
  const i = cursorAt(order, at)
  if (i < 0) return at
  const cursor = order[i]
  return { ...clickSelection(order, at, cursor, { shift: false, toggle: true }), cursor }
}
