import { describe, expect, it } from 'vitest'
import { NAME_RULE, actionFor, clashOf, clashText, filterKeys, groupSkipped, makersOf, modelsOf, onImportRequest, requestImport, takeImportRequest, type Converted, type QlcListed } from './fixtureImport'

const converted = (type: Converted['type'] = { name: '', description: '', transport: 'dmx', modes: [], default_mode: '', gamma: 1, strobo_color: { h: 0, s: 0, b: 1 } }): Converted => ({
  name: 'Stairville LED Bar 240-8',
  type,
  existing: null,
  report: { fixture: { name: 'LED Bar 240/8' }, modes: [], skipped: [], assumptions: [], notes: [], manual: [], check: '' },
})

describe('the clash with an existing type name', () => {
  const types = { 'Stairville LED Bar 240-8': {}, 'My Bar': {} }
  const origins = { 'Stairville LED Bar 240-8': 'default' as const }
  const usage = { 'My Bar': ['Show'] }
  it('is found in any letter case, with what it is and where it is used', () => {
    expect(clashOf('stairville led bar 240-8 ', types, origins, usage)).toEqual({ name: 'Stairville LED Bar 240-8', origin: 'default', used_in: [] })
    expect(clashOf('MY BAR', types, origins, usage)).toEqual({ name: 'My Bar', origin: 'user', used_in: ['Show'] })
  })
  it('a free name has none', () => expect(clashOf('Other Bar', types, origins, usage)).toBeNull())
  it('says what would be overwritten', () => {
    expect(clashText({ name: 'A', origin: 'default', used_in: [] })).toContain('comes with the app')
    expect(clashText({ name: 'A', origin: 'user', used_in: ['Show', 'Gig'] })).toMatch(/one of your own types.*Used in Show, Gig/)
  })
})

describe('the main button', () => {
  const existing = { name: 'A', origin: 'user' as const, used_in: [] }
  it('imports under a free name', () => expect(actionFor('New', converted(), null)).toEqual({ kind: 'import' }))
  it('asks to replace when the name is taken (the clash panel names what is overwritten)', () => expect(actionFor('A', converted(), existing)).toEqual({ kind: 'replace', existing }))
  it('is blocked for a bad name or when nothing could be converted', () => {
    expect(actionFor('a/b', converted(), null).kind).toBe('blocked')
    expect(actionFor('', converted(), null).kind).toBe('blocked')
    expect(actionFor('Fine', converted(null), null)).toMatchObject({ kind: 'blocked', why: expect.stringContaining('none of this fixture') })
    expect(actionFor('Fine', null, null).kind).toBe('blocked')
  })
  it('names are file names, like a rig’s', () => {
    for (const ok of ['LED Bar 240-8', 'a', 'x'.repeat(64), 'Q-Spot 40.2_b']) expect(NAME_RULE.test(ok)).toBe(true)
    for (const bad of ['', ' x', '-x', 'a/b', 'x'.repeat(65), 'é']) expect(NAME_RULE.test(bad)).toBe(false)
  })
})

describe('the report', () => {
  it('groups the modes that were left out by their reason', () => {
    const skipped = [
      { mode: '2: A', reason: 'effects', detail: '' },
      { mode: '15: Effect', reason: 'effects', detail: '' },
      { mode: 'Pix', reason: 'per pixel', detail: '' },
    ]
    expect(groupSkipped(skipped)).toEqual([
      { reason: 'effects', modes: ['2: A', '15: Effect'] },
      { reason: 'per pixel', modes: ['Pix'] },
    ])
  })
})

describe('the fixture filter', () => {
  const keys = ['led-bar-240-8', 'led-flood-panel-150', 'sonicpulse-led-bar-10']
  it('every word has to be in the key', () => {
    expect(filterKeys(keys, 'bar 240')).toEqual(['led-bar-240-8'])
    expect(filterKeys(keys, 'LED')).toEqual(keys)
    expect(filterKeys(keys, 'nothing')).toEqual([])
    expect(filterKeys(keys, '')).toEqual(keys)
  })
})

describe('the menu’s request for the dialog', () => {
  it('is taken once, when it is fresh, with the kind of dialog', () => {
    requestImport('ofl', 1000)
    expect(takeImportRequest(2000)).toBe('ofl')
    expect(takeImportRequest(2000)).toBeNull()
    requestImport('qlc', 1000)
    expect(takeImportRequest(2000)).toBe('qlc')
  })
  it('dies when nobody took it (e.g. the page change was refused)', () => {
    requestImport('qlc', 1000)
    expect(takeImportRequest(1000 + 20_000)).toBeNull()
  })
  it('tells a page that is already shown', () => {
    let heard = 0
    const stop = onImportRequest(() => heard++)
    requestImport('ofl')
    stop()
    requestImport('qlc')
    takeImportRequest()
    expect(heard).toBe(1)
  })
})

describe('the list of QLC+’s own fixtures', () => {
  const f = (manufacturer: string, model: string, type = 'Color Changer', folder = 0): QlcListed => ({ folder, file: `${manufacturer}-${model}.qxf`, manufacturer, model, type })
  const fixtures = [f('Stairville', 'LED Bar 240/8', 'LED Bar (Beams)'), f('Stairville', 'LED Bar 10', 'LED Bar (Beams)', 1), f('american dj', 'Mega Par'), f('Cameo', 'Q-Spot 40')]
  it('has the manufacturers by name with their counts, narrowed by every word', () => {
    expect(makersOf(fixtures)).toEqual([
      { name: 'american dj', count: 1 },
      { name: 'Cameo', count: 1 },
      { name: 'Stairville', count: 2 },
    ])
    expect(makersOf(fixtures, 'stair')).toEqual([{ name: 'Stairville', count: 2 }])
    expect(makersOf(fixtures, 'dj american')).toEqual([{ name: 'american dj', count: 1 }])
    expect(makersOf(fixtures, 'nobody')).toEqual([])
  })
  it('has a manufacturer’s models in natural order, narrowed by the model or the type', () => {
    expect(modelsOf(fixtures, 'Stairville').map((x) => x.model)).toEqual(['LED Bar 10', 'LED Bar 240/8'])
    expect(modelsOf(fixtures, 'Stairville', '240').map((x) => x.model)).toEqual(['LED Bar 240/8'])
    expect(modelsOf(fixtures, 'Stairville', 'beams').length).toBe(2)
    expect(modelsOf(fixtures, 'Nobody')).toEqual([])
  })
})
