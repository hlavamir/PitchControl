// The ``links`` of an imported fixture type (the Open Fixture Library's: manual, product page, video, ...), for the Fixtures page.

import type { FixtureType } from './api'

const LABELS: Record<string, string> = { manual: 'Manual', productPage: 'Product page', video: 'Video', other: 'More' }

/** The web addresses of a type's ``links`` by kind, in OFL's order of kinds (manual first); anything that isn't http(s) is left out. */
export function linkGroups(t: Pick<FixtureType, 'links'>): { label: string; urls: string[] }[] {
  const links = t.links
  if (!links || typeof links !== 'object') return []
  return Object.entries(links)
    .map(([kind, urls]) => ({
      label: LABELS[kind] ?? kind,
      urls: Array.isArray(urls) ? urls.filter((u): u is string => typeof u === 'string' && /^https?:\/\//.test(u)) : [],
    }))
    .filter((g) => g.urls.length > 0)
}
