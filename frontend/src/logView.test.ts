import { describe, expect, it } from 'vitest'
import { FOLLOW, MAX_LINES, addRecords, atBottom, clock, followAfterScroll, followAfterToggle, lastSeq, lineText, linesText, showLogPanel, toneOf, type LogRecord } from './logView'

const rec = (seq: number, level = 'INFO', msg = `line ${seq}`): LogRecord => ({ seq, t: 1_700_000_000.25, level, logger: 'pitchcontrol.test', msg })
const run = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => rec(from + i))

describe('the lines the view keeps', () => {
  it('adds a batch at the end', () => {
    expect(addRecords(run(1, 3), { records: run(4, 5) }).map((r) => r.seq)).toEqual([1, 2, 3, 4, 5])
    expect(addRecords([], { records: run(1, 2) }).map((r) => r.seq)).toEqual([1, 2])
  })
  it('keeps a bounded number of lines: the oldest go', () => {
    const lines = addRecords(run(1, 8), { records: run(9, 12) }, 10)
    expect(lines.map((r) => r.seq)).toEqual([3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    expect(addRecords([], { records: run(1, MAX_LINES + 50) }).length).toBe(MAX_LINES)
  })
  it('skips records it has (a batch that overlaps the history)', () => {
    expect(addRecords(run(1, 5), { records: run(3, 7) }).map((r) => r.seq)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })
  it('returns the same array when nothing is new (no needless render)', () => {
    const lines = run(1, 3)
    expect(addRecords(lines, { records: [] })).toBe(lines)
    expect(addRecords(lines, { records: run(2, 3) })).toBe(lines)
  })
  it('a reset (the server restarted) replaces the lines', () => {
    expect(addRecords(run(1, 50), { records: run(1, 2), reset: true }).map((r) => r.seq)).toEqual([1, 2])
    expect(addRecords(run(1, 50), { records: [], reset: true })).toEqual([])
  })
  it('names the number to ask for what is newer', () => {
    expect(lastSeq([])).toBe(0)
    expect(lastSeq(run(1, 9))).toBe(9)
  })
})

describe('the colours', () => {
  it('errors red, warnings amber, info the text colour, debug dim', () => {
    expect(toneOf('ERROR')).toBe('error')
    expect(toneOf('CRITICAL')).toBe('error')
    expect(toneOf('WARNING')).toBe('warn')
    expect(toneOf('INFO')).toBe('info')
    expect(toneOf('DEBUG')).toBe('debug')
    expect(toneOf('SOMETHING')).toBe('info')
  })
})

describe('the text of a line and what Copy puts on the clipboard', () => {
  it('has the time with milliseconds, the level, the logger and the message', () => {
    expect(clock(1_700_000_000.25)).toMatch(/^\d\d:\d\d:\d\d\.250$/)
    const text = lineText(rec(1, 'WARNING', 'no such device'))
    expect(text).toMatch(/^\d\d:\d\d:\d\d\.250 WARNING pitchcontrol\.test: no such device$/)
    expect(lineText(rec(1, 'INFO'))).toContain(' INFO    pitchcontrol.test: ') // levels line up
  })
  it('joins the lines with line breaks, a traceback inside its record', () => {
    const text = linesText([rec(1, 'ERROR', 'write failed\nTraceback (most recent call last):\nValueError: x'), rec(2)])
    expect(text.split('\n')).toHaveLength(4)
    expect(text.split('\n')[1]).toBe('Traceback (most recent call last):')
    expect(linesText([])).toBe('')
  })
})

describe('auto-scroll', () => {
  const view = (scrollTop: number) => ({ scrollTop, scrollHeight: 1000, clientHeight: 300 })
  it('is at the bottom within a few pixels', () => {
    expect(atBottom(view(700))).toBe(true)
    expect(atBottom(view(697))).toBe(true)
    expect(atBottom(view(650))).toBe(false)
  })
  it('is on by default', () => expect(FOLLOW).toEqual({ auto: true, paused: false }))
  it('scrolling up pauses it and the checkbox shows that', () => {
    expect(followAfterScroll(FOLLOW, false)).toEqual({ auto: false, paused: true })
  })
  it('scrolling back to the end resumes what the scrolling paused', () => {
    const paused = followAfterScroll(FOLLOW, false)
    expect(followAfterScroll(paused, true)).toEqual(FOLLOW)
    expect(followAfterScroll(paused, false)).toBe(paused)
  })
  it('does not change while following at the end', () => expect(followAfterScroll(FOLLOW, true)).toBe(FOLLOW))
  it('the checkbox switches it off for good and on again', () => {
    const off = followAfterToggle(FOLLOW)
    expect(off).toEqual({ auto: false, paused: false })
    expect(followAfterScroll(off, true)).toBe(off) // reaching the end by hand does not undo the user's choice
    expect(followAfterToggle(off)).toEqual(FOLLOW)
    expect(followAfterToggle(followAfterScroll(FOLLOW, false))).toEqual(FOLLOW) // clicking while paused: follow again
  })
})

describe('who sees the Log panel', () => {
  it('this computer does', () => expect(showLogPanel({ local: true })).toBe(true))
  it('a phone in network mode does not (its app-info says local: false)', () => expect(showLogPanel({ local: false })).toBe(false))
  it('nobody before the answer is in', () => {
    expect(showLogPanel(null)).toBe(false)
    expect(showLogPanel(undefined)).toBe(false)
    expect(showLogPanel({})).toBe(false)
  })
})
