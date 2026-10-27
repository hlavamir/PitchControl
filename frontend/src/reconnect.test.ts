import { describe, expect, it } from 'vitest'
import type { IoStatus } from './api'
import { lookingLine, reconnectLine } from './reconnect'

const at = (h: number, m: number, s: number) => new Date(2026, 9, 15, h, m, s).getTime() / 1000
const status = (reconnect: IoStatus['reconnect']): IoStatus => ({ error: null, reconnect })

describe('reconnectLine', () => {
  it('says nothing before a drop, or while the input is still lost', () => {
    expect(reconnectLine(null)).toBeNull()
    expect(reconnectLine(status(null))).toBeNull()
    expect(reconnectLine(status({ lost: at(21, 13, 58), back: null }))).toBeNull()
  })

  it('a drop that came back', () => {
    const line = reconnectLine(
      status({ lost: at(21, 13, 58), back: at(21, 14, 5), lost_device: 'Komplete Audio 6', back_device: 'Komplete Audio 6' }),
    )
    expect(line).toBe('lost 21:13:58 · back 21:14:05')
  })

  it('a device that was missing since the start is "connected", not "back"', () => {
    expect(reconnectLine(status({ lost: null, back: at(21, 14, 5) }))).toBe('not found at start · connected 21:14:05')
  })

  it('names both devices when the input ended up on another one', () => {
    const line = reconnectLine(
      status({ lost: at(21, 13, 58), back: at(21, 13, 59), lost_device: 'Komplete Audio 6', back_device: 'MacBook Pro Microphone' }),
    )
    expect(line).toBe("lost 'Komplete Audio 6' 21:13:58 · now 'MacBook Pro Microphone' 21:13:59")
  })

  it('pads the clock', () => {
    expect(reconnectLine(status({ lost: at(9, 5, 3), back: at(9, 5, 9) }))).toBe('lost 09:05:03 · back 09:05:09')
  })
})

describe('lookingLine', () => {
  const dev = 'Komplete Audio 6 (ASIO)'

  it('says it is still looking in the first minute, without the button', () => {
    expect(lookingLine({ looking: true, stopped_looking: false, device_missing: true }, dev)).toEqual({
      text: "'Komplete Audio 6 (ASIO)' not found · looking for it…",
      stoppedLooking: false,
    })
  })

  it('says it stopped after a minute, with the button', () => {
    expect(lookingLine({ looking: false, stopped_looking: true, device_missing: true }, dev)).toEqual({
      text: "'Komplete Audio 6 (ASIO)' not found · stopped looking after a minute",
      stoppedLooking: true,
    })
  })

  it('says it is searching after a press, and keeps the button', () => {
    expect(lookingLine({ stopped_looking: true, device_missing: true }, dev, 'searching')).toEqual({
      text: "'Komplete Audio 6 (ASIO)' not found · searching…",
      stoppedLooking: true,
    })
  })

  it("says the device isn't running when it is listed but its stream died", () => {
    expect(lookingLine({ looking: true, device_missing: false }, dev)?.text).toBe("'Komplete Audio 6 (ASIO)' isn't running · looking for it…")
  })

  it('says what the look found', () => {
    const notFound = lookingLine({ stopped_looking: true }, dev, { found: false, at: at(21, 15, 2) })
    expect(notFound?.text).toBe("'Komplete Audio 6 (ASIO)' still not found · looked 21:15:02")
    const wontOpen = lookingLine({ stopped_looking: true }, dev, { found: true, at: at(21, 15, 2) })
    expect(wontOpen?.text).toBe("'Komplete Audio 6 (ASIO)' found, but it won't open · looked 21:15:02")
    expect(notFound?.stoppedLooking && wontOpen?.stoppedLooking).toBe(true)
  })

  it('says nothing while the device runs, with no device saved, or without a status', () => {
    expect(lookingLine({ looking: false, stopped_looking: false }, dev)).toBeNull()
    expect(lookingLine({ looking: false, stopped_looking: false }, dev, { found: true, at: at(21, 15, 2) })).toBeNull()
    expect(lookingLine({ stopped_looking: true }, null)).toBeNull()
    expect(lookingLine(null, dev)).toBeNull()
  })
})
