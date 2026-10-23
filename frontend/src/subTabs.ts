/**
 * Subpage tabs (items 60 and 61): the row of tabs under the page row on Connections and the Control Desk. Q / E step to
 * the previous / next tab and wrap around at the ends; the last tab of each page is remembered, also across restarts.
 */

/** The tab ``dir`` steps away from ``current``, wrapping around at the ends; the first one when ``current`` isn't a tab. */
export function stepTab<T>(ids: readonly T[], current: T, dir: 1 | -1): T {
  const i = ids.indexOf(current)
  if (i < 0) return ids[0]
  return ids[(i + dir + ids.length) % ids.length]
}

/** What a key press does to the tabs: Q the previous one, E the next; nothing with a modifier or while typing. */
export function subTabKey(e: { key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean }, typing: boolean): 1 | -1 | null {
  if (typing || e.metaKey || e.ctrlKey || e.altKey) return null
  const key = e.key.toLowerCase()
  return key === 'q' ? -1 : key === 'e' ? 1 : null
}

const STORE_KEY = 'pitchcontrol.subtab.'
// the tab of each page in this window; the browser's storage keeps it across restarts where it can
const memory = new Map<string, string>()

/** The remembered tab of a page, or ``fallback`` when none is remembered or it is no tab any more. */
export function rememberedTab<T extends string>(page: string, ids: readonly T[], fallback: T): T {
  let id = memory.get(page)
  if (id === undefined) {
    try {
      id = localStorage.getItem(STORE_KEY + page) ?? undefined
    } catch {
      /* no storage (private mode, tests): this window only */
    }
  }
  return ids.includes(id as T) ? (id as T) : fallback
}

/** Remember a page's tab. */
export function rememberTab(page: string, id: string) {
  memory.set(page, id)
  try {
    localStorage.setItem(STORE_KEY + page, id)
  } catch {
    /* this window only */
  }
}

export const SHOW_TAB_EVENT = 'pitchcontrol:subtab'

/** Open a page's tab from outside the page (the header's status indicators): remembered, and the open page switches to it. */
export function showTab(page: string, id: string) {
  rememberTab(page, id)
  window.dispatchEvent(new CustomEvent(SHOW_TAB_EVENT, { detail: { page, id } }))
}
