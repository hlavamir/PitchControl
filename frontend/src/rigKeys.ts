/** Keyboard on the Rig page's fixture list, like files in Finder / Explorer (the mouse side is listSelection.ts). */
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
  | { kind: 'details' } // D, →: focus the first field of the details
  | { kind: 'list' } // Esc (also out of a field), A: back to the list

/**
 * What a key does on the Rig page, or null when it is not ours.
 *
 * ``typing``: the focus is in a text field or a select, where keys are text (↑ / ↓ change the value there)
 * and only Esc is ours, to leave it. ``onList``: Space belongs to the list only when nothing else has
 * the focus (a focused switch or button keeps Space).
 */
export function rigKeyAction(e: KeyInfo, typing: boolean, onList: boolean): RigKeyAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  if (e.key === 'Escape') return { kind: 'list' }
  if (typing) return null
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
  if (key === 'w' || key === 'ArrowUp') return { kind: 'move', step: -1, shift: e.shiftKey }
  if (key === 's' || key === 'ArrowDown') return { kind: 'move', step: 1, shift: e.shiftKey }
  if (key === 'd' || key === 'ArrowRight') return { kind: 'details' }
  if (key === 'a') return { kind: 'list' }
  if (key === ' ' && onList && !e.repeat) return { kind: 'toggle' }
  return null
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
