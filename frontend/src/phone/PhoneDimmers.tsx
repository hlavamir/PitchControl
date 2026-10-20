import { useEffect, useState } from 'react'
import { api, type MacroDef, type Rig } from '../api'
import type { EngineConnection } from '../useEngine'
import { PhoneSlider } from './PhoneSlider'
import { LaptopNote, PhoneSection } from './parts'

/** The sixteen dimmers as rows; the names come from the rig and are edited on the laptop. */
export function PhoneDimmers({ engine, defs }: { engine: EngineConnection; defs: Record<string, MacroDef> }) {
  const dimmers = Object.values(defs).filter((d) => d.page === 'dimmers')
  const macros = engine.state?.macros ?? {}
  const [rig, setRig] = useState<Rig | null>(null)
  useEffect(() => {
    api.get<Rig>('/api/rig').then(setRig)
  }, [])

  const names = rig?.dimmer_names ?? {}
  const used = new Set((rig?.fixtures ?? []).map((f) => f.dimmer_macro).filter(Boolean))
  // a dimmer no fixture uses is greyed out, as on the laptop
  const disabled = (d: MacroDef) => rig !== null && !used.has(d.name)

  return (
    <div className="flex flex-col gap-1.5">
      <PhoneSection index="01" title="Dimmers" right={`${used.size} in use`}>
        <div className="grid grid-cols-1 gap-px bg-edge landscape:grid-cols-2">
          {dimmers.map((d, i) => (
            <PhoneSlider key={d.name} def={{ ...d, label: names[d.name] || d.name }} value={macros[d.name] ?? 0} setMacro={engine.setMacro} index={i + 1} disabled={disabled(d)} />
          ))}
        </div>
        <p className="lbl border-t border-edge px-3 py-2.5 text-[12px] leading-snug text-dim">Fixtures choose their dimmer on the Rig page, on the laptop; a dimmer no fixture uses is greyed out.</p>
      </PhoneSection>
      <LaptopNote />
    </div>
  )
}
