import type { ChannelMode, FixtureType } from './api'

/** An id for a new mode from its name ("6CH" → "6ch"), unique among the type's modes; kept when the mode is renamed. */
export function newModeId(modes: ChannelMode[], name: string): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'mode'
  let id = base
  for (let n = 2; modes.some((m) => m.id === id); n++) id = `${base}-${n}`
  return id
}

/** Another mode of the type has the same name (ignoring case and spaces at the ends). */
export function hasSameName(modes: ChannelMode[], index: number): boolean {
  const name = modes[index].name.trim().toLowerCase()
  return modes.some((m, i) => i !== index && m.name.trim().toLowerCase() === name)
}

/** The fixtures of a rig that run in a mode of a type: their own mode, or, with none, the type's default mode. */
export function fixturesInMode(fixtures: { name: string; type: string; mode?: string | null }[], t: FixtureType, modeId: string): string[] {
  return fixtures.filter((f) => f.type === t.name && (f.mode ? f.mode === modeId : modeId === t.default_mode)).map((f) => f.name)
}
