import { describe, expect, it } from 'vitest'
import { PAGES, keyOfPage, pageOfHash, pageOfKey } from './pages'

describe('the page keys (item 60)', () => {
  it('1 to 9 open the nine pages in the order of the page row', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8, 9].map(pageOfKey)).toEqual(['General', 'Dimmers', 'Fixtures', 'Rig', 'Connections', 'Fog', 'Control Desk', 'Settings', 'Help'])
  })

  it('0 opens no page', () => {
    expect(pageOfKey(0)).toBeNull()
  })

  it('the key shown on each tab opens that page', () => {
    for (const p of PAGES) expect(pageOfKey(keyOfPage(p))).toBe(p)
  })

  it('Inputs and Outputs are gone, Connections is there', () => {
    expect(PAGES).not.toContain('Inputs')
    expect(PAGES).not.toContain('Outputs')
    expect(keyOfPage('Connections')).toBe(5)
  })
})

describe('pageOfHash', () => {
  it('reads a page, and a Connections tab after a slash', () => {
    expect(pageOfHash('#Fog')).toEqual({ page: 'Fog' })
    expect(pageOfHash('#Control%20Desk')).toEqual({ page: 'Control Desk' })
    expect(pageOfHash('#Connections/midi')).toEqual({ page: 'Connections', tab: 'midi' })
    expect(pageOfHash('#Connections/nothing')).toEqual({ page: 'Connections' })
  })

  it('opens the matching tab for a bookmark of a page that became one', () => {
    expect(pageOfHash('#Inputs')).toEqual({ page: 'Connections', tab: 'audio' })
    expect(pageOfHash('#Outputs')).toEqual({ page: 'Connections', tab: 'dmx' })
    expect(pageOfHash('#Output')).toEqual({ page: 'Connections', tab: 'dmx' })
  })

  it('falls back to General', () => {
    expect(pageOfHash('')).toEqual({ page: 'General' })
    expect(pageOfHash('#Nowhere')).toEqual({ page: 'General' })
  })
})
