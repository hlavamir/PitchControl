/** Selecting in a list as in Explorer / Finder: click, Shift + click (range), Ctrl / Cmd + click (toggle one). */

export interface ListSelection {
  selected: number[] // indices (into the items, not into the displayed order)
  anchor: number | null // where a Shift range starts: the item last picked by a click or a toggle
}

/**
 * The selection after a click on ``index``.
 *
 * - plain click: just that item, and it becomes the anchor;
 * - toggle (Ctrl on Windows, Cmd on macOS): adds or removes that item (the last one can't be removed),
 *   and the clicked item becomes the anchor;
 * - Shift: everything between the anchor and the clicked item, in the order the list is shown in,
 *   replaces the selection; the anchor stays, so the next Shift + click changes the range;
 * - toggle + Shift: the range is added to the selection.
 *
 * ``order`` is the displayed order (the list is sorted by name, the indices are not).
 */
export function clickSelection(
  order: number[],
  current: ListSelection,
  index: number,
  { shift, toggle }: { shift: boolean; toggle: boolean },
): ListSelection {
  if (shift) {
    const from = [current.anchor, ...current.selected].find((i) => i != null && order.includes(i)) ?? index
    const a = order.indexOf(from)
    const b = order.indexOf(index)
    if (a < 0 || b < 0) return { selected: [index], anchor: index }
    const range = order.slice(Math.min(a, b), Math.max(a, b) + 1)
    return { selected: toggle ? [...current.selected.filter((i) => !range.includes(i)), ...range] : range, anchor: from }
  }
  if (toggle) {
    const on = current.selected.includes(index)
    if (on && current.selected.length === 1) return { selected: current.selected, anchor: index }
    return { selected: on ? current.selected.filter((i) => i !== index) : [...current.selected, index], anchor: index }
  }
  return { selected: [index], anchor: index }
}
