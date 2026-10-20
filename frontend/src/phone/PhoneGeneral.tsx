import { useEffect, useState } from 'react'
import { api, type MacroDef } from '../api'
import { FitLabel, colorTrackFor } from '../components/MacroControl'
import { BUTTONS, FADERS, MASKS, type SceneInfo } from '../generalControls'
import type { EngineConnection } from '../useEngine'
import { PhoneSlider } from './PhoneSlider'
import { LaptopNote, PhoneSection } from './parts'

/** A function or mask button (toggle, hold or radio): a 56 px tile, the name on top and its tag below. */
function PhoneButton({ def, label, tag, on, setMacro, toggleMacro }: { def: MacroDef; label: string; tag: string; on: boolean; setMacro: (n: string, v: number) => void; toggleMacro: (n: string) => void }) {
  const cls = `lbl flex h-14 w-full min-w-0 flex-col items-start justify-center gap-1 px-2.5 text-left select-none [touch-action:manipulation] [-webkit-touch-callout:none] ${
    on ? `bg-ink text-ground ${def.kind === 'momentary' ? 'glow-held' : 'glow-on'}` : 'bg-panel text-ink active:bg-panel-2'
  }`
  const content = (
    <>
      <span className="flex w-full text-[13px]">
        <FitLabel text={label} />
      </span>
      <span className="font-mono text-[11px] opacity-60">{tag}</span>
    </>
  )
  if (def.kind === 'momentary') {
    // held while the finger is on it; lifting it or sliding off releases
    return (
      <button className={cls} onPointerDown={() => setMacro(def.name, 1)} onPointerUp={() => setMacro(def.name, 0)} onPointerCancel={() => setMacro(def.name, 0)} onPointerLeave={() => on && setMacro(def.name, 0)} onContextMenu={(e) => e.preventDefault()}>
        {content}
      </button>
    )
  }
  return (
    <button className={cls} onClick={() => (def.kind === 'toggle' ? toggleMacro(def.name) : setMacro(def.name, 1))}>
      {content}
    </button>
  )
}

export function PhoneGeneral({ engine, defs }: { engine: EngineConnection; defs: Record<string, MacroDef> }) {
  const { state, setMacro, toggleMacro } = engine
  const macros = state?.macros ?? {}
  const pending = state?.pending ?? {}
  const shown = { ...macros, ...pending }
  const [scenes, setScenes] = useState<SceneInfo[]>([])
  const [mode, setMode] = useState<'load' | 'save' | 'delete'>('load')
  const [lastScene, setLastScene] = useState<number | null>(null)

  const loadScenes = () => api.get<SceneInfo[]>('/api/scenes').then(setScenes)
  useEffect(() => {
    loadScenes()
  }, [])

  const sceneAction = async (i: number) => {
    if (mode === 'delete') {
      await api.delete(`/api/scenes/${i}`)
      loadScenes()
    } else if (mode === 'save') {
      await api.post(`/api/scenes/${i}/save`)
      loadScenes()
    } else if (await api.post(`/api/scenes/${i}/load`).then(() => true, () => false)) {
      setLastScene(i)
    }
    setMode('load')
  }

  const modeButton = (m: 'save' | 'delete', label: string) => (
    <button
      className={`lbl h-11 px-4 text-[12px] [touch-action:manipulation] ${mode === m ? 'glow-on bg-ink text-ground' : 'border border-edge text-ink'}`}
      onClick={() => setMode(mode === m ? 'load' : m)}
    >
      {label}
    </button>
  )

  // the macros first, in the laptop's order (Miro, 2026-10-20); landscape: two columns that scroll on their own,
  // the macros on the left and the buttons on the right
  return (
    <div className="flex flex-col gap-1.5 landscape:grid landscape:h-full landscape:grid-cols-2">
      <div className="flex flex-col gap-1.5 landscape:min-h-0 landscape:overflow-auto">
        <PhoneSection index="01" title="Macros" right="drag sideways">
          <div className="flex flex-col gap-px bg-edge">
            {FADERS.map((name, i) =>
              defs[name] ? (
                <PhoneSlider
                  key={name}
                  def={defs[name]}
                  value={shown[name] ?? 0}
                  applied={macros[name] ?? 0}
                  setMacro={setMacro}
                  colorTrack={colorTrackFor(name, shown, defs)}
                  pending={name in pending}
                  index={i + 1}
                />
              ) : null,
            )}
          </div>
        </PhoneSection>
      </div>

      <div className="flex flex-col gap-1.5 landscape:min-h-0 landscape:overflow-auto">
        <PhoneSection
          index="02"
          title="Scenes"
          right={
            <>
              {modeButton('save', 'Save')}
              {modeButton('delete', 'Delete')}
            </>
          }
        >
          {mode !== 'load' && (
            <p className="lbl border-b border-edge bg-ink px-3 py-1.5 text-[12px] text-ground">
              {mode === 'save' ? 'Tap a scene to save the current macros into it' : 'Tap a scene to empty it'}
            </p>
          )}
          <div className="grid grid-cols-4 gap-px bg-edge">
            {scenes.map((s) => (
              <button
                key={s.index}
                onClick={() => sceneAction(s.index)}
                className={`flex h-16 flex-col justify-center gap-1 px-2.5 text-left [touch-action:manipulation] ${mode !== 'load' ? 'bg-panel-2' : 'bg-panel active:bg-panel-2'} ${
                  lastScene === s.index ? 'shadow-[inset_0_-3px_0_var(--color-ink)]' : ''
                } ${s.exists ? 'text-ink' : 'text-dim'}`}
              >
                <span className="font-mono text-[22px] leading-none">{String(s.index + 1).padStart(2, '0')}</span>
                <span className="lbl flex w-full text-[11px] opacity-70">
                  <FitLabel text={s.name ?? 'defaults'} />
                </span>
              </button>
            ))}
          </div>
        </PhoneSection>

        <PhoneSection index="03" title="Functions">
          <div className="grid grid-cols-3 gap-px bg-edge">
            {BUTTONS.map(([name, tag, label]) =>
              defs[name] ? <PhoneButton key={name} def={defs[name]} label={label} tag={tag} on={(macros[name] ?? 0) > 0.5} setMacro={setMacro} toggleMacro={toggleMacro} /> : null,
            )}
          </div>
        </PhoneSection>

        <PhoneSection index="04" title="Mask">
          <div className="grid grid-cols-2 gap-px bg-edge min-[380px]:grid-cols-4">
            {MASKS.map(([name, label, tag]) =>
              defs[name] ? <PhoneButton key={name} def={defs[name]} label={label} tag={tag} on={(macros[name] ?? 0) > 0.5} setMacro={setMacro} toggleMacro={toggleMacro} /> : null,
            )}
          </div>
        </PhoneSection>

        <LaptopNote />
      </div>
    </div>
  )
}
