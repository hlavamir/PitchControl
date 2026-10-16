/**
 * What the MIDI port row says about the port saved in Settings. The system's list names a port the way the system
 * does; on Windows (WinMM) every name ends in an index that changes when another device comes or goes
 * ("LCXL3 1 MIDI In 0" → "… 1"). The engine finds the port under its new name (item 33), so a saved name missing
 * from the list isn't "not found" while the input is open under another name.
 */
export function savedPortState(
  saved: string,
  listed: string[],
  input: { port?: string | null; wanted?: string } | null | undefined,
): { state: 'listed' } | { state: 'renamed'; now: string } | { state: 'missing' } {
  if (listed.includes(saved)) return { state: 'listed' }
  if (input?.port && input.wanted === saved) return { state: 'renamed', now: input.port }
  return { state: 'missing' }
}
