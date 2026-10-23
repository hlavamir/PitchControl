import { describe, expect, it } from 'vitest'

/** The source of every .tsx under src (the components and pages draw the UI). */
const SOURCES = import.meta.glob<string>(['./**/*.tsx', '!./**/*.test.tsx'], { query: '?raw', import: 'default', eager: true })

// Controls the system draws in its own style (the macOS checkbox is blue and round, a datalist opens the system's list,
// a radio button, colour or date input is the system's too). The app uses Toggle, Check and its own buttons instead
// (components/forms.tsx); a <select> is styled in index.css and only its opened list is the system's.
const NATIVE = [
  [/type=["']checkbox["']/, 'a native checkbox (use Toggle or Check from components/forms.tsx)'],
  [/type=["']radio["']/, 'a native radio button (use a row of buttons)'],
  [/type=["'](color|date|time|datetime-local|month|week|range)["']/, 'a native colour / date / range input'],
  [/<datalist/, 'a datalist (the system draws its list)'],
  [/<progress|<meter/, 'a native progress / meter bar'],
] as const

describe('no native-looking form controls', () => {
  const files = Object.entries(SOURCES)
  it('finds the sources', () => expect(files.length).toBeGreaterThan(10))
  for (const [re, what] of NATIVE) {
    it(`no ${what}`, () => {
      const hits = files.filter(([, src]) => re.test(src)).map(([f]) => f)
      expect(hits).toEqual([])
    })
  }
})
