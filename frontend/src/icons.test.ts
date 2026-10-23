import { describe, expect, it } from 'vitest'

/** The source of every .tsx under src. */
const SOURCES = import.meta.glob<string>(['./**/*.tsx', '!./**/*.test.tsx'], { query: '?raw', import: 'default', eager: true })

// Item 67: a section that is an input or an output says so with its arrow (components/Icon.tsx, the one icon component)
const sections = Object.entries(SOURCES).flatMap(([file, src]) =>
  [...src.matchAll(/<Section\b([\s\S]*?)>/g)].map((m) => ({ file, attrs: m[1], title: /title="([^"]+)"/.exec(m[1])?.[1] ?? '' })),
)

describe('section icons', () => {
  it('finds the sections', () => expect(sections.length).toBeGreaterThan(10))

  it('every input or output section has its arrow', () => {
    const io = sections.filter((s) => /input|output|serial|MIDI controller/i.test(s.title))
    expect(io.length).toBeGreaterThanOrEqual(9)
    const missing = io.filter((s) => !/icon="(in|out)"/.test(s.attrs)).map((s) => `${s.file}: ${s.title}`)
    expect(missing).toEqual([])
  })

  it('inputs point in, outputs point out', () => {
    const wrong = sections.filter((s) => (/input|controller/i.test(s.title) && /icon="out"/.test(s.attrs)) || (/output|serial/i.test(s.title) && /icon="in"/.test(s.attrs)))
    expect(wrong.map((s) => s.title)).toEqual([])
  })

  it('only Icon.tsx draws the icons', () => {
    const others = Object.entries(SOURCES).filter(([f, src]) => !f.endsWith('/Icon.tsx') && src.includes('ICON_PATHS'))
    expect(others.map(([f]) => f)).toEqual([])
  })
})

describe('the header', () => {
  it('has no v2 indicator any more: its status is a row of the DMX bubble (item 66)', () => {
    expect(SOURCES['./components/HeaderBubbles.tsx'] + SOURCES['./App.tsx']).not.toMatch(/label="v2"/)
    expect(SOURCES['./components/HeaderBubbles.tsx']).toMatch(/PitchPlease v2/)
  })
})
