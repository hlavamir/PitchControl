import { useEffect, useRef } from 'react'

/**
 * How often Connections reads the device lists (audio devices, MIDI ports, controller files) while it is open
 * (item 34). The audio list is read by a short-lived child process (item 32), which takes 0.29 s in the built Mac app
 * and about 0.4 s on Windows (measured from the dev environment: a child that imports PortAudio and lists the devices,
 * an app built with PyInstaller wasn't measured on Windows). That is a fraction of a core every two seconds, and only
 * while the page is open and visible; the MIDI and controller lists are cheap. A new device shows up within a couple
 * of seconds, which is what "plug it in and it is there" needs.
 */
export const DEVICE_LIST_MS = 2000

/**
 * Calls ``load`` now and then every ``ms`` while the component is mounted: one call at a time (the next waits for the
 * last to finish), not while the browser tab is hidden, and a failing call (the engine restarting) is ignored.
 */
export function usePolling(load: () => Promise<unknown>, ms: number = DEVICE_LIST_MS) {
  const latest = useRef(load)
  latest.current = load
  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          await latest.current()
        } catch {
          // the next round tries again
        }
      }
      if (!stopped) timer = window.setTimeout(tick, ms)
    }
    timer = window.setTimeout(tick, ms)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [ms])
}

/** The previous value when the new one is the same, so that React doesn't redraw (an open dropdown would close). */
export function unchanged<T>(prev: T, next: T): T {
  return JSON.stringify(prev) === JSON.stringify(next) ? prev : next
}
