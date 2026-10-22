// The edits of the Fixtures page that build a changed copy of a type. They are plain functions so that the tests can check
// what an edit leaves alone: a type may carry data the page doesn't know (the kept data of an import, item 53), and it has to
// come back unchanged when the page saves the type.

import type { ChannelMode, ChannelSlot, FixtureType } from './api'
import { newModeId } from './modes'

export type Kind = 'value' | 'macro' | 'shutter' | 'pixels'

/** A slot of another kind, keeping its name. */
export function slotOfKind(slot: ChannelSlot, kind: Kind, firstMacro: string): ChannelSlot {
  const name = slot.name ?? null
  if (kind === 'value') return { name, value: 0 }
  if (kind === 'macro') return { name, macro: firstMacro }
  if (kind === 'shutter') return { name, shutter: { open: 0, strobo: 255 } }
  return { name, pixels: 'RGB' }
}

/** The type with ``fn`` applied to a deep copy: every key the page doesn't edit is carried along as it is. */
export function edited(t: FixtureType, fn: (t: FixtureType) => void): FixtureType {
  const next = structuredClone(t)
  fn(next)
  return next
}

/** A new mode starts as a copy of the last one: a mode is mostly the one before it with a channel more or less. */
export function copyOfLastMode(modes: ChannelMode[]): ChannelMode {
  const last = modes[modes.length - 1]
  const copy = structuredClone(last)
  copy.name = `${last.name} copy`
  copy.id = newModeId(modes, copy.name)
  return copy
}
