import { useCallback, useEffect, useRef, useState } from 'react'
import { useLeaveGuard } from '../leaveGuard'
import { api, type FogMachine } from '../api'
import { Button, NumberInput, Row, SaveBar, Section, StatusDot, Toggle, UniverseSelect } from '../components/forms'
import type { EngineConnection } from '../useEngine'
import { useFieldNav } from '../useFieldNav'

const NEW_MACHINE: FogMachine = {
  name: 'Fog',
  enabled: false,
  universe: 0,
  channel: 1,
  on_value: 255,
  off_value: 0,
  interval_s: 60,
  duration_s: 4,
  manual_macro: 'Fog Machine',
}

/** The active rig's fog machines, edited locally; Save writes them into the rig file (only them). */
function useRigFog() {
  const [rig, setRig] = useState('')
  const [machines, setMachines] = useState<FogMachine[] | null>(null)
  const [dirty, setDirty] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const reload = useCallback(() => {
    api.get<{ rig: string; machines: FogMachine[] }>('/api/rig/fog').then((r) => {
      setRig(r.rig)
      setMachines(r.machines)
      setDirty(false)
    })
  }, [])
  useEffect(reload, [reload])

  const update = useCallback((fn: (m: FogMachine[]) => void) => {
    setMachines((prev) => {
      if (!prev) return prev
      const next = structuredClone(prev)
      fn(next)
      return next
    })
    setDirty(true)
  }, [])

  const save = useCallback(async () => {
    if (!machines) return true
    let ok = true
    try {
      const res = await api.put<{ problems: string[] }>('/api/rig/fog', machines)
      setDirty(false)
      const fog = res.problems.filter((p) => p.startsWith('fog machine'))
      setMessage(fog.length ? `Saved · ${fog.join('; ')}` : 'Saved')
    } catch (e) {
      ok = false
      setMessage(String(e))
    }
    window.setTimeout(() => setMessage(null), 5000)
    return ok
  }, [machines])
  useLeaveGuard('fog machines', dirty, save)

  return { rig, machines, update, save, dirty, reload, message }
}

export function Fog({ engine }: { engine: EngineConnection }) {
  // keys (rigKeys.ts, useFieldNav.ts): W S A D move over the controls, ⏎ edits the highlighted one
  const pageRef = useRef<HTMLDivElement>(null)
  useFieldNav({ root: pageRef })

  const { rig, machines, update, save, dirty, reload, message } = useRigFog()
  if (!machines) return null

  return (
    // machines take half the page width side by side, or the full width under each other
    <div ref={pageRef} className="grid gap-1.5 wide:grid-cols-2">
      <div className="flex justify-between wide:col-span-2">
        <span className="flex items-center gap-3">
          <Button onClick={() => update((ms) => ms.push({ ...NEW_MACHINE }))} tip="Add a fog machine: a DMX channel that is switched on and off by a timer or by the Fog Machine button">
            Add fog machine
          </Button>
          <span className="lbl text-[11px] text-dim" data-hint="info" data-tip="Fog machines are part of the rig: each rig has its own, and loading another rig on the Rig page switches them">
            rig “{rig}”
          </span>
        </span>
        <SaveBar dirty={dirty} save={save} reload={reload} message={message} saveTip="Write the fog machines into the rig file (other unsaved changes of the rig stay unsaved)" />
      </div>
      {machines.length === 0 && (
        <p className="text-[12px] text-dim wide:col-span-2">This rig has no fog machines. Add one to fog on a timer or with the Fog Machine button.</p>
      )}
      {machines.map((m, i) => (
        <Section
          key={i}
          index={String(i + 1).padStart(2, '0')}
          title={m.name}
          right={<StatusDot ok={engine.state?.fog[m.name] ?? null} label={engine.state?.fog[m.name] ? 'fogging' : 'idle'} tip="Whether the machine is being sent its on value right now" />}
          tip="A fog machine as one DMX channel. On value while it fogs, off value otherwise; timer and manual trigger can fog"
        >
          <Row label="Name" hint="Name of the machine, used as this panel's title">
            <input type="text" className="w-full" value={m.name} onChange={(e) => update((ms) => (ms[i].name = e.target.value))} />
          </Row>
          <Row label="Timer" plain hint="Fog automatically: a burst every N seconds that lasts M seconds; off = only the manual trigger fogs">
            <Toggle checked={m.enabled} onChange={(v) => update((ms) => (ms[i].enabled = v))} />
            <span className="text-dim">every</span>
            <NumberInput value={m.interval_s} min={1} className="w-20" onChange={(v) => update((ms) => (ms[i].interval_s = v))} />
            <span className="text-dim">s for</span>
            <NumberInput value={m.duration_s} min={0} className="w-20" onChange={(v) => update((ms) => (ms[i].duration_s = v))} />
            <span className="text-dim">s</span>
          </Row>
          <Row label="DMX channel" plain hint="Where the machine listens: DMX universe (as in Connections) and channel 1–512">
            <span className="text-dim">universe</span>
            <UniverseSelect value={m.universe} onChange={(v) => update((ms) => (ms[i].universe = v))} />
            <span className="text-dim">channel</span>
            <NumberInput value={m.channel} integer min={1} max={512} className="w-20" onChange={(v) => update((ms) => (ms[i].channel = v))} />
          </Row>
          <Row label="DMX values" plain hint="Values (0–255) sent while fogging (on) and while idle (off); some machines need a minimum on value">
            <span className="text-dim">on</span>
            <NumberInput value={m.on_value} integer min={0} max={255} className="w-20" onChange={(v) => update((ms) => (ms[i].on_value = v))} />
            <span className="text-dim">off</span>
            <NumberInput value={m.off_value} integer min={0} max={255} className="w-20" onChange={(v) => update((ms) => (ms[i].off_value = v))} />
          </Row>
          <Row label="Manual trigger" hint="Also fog while the Fog Machine button is held (General page, or a controller button)">
            <Toggle checked={m.manual_macro === 'Fog Machine'} onChange={(v) => update((ms) => (ms[i].manual_macro = v ? 'Fog Machine' : null))} label="Fog Machine button" />
          </Row>
          <div className="mt-2">
            <Button onClick={() => update((ms) => ms.splice(i, 1))} tip="Remove this fog machine (written with Save)">
              Remove
            </Button>
          </div>
        </Section>
      ))}
    </div>
  )
}
