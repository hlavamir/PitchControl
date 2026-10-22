// The log view in Settings (item 56): the records of this run, the lines it keeps, the text it copies and the auto-scroll
// rule. Pure, so it can be tested; the panel is components/LogSection.tsx, the records come from logsetup.py's
// MemoryLogHandler (GET /api/log and, live and batched, the websocket).

export interface LogRecord {
  seq: number // counts the records of this run
  t: number // epoch seconds
  level: string // DEBUG, INFO, WARNING, ERROR, CRITICAL: a field of the record, not read from the text
  logger: string
  msg: string // with the traceback on the lines below when there is one
}

/** What the websocket sends: the records that came in since the last batch (``reset``: the server restarted, these are all of the new run). */
export interface LogBatch {
  records: LogRecord[]
  reset?: boolean
}

/** Lines the view keeps (the server keeps a bit more: logsetup.LOG_CAPACITY). */
export const MAX_LINES = 2000

/** The batch added at the end, the oldest lines dropped beyond ``max``; a reset replaces them. Records already there (by ``seq``) are skipped. */
export function addRecords(lines: LogRecord[], batch: LogBatch, max = MAX_LINES): LogRecord[] {
  const base = batch.reset ? [] : lines
  const last = base.length ? base[base.length - 1].seq : 0
  const fresh = batch.records.filter((r) => r.seq > last)
  if (!fresh.length && base === lines) return lines
  const all = fresh.length ? base.concat(fresh) : base
  return all.length > max ? all.slice(all.length - max) : all
}

/** The sequence number to ask the server for newer records than (0: everything it keeps). */
export const lastSeq = (lines: LogRecord[]): number => (lines.length ? lines[lines.length - 1].seq : 0)

export type LogTone = 'error' | 'warn' | 'info' | 'debug'

/** How a record is shown: errors red, warnings amber, info the normal text colour, debug dim. */
export function toneOf(level: string): LogTone {
  if (level === 'ERROR' || level === 'CRITICAL') return 'error'
  if (level === 'WARNING') return 'warn'
  return level === 'DEBUG' ? 'debug' : 'info'
}

const pad = (n: number, width = 2) => String(n).padStart(width, '0')

/** ``13:05:09.123`` in the computer's own time zone. */
export function clock(t: number): string {
  const d = new Date(t * 1000)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}

/** The line as the file has it: time, level, logger, message. */
export const lineText = (r: LogRecord): string => `${clock(r.t)} ${r.level.padEnd(7)} ${r.logger}: ${r.msg}`

/** All lines as text, for the Copy button (a bug report). */
export const linesText = (lines: LogRecord[]): string => lines.map(lineText).join('\n')

/** Pixels from the bottom within which the view counts as scrolled to the end. */
const AT_BOTTOM = 4

export const atBottom = (el: { scrollTop: number; scrollHeight: number; clientHeight: number }): boolean => el.scrollHeight - el.scrollTop - el.clientHeight <= AT_BOTTOM

/** ``paused``: auto-scroll was switched off by scrolling up (not by the checkbox), so scrolling back to the end switches it on again. */
export interface Follow {
  auto: boolean
  paused: boolean
}

export const FOLLOW: Follow = { auto: true, paused: false }

/** The view was scrolled by hand (or by itself to the end): up pauses auto-scroll, back at the end resumes what a scroll paused. */
export function followAfterScroll(f: Follow, atEnd: boolean): Follow {
  if (f.auto && !atEnd) return { auto: false, paused: true }
  if (!f.auto && f.paused && atEnd) return FOLLOW
  return f
}

/** The checkbox was clicked: on follows again, off stays off until it is clicked. */
export const followAfterToggle = (f: Follow): Follow => (f.auto ? { auto: false, paused: false } : FOLLOW)

/** Whether Settings shows the Log panel: on this computer only (``local`` of ``/api/app-info``). A device on the network gets no panel
 * and no stream (the server refuses it too: GET /api/log answers 403); nothing is shown until the answer is in. */
export const showLogPanel = (info: { local?: boolean } | null | undefined): boolean => info?.local === true
