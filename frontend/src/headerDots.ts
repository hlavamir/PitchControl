import type { EngineState } from './api'
import { QUIET_AFTER_S } from './liveInput'

// What the header's DMX and Art-Net dots show (item 86): they light for the inputs too, not only for the outputs. The
// look is StatusDot's: ok true = filled, null = hollow, false = crossed.

type Io = EngineState['io'] | undefined

export interface Dot {
  ok: boolean | null
  label: string
  error: string | null
  tip: string
}

/** True while the DMX input is receiving: enabled, connected and a packet within the last 2 s. */
export function dmxInputActive(io: Io): boolean {
  const d = io?.live_input?.dmx
  return Boolean(d?.enabled && d.connected && d.age != null && d.age < QUIET_AFTER_S)
}

/** True while any Art-Net input universe got a packet within the last 2 s. */
export function artnetInputActive(io: Io): boolean {
  const a = io?.live_input?.artnet
  return Boolean(a?.enabled && a.universes?.some((u) => u.age < QUIET_AFTER_S))
}

/** The DMX dots: one per USB DMX output interface, and the first also lights for the DMX input (one dot per output
 * keeps each interface readable; the input is one source, so it joins the first dot instead of adding a dot or merging
 * them all). With no output interface the input has the one dot, hollow while it is off, quiet or just not connected. */
export function dmxDots(io: Io): Dot[] {
  const outputs = io?.outputs?.enttec ?? []
  const input = io?.live_input?.dmx
  const receiving = dmxInputActive(io)
  const inputError = input?.enabled ? (input.error ?? null) : null
  const inTip = 'USB DMX input: filled = receiving (last 2 s)'
  if (outputs.length === 0) {
    if (!input?.enabled) return [{ ok: null, label: 'dmx', error: null, tip: 'No USB DMX interface configured. Click: Connections → DMX & Art-Net' }]
    return [{ ok: receiving ? true : inputError ? false : null, label: 'dmx', error: receiving ? null : inputError, tip: `${inTip}, hollow = quiet or off, crossed = error. Click: Connections → DMX & Art-Net` }]
  }
  return outputs.map((e, i) => {
    const first = i === 0
    const lit = Boolean(e?.connected) || (first && receiving)
    const ok = lit ? true : e || (first && inputError) ? false : null
    const error = lit ? null : (e?.error ?? (first ? inputError : null))
    const tip = first
      ? `USB DMX interface 1 and input: filled = connected or receiving (last 2 s), hollow = off, crossed = error. Click: Connections → DMX & Art-Net`
      : `USB DMX interface ${i + 1}: filled = connected, hollow = off, crossed = error. Click: Connections → DMX & Art-Net`
    return { ok, label: outputs.length > 1 ? `dmx ${i + 1}` : 'dmx', error, tip }
  })
}

/** The Art-Net dot: filled while the output is connected or an input universe is receiving; the error is the output's,
 * else the input's. */
export function artnetDot(io: Io): Dot {
  const out = io?.outputs?.artnet ?? null
  const input = io?.live_input?.artnet
  const lit = Boolean(out?.connected) || artnetInputActive(io)
  const inputError = input?.enabled ? (input.error ?? null) : null
  const error = lit ? null : (out?.error ?? inputError)
  const ok = lit ? true : out || inputError ? false : null
  return { ok, label: 'art-net', error, tip: 'Art-Net: filled = sending or receiving (last 2 s), hollow = off, crossed = error. Click: Connections → DMX & Art-Net' }
}
