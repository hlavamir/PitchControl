import { describe, expect, it } from 'vitest'
import type { ChannelMode, FixtureType } from './api'
import { channelCount, modeOf } from './api'
import { fixturesInMode, hasSameName, newModeId } from './modes'

const mode = (id: string, name: string, channels: ChannelMode['channels'] = [{ pixels: 'RGB' }]): ChannelMode => ({ id, name, description: '', channels })
const spot = {
  name: 'spot',
  pixels: 2,
  default_mode: '4ch',
  modes: [mode('3ch', '3CH'), mode('4ch', '4CH', [{ pixels: 'RGBW' }]), mode('6ch', '6CH', [{ pixels: 'RGBW' }, { value: 255 }, { value: 0 }])],
} as unknown as FixtureType

describe('channel modes', () => {
  it('counts channels per mode, the pixel block times the pixel count', () => {
    expect([...spot.modes.map((m) => channelCount(spot, m.id)), channelCount(spot)]).toEqual([6, 8, 10, 8])
  })
  it('takes the default mode for none or an unknown id', () => {
    expect(modeOf(spot, '6ch').name).toBe('6CH')
    expect(modeOf(spot).id).toBe('4ch')
    expect(modeOf(spot, 'gone').id).toBe('4ch')
  })
  it('makes an id from the name that no other mode has', () => {
    expect(newModeId(spot.modes, '9 CH')).toBe('9-ch')
    expect(newModeId(spot.modes, '6CH')).toBe('6ch-2')
    expect(newModeId([...spot.modes, mode('6ch-2', 'x')], '6ch')).toBe('6ch-3')
    expect(newModeId([], '???')).toBe('mode')
  })
  it('warns about a name another mode has, ignoring case', () => {
    const modes = [mode('a', '6CH'), mode('b', ' 6ch '), mode('c', '9CH')]
    expect([0, 1, 2].map((i) => hasSameName(modes, i))).toEqual([true, true, false])
  })
  it('finds the fixtures that run in a mode, those without one in the default mode', () => {
    const rig = [
      { name: 'a', type: 'spot', mode: '6ch' },
      { name: 'b', type: 'spot' },
      { name: 'c', type: 'spot', mode: '4ch' },
      { name: 'd', type: 'other', mode: '6ch' },
    ]
    expect(fixturesInMode(rig, spot, '6ch')).toEqual(['a'])
    expect(fixturesInMode(rig, spot, '4ch')).toEqual(['b', 'c'])
    expect(fixturesInMode(rig, spot, '3ch')).toEqual([])
  })
})
