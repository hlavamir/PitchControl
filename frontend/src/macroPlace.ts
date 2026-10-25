// Where a macro sits as a numbered control, for the MIDI mapping grid (item 96): the numbers the pages show.
import { BUTTONS, FADERS, MASKS } from './generalControls'

const pad = (n: number) => String(n).padStart(2, '0')

/** The General page's two button rows are numbered together: 01–08 the functions, 09–16 the masks (empty cells count, so the masks start at 09). */
export const buttonNumber = (name: string): number | null => {
  const f = BUTTONS.findIndex(([n]) => n === name)
  if (f >= 0) return f + 1
  const m = MASKS.findIndex(([n]) => n === name)
  return m >= 0 ? 8 + m + 1 : null
}

/** The number of a General-page fader (01–16), or null. */
export const faderNumber = (name: string): number | null => {
  const i = FADERS.indexOf(name)
  return i >= 0 ? i + 1 : null
}

/**
 * The place of a macro on its page, as the pages show it: "fader 05", "button 12", "dimmer 03" (Dimmers page),
 * "scene 4" (the load and save macros of a scene slot); null for a macro that sits nowhere as a numbered control.
 */
export function macroPlace(name: string): string | null {
  const fader = faderNumber(name)
  if (fader !== null) return `fader ${pad(fader)}`
  const button = buttonNumber(name)
  if (button !== null) return `button ${pad(button)}`
  const dimmer = /^Dimmer (\d{2})$/.exec(name)
  if (dimmer && Number(dimmer[1]) >= 1 && Number(dimmer[1]) <= 16) return `dimmer ${dimmer[1]}`
  const scene = /^Scene ([1-8]) (?:Load|Save)$/.exec(name)
  if (scene) return `scene ${scene[1]}`
  return null
}
