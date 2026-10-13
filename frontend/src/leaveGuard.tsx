import { createContext, useContext, useEffect, useRef } from 'react'

// Pages that keep edits in a local draft (Inputs, Outputs, Fog, the MIDI mapping) register here, so that
// changing the page asks what to do with unsaved edits instead of silently dropping them.

export interface Guard {
  label: string
  dirty: () => boolean
  /** true when saved (false: it failed, stay on the page) */
  save: () => Promise<boolean | void>
}

export interface LeaveGuards {
  register: (guard: Guard) => () => void
}

export const LeaveGuardContext = createContext<LeaveGuards | null>(null)

export function useLeaveGuard(label: string, dirty: boolean, save: () => Promise<boolean | void>) {
  const guards = useContext(LeaveGuardContext)
  const latest = useRef({ dirty, save })
  useEffect(() => {
    latest.current = { dirty, save }
  })
  useEffect(() => guards?.register({ label, dirty: () => latest.current.dirty, save: () => latest.current.save() }), [guards, label])
}
