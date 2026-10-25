import { describe, expect, it } from 'vitest'
import { createSaveQueue } from './saveQueue'

/** A send that stays open until the test lets it finish. */
function gate() {
  const sent: number[] = []
  const open: { resolve: () => void; reject: (e: Error) => void }[] = []
  const send = (v: number) => {
    sent.push(v)
    return new Promise<void>((resolve, reject) => open.push({ resolve, reject }))
  }
  return { sent, open, send }
}
const tick = () => new Promise((r) => setTimeout(r, 0))

describe('createSaveQueue', () => {
  it('sends a single value at once', async () => {
    const g = gate()
    const q = createSaveQueue(g.send)
    const p = q.push(1)
    await tick()
    expect(g.sent).toEqual([1])
    g.open[0].resolve()
    expect(await p).toEqual({ ok: true })
  })

  it('keeps one PUT in flight and sends only the latest value that waited', async () => {
    const g = gate()
    const q = createSaveQueue(g.send)
    const results = [q.push(1), q.push(2), q.push(3)]
    await tick()
    expect(g.sent).toEqual([1])
    g.open[0].resolve()
    await tick()
    expect(g.sent).toEqual([1, 3]) // 2 was replaced by 3
    g.open[1].resolve()
    expect(await Promise.all(results)).toEqual([{ ok: true }, { ok: true }, { ok: true }])
  })

  it('starts again after the queue ran empty', async () => {
    const g = gate()
    const q = createSaveQueue(g.send)
    const first = q.push(1)
    await tick()
    g.open[0].resolve()
    await first
    const second = q.push(2)
    await tick()
    expect(g.sent).toEqual([1, 2])
    g.open[1].resolve()
    await second
  })

  it('reports a failure to the value that failed and drops what waited behind it', async () => {
    const g = gate()
    const q = createSaveQueue(g.send)
    const a = q.push(1)
    const b = q.push(2)
    await tick()
    g.open[0].reject(new Error('bad'))
    const [ra, rb] = await Promise.all([a, b])
    expect(ra.ok).toBe(false)
    expect(rb.ok).toBe(false)
    expect(g.sent).toEqual([1])
    // and the queue works again
    const c = q.push(3)
    await tick()
    g.open[1].resolve()
    expect(await c).toEqual({ ok: true })
  })
})
