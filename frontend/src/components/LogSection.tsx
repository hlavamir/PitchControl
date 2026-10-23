import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from '../api'
import { LOG_SECTION } from '../appMenu'
import { FOLLOW, addRecords, atBottom, clock, followAfterScroll, followAfterToggle, lastSeq, linesText, toneOf, type LogBatch, type LogRecord } from '../logView'
import type { EngineConnection } from '../useEngine'
import { Section, Toggle } from './forms'

const TONE_CLASS = {
  error: 'text-log-error',
  warn: 'text-log-warn',
  info: '', // the normal text colour (the ink)
  debug: 'text-dim',
}

const Line = memo(function Line({ r }: { r: LogRecord }) {
  return (
    <div className={`whitespace-pre-wrap break-words ${TONE_CLASS[toneOf(r.level)]}`}>
      <span className="opacity-70">{clock(r.t)}</span> {r.level.padEnd(7)} {r.logger}: {r.msg}
    </div>
  )
})

/**
 * Settings → Log (item 56): the log of this run, read-only. The history comes from ``GET /api/log``, the new records
 * over the engine's websocket (batched by the server). Errors are red, warnings amber, info in the text colour, debug
 * dim. The view follows the end of the log unless the checkbox is off; scrolling up by hand switches it off (the
 * checkbox shows that), scrolling back to the end switches it on again. Settings shows it on this computer only (not on a
 * device on the network, whose app-info says ``local: false``): the log carries paths and device names, so such a device
 * gets neither the panel nor the stream (the server refuses it as well).
 */
export function LogSection({ index, engine }: { index: string; engine: EngineConnection }) {
  const [lines, setLines] = useState<LogRecord[]>([])
  const [follow, setFollow] = useState(FOLLOW)
  const [copied, setCopied] = useState(false)
  const linesRef = useRef<LogRecord[]>([]) // what the view has, for asking the server for newer records
  const viewRef = useRef<HTMLDivElement>(null)

  const { subscribeLog } = engine
  useEffect(() => {
    let alive = true
    let unsubscribe: (() => void) | undefined
    const apply = (batch: LogBatch) => {
      if (!alive) return
      const next = addRecords(linesRef.current, batch)
      linesRef.current = next
      setLines(next)
    }
    // the history first, then what follows it live (the server sends the records newer than the last one the view has)
    api
      .get<LogBatch>('/api/log')
      .then(apply)
      .catch(() => undefined)
      .then(() => {
        if (alive) unsubscribe = subscribeLog(() => lastSeq(linesRef.current), apply)
      })
    return () => {
      alive = false
      unsubscribe?.()
    }
  }, [subscribeLog])

  // follow the end after each change of the lines
  useLayoutEffect(() => {
    const el = viewRef.current
    if (el && follow.auto) el.scrollTop = el.scrollHeight
  }, [lines, follow.auto])

  const onScroll = useCallback(() => {
    const el = viewRef.current
    if (el) setFollow((f) => followAfterScroll(f, atBottom(el)))
  }, [])

  const copy = () => {
    void navigator.clipboard?.writeText(linesText(lines)).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <Section
      id={LOG_SECTION}
      index={index}
      title="Log"
      right={`${lines.length} line${lines.length === 1 ? '' : 's'} · this run`}
      tip="The log of this run: what the app and the engine report. Errors are red, warnings amber, debug lines dim. Attach it to a bug report with Copy, or the file (File → Open logs folder)"
      className="min-h-0 flex-1" // takes what is left of its column, so the page fits the window
    >
      <div className="mb-2 flex flex-none items-center justify-between gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-[12px]" data-tip="Keep the view at the newest line. Scrolling up stops it, and so does switching it off; scroll back to the end or switch it on to follow again">
          <Toggle checked={follow.auto} onChange={() => setFollow(followAfterToggle)} label="Auto-scroll" />
          {!follow.auto && follow.paused && <span className="lbl text-[10px] text-dim">paused: you scrolled up</span>}
        </label>
        <button
          className="lbl glow-hover h-8 border border-edge px-3 text-[11px]"
          data-hint="button"
          data-tip="Copy all the lines of the view as text, for a bug report"
          disabled={!lines.length}
          onClick={copy}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <div
        ref={viewRef}
        onScroll={onScroll}
        role="log"
        aria-label="Log of this run"
        data-hint="info"
        className="max-h-[340px] min-h-[220px] flex-1 overflow-auto wide:max-h-none border border-edge bg-ground p-2 font-mono text-[12px] leading-[1.45] select-text"
      >
        {lines.length ? lines.map((r) => <Line key={r.seq} r={r} />) : <span className="text-dim">Nothing logged yet.</span>}
      </div>
    </Section>
  )
}
