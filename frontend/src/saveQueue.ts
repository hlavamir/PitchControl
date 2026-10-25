// Connections writes every change at once (item 88): the PUTs go one after the other, so two quick clicks never race.

export type SaveOutcome = { ok: true } | { ok: false; error: unknown }

export interface SaveQueue<T> {
  /** Queue ``value`` to be sent; resolves with the outcome of the PUT that carried it (or the newer one that replaced it). */
  push: (value: T) => Promise<SaveOutcome>
}

interface Job<T> {
  value: T
  done: ((o: SaveOutcome) => void)[]
}

/**
 * One PUT in flight at a time. A value pushed meanwhile waits, and a newer one replaces it: every value is a whole draft
 * that already holds the earlier changes, so only the latest has to be sent. When a PUT fails, the values waiting behind
 * it are dropped with it (they hold the failed change too); the caller shows the message and loads what is saved.
 */
export function createSaveQueue<T>(send: (value: T) => Promise<unknown>): SaveQueue<T> {
  let waiting: Job<T> | null = null
  let running = false

  const run = async () => {
    running = true
    while (waiting) {
      const job = waiting
      waiting = null
      let outcome: SaveOutcome = { ok: true }
      try {
        await send(job.value)
      } catch (error) {
        outcome = { ok: false, error }
      }
      if (!outcome.ok) {
        const behind = waiting as Job<T> | null // pushed while the PUT was out
        waiting = null
        behind?.done.forEach((d) => d(outcome))
      }
      job.done.forEach((d) => d(outcome))
    }
    running = false
  }

  return {
    push(value) {
      return new Promise((resolve) => {
        waiting = { value, done: [...(waiting?.done ?? []), resolve] }
        if (!running) void run()
      })
    },
  }
}
