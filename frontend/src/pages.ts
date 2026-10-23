// The pages of the page row and their keys (item 60: Inputs and Outputs became Connections). menu.py has the same list.

/** The pages in the order of the keys 1 to 9; 0 has no page. */
export const PAGES = ['General', 'Dimmers', 'Fixtures', 'Rig', 'Connections', 'Fog', 'Control Desk', 'Settings', 'Help'] as const
export type Page = (typeof PAGES)[number]

/** The page of a number key, null for a key without one (0). */
export const pageOfKey = (n: number): Page | null => PAGES[n - 1] ?? null
export const keyOfPage = (p: Page) => PAGES.indexOf(p) + 1

/** The subpage tabs of Connections. */
export const CONNECTION_TABS = ['audio', 'midi', 'dmx', 'osc', 'serial'] as const
export type ConnectionTab = (typeof CONNECTION_TABS)[number]

/** The Control Desk's subpages: the eight blocks of 64 channels, then the routes. */
export const DESK_TABS = ['ch-0', 'ch-1', 'ch-2', 'ch-3', 'ch-4', 'ch-5', 'ch-6', 'ch-7', 'routes'] as const
export type DeskTab = (typeof DESK_TABS)[number]

/**
 * The page (and Connections tab) of a URL hash: ``#Connections/midi``; the pages that became tabs of Connections
 * (bookmarks from before item 60) open their tab.
 */
export function pageOfHash(hash: string): { page: Page; tab?: ConnectionTab } {
  const [name, tab] = decodeURIComponent(hash.replace(/^#/, '')).split('/')
  if (name === 'Inputs') return { page: 'Connections', tab: 'audio' }
  if (name === 'Outputs' || name === 'Output') return { page: 'Connections', tab: 'dmx' }
  if (!(PAGES as readonly string[]).includes(name)) return { page: 'General' }
  return name === 'Connections' && (CONNECTION_TABS as readonly string[]).includes(tab) ? { page: name, tab: tab as ConnectionTab } : { page: name as Page }
}
