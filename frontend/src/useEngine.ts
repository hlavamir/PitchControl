import { useCallback, useEffect, useRef, useState } from 'react'
import type { AudioFrame, EngineState } from './api'
import type { LogBatch } from './logView'
import type { PerfBatch } from './bubbles'

export const PREVIEW_SIZE = 256

export interface EngineConnection {
  state: EngineState | null
  preview: Uint8Array | null
  connected: boolean
  setMacro: (name: string, value: number) => void
  toggleMacro: (name: string) => void
  setDeferred: (name: string, value: number) => void // hue/saturation from the keyboard: applied once keys rest
  cancelPending: (name: string) => void
  setOverride: (universe: number, channel: number, value: number | null) => void // Control Desk; null releases
  /**
   * The log view (Settings → Log, item 56) asks for the records of this run that are newer than ``after()`` and gets them,
   * batched, until it unsubscribes (the returned function). Asked again after a reconnect. One viewer at a time; this
   * computer only: the server sends a device on the network nothing.
   */
  subscribeLog: (after: () => number, onBatch: (batch: LogBatch) => void) => () => void
  /**
   * The FPS bubble (item 66) asks for the engine's frame times: the last 10 s, then what is new every 0.25 s, until it
   * unsubscribes (the returned function). Asked again after a reconnect. One subscriber at a time.
   */
  subscribePerf: (onBatch: (batch: PerfBatch) => void) => () => void
  /**
   * The band displays (item 81) ask for the audio bands once per engine frame, until they unsubscribe (the returned
   * function). Several displays may be mounted at once: the server is asked while at least one listens, and asked again
   * after a reconnect. The frames go to the listeners only, not into ``state``: 40 renders a second of the whole app.
   */
  subscribeAudio: (onFrame: (frame: AudioFrame) => void) => () => void
}

/**
 * Live connection to the engine: JSON state + binary 256×256 preview, reconnecting automatically.
 * ``preview: false`` asks for the state only (the phone layout has no scene preview: less wifi, less rendering).
 */
export function useEngine({ preview: withPreview = true }: { preview?: boolean } = {}): EngineConnection {
  const [state, setState] = useState<EngineState | null>(null)
  const [preview, setPreview] = useState<Uint8Array | null>(null)
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const logRef = useRef<{ after: () => number; onBatch: (batch: LogBatch) => void } | null>(null)
  const perfRef = useRef<{ onBatch: (batch: PerfBatch) => void } | null>(null)
  const audioRef = useRef<Set<(frame: AudioFrame) => void>>(new Set())

  useEffect(() => {
    let closed = false
    let retry: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws${withPreview ? '' : '?preview=0'}`)
      ws.binaryType = 'arraybuffer'
      socketRef.current = ws
      ws.onopen = () => {
        setConnected(true)
        const log = logRef.current
        if (log) ws.send(JSON.stringify({ type: 'log_subscribe', after: log.after() })) // the view stays open over a reconnect
        if (perfRef.current) ws.send(JSON.stringify({ type: 'perf_subscribe' }))
        if (audioRef.current.size) ws.send(JSON.stringify({ type: 'audio_subscribe' }))
      }
      ws.onmessage = (ev) => {
        if (typeof ev.data !== 'string') return setPreview(new Uint8Array(ev.data))
        const msg = JSON.parse(ev.data)
        if (msg.type === 'log') logRef.current?.onBatch(msg) // the engine state has no "type"
        else if (msg.type === 'perf') perfRef.current?.onBatch(msg)
        else if (msg.type === 'audio') audioRef.current.forEach((listener) => listener(msg))
        else setState({ ...msg, received_at: performance.now() })
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = window.setTimeout(connect, 1000)
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(retry)
      socketRef.current?.close()
    }
  }, [withPreview])

  const send = useCallback((msg: object) => {
    const ws = socketRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }, [])

  const setMacro = useCallback((name: string, value: number) => send({ type: 'macro', name, value }), [send])
  const toggleMacro = useCallback((name: string) => send({ type: 'toggle', name }), [send])
  const setDeferred = useCallback((name: string, value: number) => send({ type: 'macro_deferred', name, value }), [send])
  const cancelPending = useCallback((name: string) => send({ type: 'cancel_pending', name }), [send])

  const setOverride = useCallback(
    (universe: number, channel: number, value: number | null) => send({ type: 'override', universe, channel, value }),
    [send],
  )

  const subscribeLog = useCallback(
    (after: () => number, onBatch: (batch: LogBatch) => void) => {
      const sub = { after, onBatch }
      logRef.current = sub
      send({ type: 'log_subscribe', after: after() }) // not open yet: onopen asks
      return () => {
        if (logRef.current !== sub) return
        logRef.current = null
        send({ type: 'log_unsubscribe' })
      }
    },
    [send],
  )

  const subscribePerf = useCallback(
    (onBatch: (batch: PerfBatch) => void) => {
      const sub = { onBatch }
      perfRef.current = sub
      send({ type: 'perf_subscribe' }) // not open yet: onopen asks
      return () => {
        if (perfRef.current !== sub) return
        perfRef.current = null
        send({ type: 'perf_unsubscribe' })
      }
    },
    [send],
  )

  const subscribeAudio = useCallback(
    (onFrame: (frame: AudioFrame) => void) => {
      const listeners = audioRef.current
      listeners.add(onFrame)
      if (listeners.size === 1) send({ type: 'audio_subscribe' }) // not open yet: onopen asks
      return () => {
        if (!listeners.delete(onFrame) || listeners.size > 0) return
        send({ type: 'audio_unsubscribe' })
      }
    },
    [send],
  )

  return { state, preview, connected, setMacro, toggleMacro, setDeferred, cancelPending, setOverride, subscribeLog, subscribePerf, subscribeAudio }
}
