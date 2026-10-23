import { createContext, useContext, useEffect, useRef } from 'react'

// Pages that keep edits in a local draft (Connections, Fog, the MIDI mapping) register here, so that
// changing the page asks what to do with unsaved edits instead of silently dropping them. The menu bar's Save (item 52)
// saves what is registered here: those drafts, and the pages whose edits are live but not written yet (Fixtures, Rig),
// which register with ``leave: false`` (leaving them keeps the edits, so nothing is asked).

export interface Guard {
  label: string
  dirty: () => boolean
  /** true when saved (false: it failed, stay on the page) */
  save: () => Promise<boolean | void>
  /** false: only for the menu's Save; leaving the page doesn't ask and the quit guard isn't told */
  leave?: boolean
}

export interface LeaveGuards {
  register: (guard: Guard) => () => void
}

export const LeaveGuardContext = createContext<LeaveGuards | null>(null)

export function useLeaveGuard(label: string, dirty: boolean, save: () => Promise<boolean | void>, leave = true) {
  const guards = useContext(LeaveGuardContext)
  const latest = useRef({ dirty, save })
  useEffect(() => {
    latest.current = { dirty, save }
  })
  useEffect(() => guards?.register({ label, dirty: () => latest.current.dirty, save: () => latest.current.save(), leave }), [guards, label, leave])
}

/** A page's Save button for the menu bar's Save, where leaving the page keeps the edits (Fixtures, Rig). */
export function useSaveAction(label: string, dirty: boolean, save: () => Promise<boolean | void>) {
  useLeaveGuard(label, dirty, save, false)
}
