import { describe, expect, it } from 'vitest'
import { CONNECTION_TABS, DESK_TABS } from './pages'
import { rememberTab, rememberedTab, stepTab, subTabKey } from './subTabs'

const key = (k: string, mods: Partial<{ metaKey: boolean; ctrlKey: boolean; altKey: boolean }> = {}) => ({ key: k, metaKey: false, ctrlKey: false, altKey: false, ...mods })

describe('stepTab', () => {
  it('steps to the next and the previous tab', () => {
    expect(stepTab(CONNECTION_TABS, 'midi', 1)).toBe('dmx')
    expect(stepTab(CONNECTION_TABS, 'midi', -1)).toBe('audio')
  })

  it('wraps around at both ends', () => {
    expect(stepTab(CONNECTION_TABS, 'serial', 1)).toBe('audio')
    expect(stepTab(CONNECTION_TABS, 'audio', -1)).toBe('serial')
  })

  it('on the Control Desk, Routes is one step back from the first channels and one on from the last ones', () => {
    expect(stepTab(DESK_TABS, 'ch-0', -1)).toBe('routes')
    expect(stepTab(DESK_TABS, 'ch-7', 1)).toBe('routes')
    expect(stepTab(DESK_TABS, 'routes', 1)).toBe('ch-0')
  })

  it('starts at the first tab when the current one is no tab', () => {
    expect(stepTab<string>(CONNECTION_TABS, 'monitor', 1)).toBe('audio')
  })
})

describe('subTabKey', () => {
  it('Q is the previous tab, E the next, in either case', () => {
    expect(subTabKey(key('q'), false)).toBe(-1)
    expect(subTabKey(key('E'), false)).toBe(1)
  })

  it('does nothing while typing or with a modifier (⌘Q quits, Ctrl+E is the browser’s)', () => {
    expect(subTabKey(key('e'), true)).toBeNull()
    expect(subTabKey(key('q', { metaKey: true }), false)).toBeNull()
    expect(subTabKey(key('e', { ctrlKey: true }), false)).toBeNull()
    expect(subTabKey(key('e', { altKey: true }), false)).toBeNull()
  })

  it('ignores the other keys', () => {
    for (const k of ['w', 'a', 's', 'd', 'f', '1', 'Enter', 'Tab']) expect(subTabKey(key(k), false)).toBeNull()
  })
})

describe('the remembered tab', () => {
  it('is the fallback until a tab was chosen, then the chosen one, per page', () => {
    expect(rememberedTab('Test page', CONNECTION_TABS, 'audio')).toBe('audio')
    rememberTab('Test page', 'osc')
    expect(rememberedTab('Test page', CONNECTION_TABS, 'audio')).toBe('osc')
    expect(rememberedTab('Another page', CONNECTION_TABS, 'midi')).toBe('midi')
  })

  it('falls back when the remembered tab no longer exists', () => {
    rememberTab('Old page', 'monitor')
    expect(rememberedTab('Old page', CONNECTION_TABS, 'audio')).toBe('audio')
  })
})
