import { describe, expect, it } from 'vitest'
import type { FixtureType } from './api'
import { copyOfLastMode, edited, slotOfKind } from './fixtureEdit'
import asteraText from '../../config/fixtures/types/Astera FP1 Titan Tube.json?raw'
import bar from '../../config/fixtures/types/Stairville LED Bar 240-8.json?raw'

// A type as the app ships it: imported from the Open Fixture Library, with the original data kept (item 53). The Fixtures page
// loads it, edits it and PUTs it back; what it doesn't edit must come back as it was.
const shipped = (name: string, text: string): FixtureType => ({ ...JSON.parse(text), name })
const wire = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) // api.put / api.get: JSON both ways

const KEPT = ['shortName', 'categories', 'meta', 'links', 'physical', 'matrix', 'availableChannels', 'templateChannels', 'source', 'ofl_modes']

describe('the kept data of an imported type survives the Fixtures page', () => {
  const type = shipped('Stairville LED Bar 240-8', bar)
  const keptOf = (t: FixtureType) => Object.fromEntries(KEPT.map((k) => [k, t[k]]))

  it('the shipped type has it', () => {
    for (const k of ['categories', 'links', 'physical', 'availableChannels', 'source', 'ofl_modes']) expect(type[k], k).toBeDefined()
    expect(type.modes.every((m) => typeof m.ofl_mode === 'string')).toBe(true)
  })

  it('an edit of the page (a value, a name, the gamma, a changed kind) leaves it alone', () => {
    const next = edited(type, (x) => {
      x.gamma = 2.2
      x.description = 'my words'
      x.modes[0].name = 'Renamed'
      x.modes[0].description = 'edited'
      x.modes[0].channels[0] = slotOfKind(x.modes[0].channels[0], 'macro', 'Dimmer 01')
      x.default_mode = x.modes[1].id
    })
    const back = wire(next)
    expect(keptOf(back)).toEqual(keptOf(type))
    expect(back.gamma).toBe(2.2)
    expect(back.modes[0].ofl_mode).toBe(type.modes[0].ofl_mode) // a renamed mode still says which OFL mode it was
  })

  it('the original is not touched by the edit (the page edits a copy)', () => {
    const before = JSON.stringify(type)
    edited(type, (x) => {
      x.modes.splice(0, 1)
      x.links?.manual.push('https://x.example')
    })
    expect(JSON.stringify(type)).toBe(before)
  })

  it('a deleted mode leaves OFL’s own mode list as it was; a copied mode keeps its OFL mode', () => {
    const next = edited(type, (x) => {
      x.modes.push(copyOfLastMode(x.modes))
      x.modes.splice(0, 1)
    })
    expect(next.ofl_modes).toEqual(type.ofl_modes)
    const copy = next.modes[next.modes.length - 1]
    expect(copy.ofl_mode).toBe(type.modes[type.modes.length - 1].ofl_mode)
    expect(copy.name).toMatch(/ copy$/)
  })

  it('also a type with many kept modes and nulls in them', () => {
    const astera = shipped('Astera FP1 Titan Tube', asteraText)
    expect((astera.ofl_modes as unknown[]).length).toBeGreaterThan(50)
    expect(wire(edited(astera, (x) => void (x.gamma = 1.5))).ofl_modes).toEqual(astera.ofl_modes)
  })
})
