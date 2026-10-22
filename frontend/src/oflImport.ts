// Import Fixture → Open Fixture Library (item 53): what the dialog needs that isn't React. The conversion, the report and
// the saving are the backend's (ofl/importer.py, POST /api/ofl/convert and /api/fixture-types/import).

import type { FixtureType } from './api'
import type { Origin } from './components/RigPanel'

export interface OflReport {
  fixture: { name: string; manufacturer?: string | null; key?: string | null; url?: string | null }
  modes: { name: string; ofl_mode: string; pixels: number; channels: number; description: string }[]
  skipped: { mode: string; reason: string; detail: string }[]
  assumptions: string[]
  notes: string[]
  manual: string[]
  check: string
}


export interface Existing {
  name: string
  origin: Origin
  used_in: string[]
}

export interface Converted {
  name: string
  type: FixtureType | null // null: none of the fixture's modes can be expressed
  report: OflReport
  existing: Existing | null
}

/** What the type's name may be: a file name (the same rule as a rig's, loader.py RIG_NAME). */
export const NAME_RULE = /^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$/

/** The type that ``name`` would clash with: the same name in any letter case (they are file names). */
export function clashOf(name: string, types: Record<string, unknown>, origins: Record<string, Origin>, usage: Record<string, string[]>): Existing | null {
  const taken = Object.keys(types).find((n) => n.toLowerCase() === name.trim().toLowerCase())
  return taken === undefined ? null : { name: taken, origin: origins[taken] ?? 'user', used_in: usage[taken] ?? [] }
}

/** What the dialog's main button does for a name: import it, replace the type that has the name (it asks first: the clash panel
 * names what would be overwritten), or nothing yet. */
export type Action = { kind: 'import' } | { kind: 'replace'; existing: Existing } | { kind: 'blocked'; why: string }

export function actionFor(name: string, converted: Converted | null, clash: Existing | null): Action {
  if (!converted?.type) return { kind: 'blocked', why: 'none of this fixture’s modes can be imported' }
  if (!NAME_RULE.test(name.trim())) return { kind: 'blocked', why: 'a name needs letters, digits, space, - _ . (at most 64, starting with a letter or digit)' }
  return clash ? { kind: 'replace', existing: clash } : { kind: 'import' }
}

/** The modes that were left out, grouped by why (the Astera tube has 55 left out for one reason). */
export function groupSkipped(skipped: OflReport['skipped']): { reason: string; modes: string[] }[] {
  const groups: { reason: string; modes: string[] }[] = []
  for (const { mode, reason } of skipped) {
    const group = groups.find((g) => g.reason === reason)
    if (group) group.modes.push(mode)
    else groups.push({ reason, modes: [mode] })
  }
  return groups
}

/** How a clash is put to the user: what would be overwritten. */
export function clashText(clash: Existing): string {
  const where = clash.origin === 'default' ? 'It comes with the app (replacing it makes your own copy; Reset brings the original back).' : clash.origin === 'modified' ? 'It comes with the app and you changed it.' : 'It is one of your own types.'
  const used = clash.used_in.length ? ` Used in ${clash.used_in.join(', ')}: a fixture whose mode is gone moves to the new default mode.` : ''
  return `A fixture type named “${clash.name}” exists. ${where}${used}`
}

/** The fixtures of one manufacturer that match what was typed: every word is in the key. */
export function filterKeys(keys: string[], text: string): string[] {
  const words = text.toLowerCase().split(/[\s/]+/).filter(Boolean)
  return keys.filter((k) => words.every((w) => k.includes(w)))
}

// ---- the menu's File → Import Fixture → Open Fixture Library…: the page that has the dialog opens it. The menu may have to switch
// to the Fixtures page first (it mounts later), so the request waits a moment for it.
const WAIT_MS = 15_000
let requested = 0
const listeners = new Set<() => void>()

export function requestOflImport(now = Date.now()): void {
  requested = now
  listeners.forEach((f) => f())
}

/** true once per request, and only while it is fresh (a request the Fixtures page never took, e.g. after "unsaved changes? Stay", dies). */
export function takeOflImportRequest(now = Date.now()): boolean {
  const fresh = requested > 0 && now - requested < WAIT_MS
  requested = 0
  return fresh
}

export function onOflImportRequest(listener: () => void): () => void {
  listeners.add(listener)
  return () => void listeners.delete(listener)
}
