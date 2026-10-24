import { describe, expect, it } from 'vitest'
import { releaseDate, updateText, type UpdateCheck } from './updateCheck'

const base: UpdateCheck = { status: 'latest', current: '1.8.3', latest: '1.8.3', published: '2026-10-01T08:00:00Z', notes: '', url: null, page: null, error: null }

describe('updateText', () => {
  it('says the app is up to date', () => {
    expect(updateText(base)).toBe('PitchControl 1.8.3 is the latest version.')
  })

  it('names the new version and its date', () => {
    expect(updateText({ ...base, status: 'newer', latest: '1.9.0', published: '2026-11-01T23:30:00Z' })).toBe('PitchControl 1.9.0 is available (released 2026-11-01).')
  })

  it('leaves the date out when GitHub gave none', () => {
    expect(updateText({ ...base, status: 'newer', latest: '1.9.0', published: null })).toBe('PitchControl 1.9.0 is available.')
  })

  it("gives the reason when GitHub can't be reached", () => {
    expect(updateText({ ...base, status: 'offline', error: 'no answer in time' })).toBe("Couldn't reach GitHub: no answer in time.")
    expect(updateText({ ...base, status: 'offline', error: null })).toBe("Couldn't reach GitHub: no answer.")
  })
})

describe('releaseDate', () => {
  it('keeps the date part only', () => {
    expect(releaseDate('2026-11-01T10:00:00Z')).toBe('2026-11-01')
    expect(releaseDate('garbage')).toBe('')
    expect(releaseDate(null)).toBe('')
  })
})
