import { describe, expect, it } from 'vitest'
import { PHONE_MAX, isPhoneSize, pickLayout } from './phone'

describe('isPhoneSize', () => {
  it('takes the short side of the screen, in portrait and in landscape', () => {
    for (const [w, h] of [[360, 740], [390, 844], [430, 932], [844, 390], [320, 568]]) expect(isPhoneSize(w, h)).toBe(true)
  })

  it('leaves an iPad, a laptop and a monitor out', () => {
    for (const [w, h] of [[744, 1133], [768, 1024], [1024, 768], [1512, 982], [1920, 1080], [PHONE_MAX, 1000]]) expect(isPhoneSize(w, h)).toBe(false)
  })
})

describe('pickLayout', () => {
  it('gives a phone the phone layout, unless it asked for the full UI', () => {
    expect(pickLayout(390, 844, null)).toBe('phone')
    expect(pickLayout(390, 844, 'full')).toBe('full')
  })

  it('always gives the laptop the full UI', () => {
    expect(pickLayout(1512, 982, null)).toBe('full')
    expect(pickLayout(1512, 982, 'phone')).toBe('full')
  })
})
