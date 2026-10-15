import { describe, expect, it } from 'vitest'
import type { IoStatus } from './api'
import { audioReconnectLine } from './audioReconnect'

const at = (h: number, m: number, s: number) => new Date(2026, 9, 15, h, m, s).getTime() / 1000
const status = (reconnect: IoStatus['reconnect']): IoStatus => ({ error: null, reconnect })

describe('audioReconnectLine', () => {
  it('says nothing before a drop, or while the input is still lost', () => {
    expect(audioReconnectLine(null)).toBeNull()
    expect(audioReconnectLine(status(null))).toBeNull()
    expect(audioReconnectLine(status({ lost: at(21, 13, 58), back: null }))).toBeNull()
  })

  it('a drop that came back', () => {
    const line = audioReconnectLine(
      status({ lost: at(21, 13, 58), back: at(21, 14, 5), lost_device: 'Komplete Audio 6', back_device: 'Komplete Audio 6' }),
    )
    expect(line).toBe('lost 21:13:58 · back 21:14:05')
  })

  it('a device that was missing since the start is "connected", not "back"', () => {
    expect(audioReconnectLine(status({ lost: null, back: at(21, 14, 5) }))).toBe('not found at start · connected 21:14:05')
  })

  it('names both devices when the input ended up on another one', () => {
    const line = audioReconnectLine(
      status({ lost: at(21, 13, 58), back: at(21, 13, 59), lost_device: 'Komplete Audio 6', back_device: 'MacBook Pro Microphone' }),
    )
    expect(line).toBe("lost 'Komplete Audio 6' 21:13:58 · now 'MacBook Pro Microphone' 21:13:59")
  })

  it('pads the clock', () => {
    expect(audioReconnectLine(status({ lost: at(9, 5, 3), back: at(9, 5, 9) }))).toBe('lost 09:05:03 · back 09:05:09')
  })
})
