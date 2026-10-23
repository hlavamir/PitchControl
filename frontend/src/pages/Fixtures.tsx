import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import { api, byName, channelCount, slotKind, type ChannelMode, type FixtureType, type HSB, type MacroDef, type PixelFormat } from '../api'
import { hsvCss } from '../components/MacroControl'
import { FixtureImportDialog } from '../components/FixtureImport'
import { Button, NumberInput, Row, Section } from '../components/forms'
import { useSaveAction } from '../leaveGuard'
import type { Origin } from '../components/RigPanel'
import { copyOfLastMode, edited, slotOfKind, type Kind } from '../fixtureEdit'
import { fixturesInMode, hasSameName } from '../modes'
import { linkGroups } from '../links'
import { onImportRequest, takeImportRequest, type ImportKind } from '../fixtureImport'
import { useFieldNav } from '../useFieldNav'
import { OPEN_TYPE_KEY } from './Rig'

const KIND_LABEL: Record<Kind, string> = { value: 'constant', macro: 'macro', shutter: 'shutter', pixels: 'pixels' }
const FORMATS: PixelFormat[] = ['I', 'RGB', 'RGBW']

interface Status {
  unsaved: string[]
  usage: Record<string, string[]>
  origins: Record<string, Origin>
}

type Prompt = { kind: 'name'; action: 'new' | 'duplicate' | 'rename' } | { kind: 'delete' } | { kind: 'reset' }

/** The DMX channels of one mode of a type, as "start–end: what" lines. */
function channelMap(mode: ChannelMode): { from: number; to: number; text: string }[] {
  const rows: { from: number; to: number; text: string }[] = []
  let ch = 1
  for (const s of mode.channels) {
    const n = s.pixels ? mode.pixels * s.pixels.length : 1
    const label = s.name ? `${s.name} ` : ''
    let text: string
    if (s.pixels) text = `${label}pixels ${s.pixels} × ${mode.pixels}`
    else if (s.value != null) text = `${label}= ${s.value}`
    else if (s.macro) text = `${label}← ${s.macro}`
    else text = `${label}shutter (open ${s.shutter?.open}, strobe ${s.shutter?.strobo})`
    rows.push({ from: ch, to: ch + n - 1, text })
    ch += n
  }
  return rows
}

/**
 * Fixture types: everything shared by all fixtures of one model (output, pixels, channel layout,
 * gamma, strobo defaults), one JSON file each in fixtures/types/. Edits apply live; Save writes
 * the file, Revert reloads it. Rig fixtures can override some values on the Rig page.
 */
export function Fixtures({ defs }: { defs: Record<string, MacroDef> }) {
  const [types, setTypes] = useState<Record<string, FixtureType>>({})
  const [status, setStatus] = useState<Status>({ unsaved: [], usage: {}, origins: {} })
  const [selected, setSelected] = useState<string>('')
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [name, setName] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [modeAsk, setModeAsk] = useState<{ index: number; fixtures: string[] } | null>(null) // deleting a mode the rig uses
  const [importing, setImporting] = useState<ImportKind | null>(null) // File → Import Fixture → Open Fixture Library… / QLC+… (which dialog is open)
  const [app, setApp] = useState<{ desktop: boolean; local: boolean }>({ desktop: false, local: true })

  const loadStatus = useCallback(() => api.get<Status>('/api/fixture-types/status').then(setStatus), [])
  const reload = useCallback(
    async (select?: string) => {
      const all = await api.get<Record<string, FixtureType>>('/api/fixture-types')
      setTypes(all)
      loadStatus()
      setSelected((cur) => {
        let wanted = select ?? cur
        if (!wanted) {
          try {
            wanted = sessionStorage.getItem(OPEN_TYPE_KEY) ?? ''
            sessionStorage.removeItem(OPEN_TYPE_KEY)
          } catch {
            wanted = ''
          }
        }
        return all[wanted] ? wanted : (Object.keys(all).sort(byName)[0] ?? '')
      })
    },
    [loadStatus],
  )
  useEffect(() => {
    reload()
  }, [reload])
  useEffect(() => {
    api.get<{ desktop: boolean; local: boolean }>('/api/app-info').then(setApp).catch(() => undefined)
  }, [])
  // the menu bar's File → Import Fixture → … (on this page already, or asked before it was shown)
  useEffect(() => {
    const take = () => {
      const kind = takeImportRequest()
      if (kind) setImporting(kind)
    }
    take()
    return onImportRequest(take)
  }, [])
  // a link of a type (manual, product page): the desktop app opens it in the default browser through the backend
  const openLink = (e: MouseEvent, url: string) => {
    if (!app.desktop || !app.local) return // a browser follows the link itself
    e.preventDefault()
    api.post('/api/open-url', { url }).catch(() => window.open(url, '_blank'))
  }

  const t = types[selected]

  // keys (rigKeys.ts, useFieldNav.ts): W S ↑ ↓ choose the type in the list, D → goes into the editor, which is navigated field by field
  const pageRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const editorRef = useRef<HTMLDivElement>(null)
  useFieldNav({
    root: pageRef,
    list: listRef,
    entry: editorRef,
    onListAction: (action) => {
      if (action.kind !== 'move') return
      const names = Object.values(types).sort((a, b) => byName(a.name, b.name)).map((x) => x.name)
      const to = names[names.indexOf(selected) + action.step]
      if (!to) return false
      setSelected(to)
      setModeAsk(null)
      setMessage(null)
    },
    listFooter: t ? { label: t.name, hint: 'list', tip: 'The fixture types: W S ↑ ↓ choose one, D or → goes into its editor' } : null,
  })
  useEffect(() => {
    ;[...(listRef.current?.querySelectorAll<HTMLElement>('[data-name]') ?? [])].find((el) => el.dataset.name === selected)?.scrollIntoView({ block: 'nearest' })
  }, [selected])
  const unsaved = status.unsaved.includes(selected)
  const usedIn = status.usage[selected] ?? []
  const origin: Origin = status.origins[selected] ?? 'user'
  // macros a channel can follow: the faders (dimmers first, they're what fixtures usually bind)
  const macroNames = Object.values(defs)
    .filter((d) => d.kind === 'fader')
    .sort((a, b) => (a.page === 'dimmers' ? 0 : 1) - (b.page === 'dimmers' ? 0 : 1))
    .map((d) => d.name)

  // live edits are chained so Save / Revert / Rename wait for the last one
  const live = useRef<Promise<unknown>>(Promise.resolve())
  const applyLive = (next: FixtureType) => {
    live.current = live.current
      .then(() => api.put(`/api/fixture-types/${encodeURIComponent(next.name)}?persist=false`, next))
      .then(loadStatus)
      .catch((e) => setMessage(String(e)))
  }
  const edit = (fn: (t: FixtureType) => void, liveNow = true) => {
    if (!t) return
    const next = edited(t, fn)
    setTypes((all) => ({ ...all, [next.name]: next }))
    if (liveNow) applyLive(next)
  }

  const save = async () => {
    await live.current
    const res = await api.put<{ problems: string[] }>(`/api/fixture-types/${encodeURIComponent(selected)}`, types[selected])
    setMessage(res.problems.length ? `Saved · rig: ${res.problems.join('; ')}` : 'Saved')
    loadStatus()
  }
  useSaveAction('fixture type', unsaved, save) // the menu bar's Save: the same as the Save button
  const reset = () =>
    run(async () => {
      const fresh = await api.post<FixtureType>(`/api/fixture-types/${encodeURIComponent(selected)}/reset`)
      setTypes((all) => ({ ...all, [selected]: { ...fresh, name: selected } }))
      setMessage('Reset to the version that comes with the app')
      return selected
    })
  const revert = async () => {
    await live.current
    const fresh = await api.post<FixtureType>(`/api/fixture-types/${encodeURIComponent(selected)}/reload`)
    setTypes((all) => ({ ...all, [selected]: { ...fresh, name: selected } }))
    setMessage(null)
    loadStatus()
  }

  const run = async (fn: () => Promise<string | undefined>) => {
    try {
      await live.current
      const select = await fn()
      setPrompt(null)
      await reload(select)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    }
  }
  const submitName = (action: 'new' | 'duplicate' | 'rename') =>
    run(async () => {
      const n = name.trim()
      if (action === 'rename') {
        const res = await api.post<{ name: string; rigs_updated: string[] }>(`/api/fixture-types/${encodeURIComponent(selected)}/rename`, { name: n })
        setMessage(res.rigs_updated.length ? `Renamed · updated rigs: ${res.rigs_updated.join(', ')}` : 'Renamed')
        return res.name
      }
      await api.post('/api/fixture-types', action === 'new' ? { name: n } : { name: n, copy_of: selected })
      setMessage(null)
      return n
    })
  const askName = (action: 'new' | 'duplicate' | 'rename') => {
    setMessage(null)
    setName(action === 'rename' ? selected : action === 'duplicate' ? `${selected} copy` : '')
    setPrompt({ kind: 'name', action })
  }

  const moveSlot = (mi: number, i: number, d: -1 | 1) =>
    edit((x) => {
      const channels = x.modes[mi].channels
      const j = i + d
      if (j < 0 || j >= channels.length) return
      ;[channels[i], channels[j]] = [channels[j], channels[i]]
    })

  const addMode = () => edit((x) => x.modes.push(copyOfLastMode(x.modes)))

  const removeMode = (mi: number) =>
    edit((x) => {
      const [gone] = x.modes.splice(mi, 1)
      if (x.default_mode === gone.id) x.default_mode = x.modes[0].id
    })

  /** Deleting a mode: at once when no fixture of the active rig runs in it, else after asking (they move to the default mode). */
  const askRemoveMode = async (mi: number) => {
    if (!t) return
    const gone = t.modes[mi]
    const rig = await api.get<{ fixtures: { name: string; type: string; mode?: string | null }[] }>('/api/rig')
    const users = fixturesInMode(rig.fixtures, t, gone.id)
    if (users.length) setModeAsk({ index: mi, fixtures: users })
    else removeMode(mi)
  }

  /** The confirmed deletion: the fixtures of the active rig that ran in the mode go to the default mode, live (the Rig page shows the rig unsaved). */
  const removeUsedMode = async (mi: number, names: string[]) => {
    if (!t) return
    const fallback = t.modes[mi].id === t.default_mode ? t.modes.find((_, i) => i !== mi)!.id : t.default_mode
    removeMode(mi)
    setModeAsk(null)
    try {
      await live.current
      const rig = await api.get<{ fixtures: { name: string; type: string; mode?: string | null }[] }>('/api/rig')
      for (const f of rig.fixtures) if (f.type === t.name && names.includes(f.name)) f.mode = fallback
      await api.put('/api/rig?persist=false', rig)
      setMessage(`Mode deleted. ${names.join(', ')} now ${names.length === 1 ? 'runs' : 'run'} in the default mode; the rig has unsaved changes (Rig page).`)
    } catch (e) {
      setMessage(String(e))
    }
  }

  const hsb = (c: HSB) => (
    <>
      {(['h', 's', 'b'] as const).map((k) => (
        <NumberInput key={k} value={c[k]} min={0} max={1} className="w-14 shrink" onChange={(v) => edit((x) => (x.strobo_color = { ...x.strobo_color, [k]: v }))} />
      ))}
      <span className="size-3.5 flex-none" style={{ background: hsvCss(c.h, c.s, c.b) }} />
    </>
  )

  const count = t ? channelCount(t) : 0

  return (
    <>
    <div ref={pageRef} className="grid gap-1.5 wide:h-full wide:grid-cols-[17rem_minmax(0,1fr)_22rem] wide:grid-rows-[minmax(0,1fr)]">
      <Section
        index="01"
        title="Fixture types"
        right={`${Object.keys(types).length} types`}
        bodyClassName="p-2.5 min-h-0 gap-2"
        tip="Fixture types: what a kind of light is (pixels, channels, defaults). Some come with the app, your own are files in your data folder (fixtures/types); rigs place them"
      >
        <ul ref={listRef} className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-auto select-none">
          {Object.values(types)
            .sort((a, b) => byName(a.name, b.name))
            .map((x) => (
            <li key={x.name}>
              <button
                onClick={() => {
                  setSelected(x.name)
                  setModeAsk(null)
                  setMessage(null)
                }}
                className={`flex w-full items-center gap-2 px-2 py-1.5 text-left text-[13px] ${x.name === selected ? 'glow-on bg-ink text-ground' : 'hover:bg-panel-2'}`}
                data-hint="list"
                data-name={x.name}
                data-tip={status.usage[x.name]?.length ? `Used in: ${status.usage[x.name].join(', ')}` : 'Not used in any rig'}
              >
                <span className="flex-1 truncate">{x.name}</span>
                {status.unsaved.includes(x.name) && <span className={`size-[6px] flex-none ${x.name === selected ? 'bg-ground' : 'dot-on'}`} data-hint="info" data-tip="Unsaved edits: live in the engine, Save writes the type file" />}
                {status.origins[x.name] && status.origins[x.name] !== 'user' && (
                  <span className="lbl text-[9px] opacity-60" data-hint="info" data-tip={status.origins[x.name] === 'default' ? 'Comes with the app' : 'Comes with the app, changed by you (your copy is in your data folder)'}>
                    {status.origins[x.name] === 'default' ? 'app' : 'mod'}
                  </span>
                )}
                <span className="font-mono text-[11px] opacity-70">{x.transport === 'pitchpls_v2' ? 'serial' : x.modes.length > 1 ? `${x.modes.length} modes` : `${channelCount(x)} ch`}</span>
              </button>
            </li>
          ))}
        </ul>

        {prompt === null && (
          <div className="flex flex-wrap gap-1.5">
            <Button onClick={() => askName('new')} tip="Create a new type: 1 RGB pixel on DMX; shape it in the editor">
              New
            </Button>
            <Button onClick={() => askName('duplicate')} disabled={!t} tip="Copy the selected type under a new name, as a starting point for a similar light">
              Duplicate
            </Button>
            <Button onClick={() => askName('rename')} disabled={!t} tip="Rename the type file; every rig that uses it is updated">
              Rename
            </Button>
            <Button
              onClick={() => setImporting('ofl')}
              disabled={!app.local}
              tip={app.local ? 'Import a fixture from the Open Fixture Library: a .json file, or online by manufacturer and fixture (File → Import Fixture)' : 'Importing works on the computer that runs PitchControl: it writes that computer’s data folder'}
            >
              Import OFL…
            </Button>
            <Button
              onClick={() => setImporting('qlc')}
              disabled={!app.local}
              tip={app.local ? 'Import a fixture from QLC+: a .qxf file, or one of the fixtures in the folders of QLC+ on this computer (File → Import Fixture)' : 'Importing works on the computer that runs PitchControl: it writes that computer’s data folder'}
            >
              Import QLC+…
            </Button>
            {origin === 'modified' ? (
              <Button onClick={() => setPrompt({ kind: 'reset' })} disabled={!t} tip="Back to the version that comes with the app: your changes to this type are deleted (asks first)">
                Reset
              </Button>
            ) : (
              <span data-tip={origin === 'default' ? 'Comes with the app: it cannot be deleted' : usedIn.length ? `Cannot delete: used in ${usedIn.join(', ')}` : undefined}>
                <Button onClick={() => setPrompt({ kind: 'delete' })} disabled={!t || usedIn.length > 0 || origin !== 'user'} tip="Delete the type file (asks first); refused while a rig uses it">
                  Delete
                </Button>
              </span>
            )}
          </div>
        )}
        {prompt?.kind === 'name' && (
          <div className="flex flex-col gap-1.5 border border-edge p-2">
            <span className="lbl text-[10px] text-dim">
              {prompt.action === 'new' ? 'New fixture type (1 RGB pixel on DMX)' : prompt.action === 'duplicate' ? `Duplicate “${selected}”` : `Rename “${selected}” — rigs using it are updated`}
            </span>
            <input
              type="text"
              autoFocus
              onFocus={(e) => e.currentTarget.select()}
              value={name}
              placeholder="type name"
              data-tip="Name of the type file (also its name in rigs): letters, digits, space, - _ . ; ⏎ confirms, Esc cancels"
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitName(prompt.action)
                else if (e.key === 'Escape') setPrompt(null)
              }}
            />
            <div className="flex gap-1.5">
              <Button primary onClick={() => submitName(prompt.action)} disabled={!name.trim()}>
                {prompt.action === 'new' ? 'Create' : prompt.action === 'rename' ? 'Rename' : 'Duplicate'}
              </Button>
              <Button onClick={() => setPrompt(null)}>Cancel</Button>
            </div>
          </div>
        )}
        {prompt?.kind === 'delete' && (
          <div className="flex flex-col gap-1.5 border border-ink p-2">
            <span className="text-[11px]">Delete the fixture type file “{selected}”?</span>
            <div className="flex gap-1.5">
              <Button primary onClick={() => run(async () => (await api.delete(`/api/fixture-types/${encodeURIComponent(selected)}`), ''))}>
                Delete
              </Button>
              <Button onClick={() => setPrompt(null)}>Cancel</Button>
            </div>
          </div>
        )}
        {prompt?.kind === 'reset' && (
          <div className="flex flex-col gap-1.5 border border-ink p-2">
            <span className="text-[11px]">Reset “{selected}” to the version that comes with the app? Your changes to it are lost.</span>
            <div className="flex gap-1.5">
              <Button primary onClick={reset}>
                Reset
              </Button>
              <Button onClick={() => setPrompt(null)}>Cancel</Button>
            </div>
          </div>
        )}
        {message && <p className="text-[11px] text-ink">{message}</p>}
      </Section>

      <Section
        index="02"
        title={t ? t.name : 'Fixture type'}
        right={
          t && (
            <>
              {unsaved ? (
                <span className="inline-flex items-center gap-1.5 text-ink" data-hint="info" data-tip="Edits are live in the engine but not written to the type file yet">
                  <span className="dot-on inline-block size-[7px]" />
                  unsaved
                </span>
              ) : (
                'saved'
              )}
              <button className="lbl h-[18px] border border-edge px-2 text-[10px] text-ink disabled:opacity-35" disabled={!unsaved} onClick={revert} data-tip="Throw away the unsaved edits and reload the type from its file">
                Revert
              </button>
              <button className="lbl glow-on h-[18px] bg-ink px-2 text-[10px] text-ground disabled:opacity-35" disabled={!unsaved} onClick={save} data-tip="Write the type to its file in your data folder (fixtures/types); a type that comes with the app gets your own copy">
                Save
              </button>
            </>
          )
        }
        bodyClassName="p-3 min-h-0 overflow-auto"
        tip="Editor of the selected fixture type. Edits apply to the lights at once; Save writes the file"
      >
        {t && (
          <div ref={editorRef} className="flex flex-col">
            <Row label="Description" hint="Free text about this light; shown as the tip of the type in the Rig page's fixture list">
              <textarea
                rows={2}
                className="w-full resize-none text-[12px] leading-snug"
                value={t.description}
                onChange={(e) => edit((x) => (x.description = e.target.value), false)}
                onBlur={() => applyLive(types[selected])}
              />
            </Row>
            <Row label="Output" hint="DMX (Enttec / Art-Net, with a channel layout) or the PitchPlease v2 serial protocol (3 bytes per pixel)">
              <select value={t.transport} onChange={(e) => edit((x) => (x.transport = e.target.value as FixtureType['transport']))}>
                <option value="dmx">DMX</option>
                <option value="pitchpls_v2">PitchPlease v2 serial</option>
              </select>
            </Row>
            {t.transport === 'pitchpls_v2' && (
              <Row label="Pixels" hint="Number of pixels (individually controlled segments) of one fixture, 1–512">
                <NumberInput value={t.modes[0].pixels} integer min={1} max={512} onChange={(v) => edit((x) => x.modes.forEach((m) => (m.pixels = v)))} />
              </Row>
            )}
            <Row
              label="Gamma"
              hint="Device curve: sent = value ^ gamma. 1 = unchanged (v2 / v3 decode it themselves); ~2.2 for fixtures without a curve"
            >
              <NumberInput value={t.gamma} min={0.1} max={5} className="w-20 shrink" onChange={(v) => edit((x) => (x.gamma = v))} />
            </Row>
            <Row label="Strobo colour (HSB)" hint="Colour of the strobo flash: hue, saturation, brightness, each 0–1; a rig fixture can override it">
              {hsb(t.strobo_color)}
            </Row>
            <Row label="Used in" hint="Rigs that place this type; a type in use cannot be deleted">
              <span className="text-[12px] text-dim">{usedIn.length ? usedIn.join(', ') : 'no rig'}</span>
            </Row>
            {linkGroups(t).length > 0 && (
              <Row label="Links" hint="Where the fixture's manual and product page are, as the Open Fixture Library has them: check the type against the manual" plain>
                <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-[12px]">
                  {linkGroups(t).map((g) =>
                    g.urls.map((u, i) => (
                      <a key={u} href={u} target="_blank" rel="noreferrer" className="underline" data-tip={u} onClick={(e) => openLink(e, u)}>
                        {g.urls.length > 1 ? `${g.label} ${i + 1}` : g.label} ›
                      </a>
                    )),
                  )}
                </span>
              </Row>
            )}
            {t.source?.format === 'ofl' && (
              <Row
                label="Source"
                hint={
                  t.source.via === 'qlcplus'
                    ? "This type was imported from a QLC+ fixture definition; the data is kept in the type file (the OFL keys and the original in qlcplus), whatever you edit here"
                    : "This type was imported from the Open Fixture Library; the library's original data is kept in the type file, whatever you edit here"
                }
                plain
              >
                <span className="text-[12px] text-dim">
                  {t.source.via === 'qlcplus' ? 'QLC+ fixture definition' : 'Open Fixture Library'}
                  {[t.source.fixture, t.source.file, t.source.commit?.slice(0, 7)].filter(Boolean).map((x) => ` · ${x}`)}
                </span>
              </Row>
            )}

            <div className="mt-3 border-t border-seam pt-3">
              <p className="lbl mb-2 text-[10px] text-dim">
                {t.transport === 'pitchpls_v2' ? 'Channel layout' : "Channel modes · one section per mode, channels in DMX order from the fixture's address"}
              </p>
              {t.transport === 'pitchpls_v2' ? (
                <p className="text-[12px] text-dim">The PitchPlease v2 serial protocol sends 3 bytes (RGB) per pixel; a channel layout isn't used.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {t.modes.map((mode, mi) => {
                    const isDefault = mode.id === t.default_mode
                    const duplicate = hasSameName(t.modes, mi)
                    return (
                      <div key={mode.id} className={`flex flex-col gap-1 border p-2 ${isDefault ? 'border-ink' : 'border-edge'}`}>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <input
                            type="text"
                            className="w-32"
                            placeholder="mode name"
                            value={mode.name}
                            onChange={(e) => edit((x) => (x.modes[mi].name = e.target.value), false)}
                            onBlur={() => applyLive(types[selected])}
                            data-tip="Name of this mode, as the fixture's display or manual calls it (e.g. 6CH). Rigs store the mode's id, so renaming never breaks one"
                          />
                          <NumberInput
                            value={mode.pixels}
                            integer
                            min={1}
                            max={512}
                            className="w-16 shrink"
                            tip="Number of pixels (individually controlled segments) the light has in this mode, 1–512: a bar can have 1 pixel in one mode and 8 in another"
                            onChange={(v) => edit((x) => (x.modes[mi].pixels = v))}
                          />
                          <span className="lbl text-[10px] text-dim">px · {channelCount(t, mode.id)} ch</span>
                          {isDefault ? (
                            <span className="lbl glow-on bg-ink px-1.5 text-[10px] leading-[18px] text-ground" data-hint="info" data-tip="The default mode: a new fixture of this type starts in it, and a fixture without a mode uses it">
                              default
                            </span>
                          ) : (
                            <button
                              className="lbl h-[18px] border border-edge px-1.5 text-[10px] text-dim hover:text-ink"
                              data-tip="Make this the default mode: new fixtures of this type start in it"
                              onClick={() => edit((x) => (x.default_mode = mode.id))}
                            >
                              make default
                            </button>
                          )}
                          {duplicate && (
                            <span className="lbl text-[10px] text-ink" data-hint="info" data-tip="Another mode of this type has the same name: the Mode dropdown on the Rig page would show two of the same">
                              ⚠ same name as another mode
                            </span>
                          )}
                          <button
                            className="ml-auto px-1 text-dim hover:text-ink disabled:opacity-30"
                            disabled={t.modes.length === 1}
                            data-tip={t.modes.length === 1 ? 'A type needs at least one mode' : 'Delete this mode (asks first when a fixture of the rig runs in it)'}
                            onClick={() => askRemoveMode(mi)}
                          >
                            ✕ delete mode
                          </button>
                        </div>
                        {modeAsk?.index === mi && (
                          <div className="flex flex-wrap items-center gap-1.5 border border-ink p-2 text-[11px]">
                            <span className="min-w-0 flex-1">
                              {modeAsk.fixtures.join(', ')} {modeAsk.fixtures.length === 1 ? 'runs' : 'run'} in this mode in the active rig. Delete it anyway? {modeAsk.fixtures.length === 1 ? 'That fixture moves' : 'They move'} to the default mode.
                            </span>
                            <Button primary onClick={() => removeUsedMode(mi, modeAsk.fixtures)}>
                              Delete mode
                            </Button>
                            <Button onClick={() => setModeAsk(null)}>Cancel</Button>
                          </div>
                        )}
                        <input
                          type="text"
                          className="w-full text-[12px]"
                          placeholder="short description (optional), e.g. what the channels are"
                          value={mode.description}
                          onChange={(e) => edit((x) => (x.modes[mi].description = e.target.value), false)}
                          onBlur={() => applyLive(types[selected])}
                          data-tip="A line about this mode, shown with it in the editor and as the tip of the Mode dropdown on the Rig page"
                        />
                        <div className="flex flex-col gap-1">
                {mode.channels.map((slot, i) => {
                  const kind = slotKind(slot)
                  return (
                    <div key={i} data-tip={`DMX channel ${i + 1} of the fixture: what it does, its name, and its value`} className="flex flex-wrap items-center gap-1.5 bg-panel-2 px-2 py-1 text-[12px]">
                      <span className="w-6 font-mono text-[11px] text-dim">{String(i + 1).padStart(2, '0')}</span>
                      <select
                        value={kind}
                        data-tip="What this DMX channel does: a constant, a macro (e.g. a dimmer), the shutter, or the pixel colours"
                        onChange={(e) => edit((x) => (x.modes[mi].channels[i] = slotOfKind(slot, e.target.value as Kind, macroNames[0] ?? 'Dimmer 01')))}
                      >
                        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
                          <option key={k} value={k}>
                            {KIND_LABEL[k]}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        className="w-28"
                        placeholder="name"
                        value={slot.name ?? ''}
                        onChange={(e) => edit((x) => (x.modes[mi].channels[i].name = e.target.value || null), false)}
                        onBlur={() => applyLive(types[selected])}
                        data-tip="Name of the channel. A named constant can be overridden per fixture on the Rig page"
                      />
                      {kind === 'value' && (
                        <NumberInput value={slot.value} integer min={0} max={255} className="w-16" tip="Constant value sent on this channel (0–255)" onChange={(v) => edit((x) => (x.modes[mi].channels[i].value = v))} />
                      )}
                      {kind === 'macro' && (
                        <select value={slot.macro ?? ''} data-tip="Macro whose value (0–1) is sent on this channel, e.g. a dimmer fader" onChange={(e) => edit((x) => (x.modes[mi].channels[i].macro = e.target.value))}>
                          {!macroNames.includes(slot.macro ?? '') && <option value={slot.macro ?? ''}>{slot.macro} (missing)</option>}
                          {macroNames.map((m) => (
                            <option key={m}>{m}</option>
                          ))}
                        </select>
                      )}
                      {kind === 'shutter' && (
                        <>
                          <span className="lbl text-[10px] text-dim">open</span>
                          <NumberInput value={slot.shutter?.open} integer min={0} max={255} className="w-14" tip="Shutter channel value for open (no strobe), 0–255" onChange={(v) => edit((x) => (x.modes[mi].channels[i].shutter = { ...x.modes[mi].channels[i].shutter!, open: v }))} />
                          <span className="lbl text-[10px] text-dim">strobe</span>
                          <NumberInput value={slot.shutter?.strobo} integer min={0} max={255} className="w-14" tip="Shutter channel value for the fixture's own strobe, 0–255" onChange={(v) => edit((x) => (x.modes[mi].channels[i].shutter = { ...x.modes[mi].channels[i].shutter!, strobo: v }))} />
                        </>
                      )}
                      {kind === 'pixels' && (
                        <select value={slot.pixels ?? 'RGB'} data-tip="Colour format of the pixel channels: I (one brightness channel per pixel, for a single-colour light), RGB or RGBW (white is extracted from RGB)" onChange={(e) => edit((x) => (x.modes[mi].channels[i].pixels = e.target.value as PixelFormat))}>
                          {FORMATS.map((f) => (
                            <option key={f} value={f}>
                              {f === 'I' ? 'I (one brightness channel)' : f}
                            </option>
                          ))}
                        </select>
                      )}
                      <span className="ml-auto flex gap-1">
                        <button className="px-1 text-dim hover:text-ink disabled:opacity-30" disabled={i === 0} data-tip="Move this channel up: earlier in the DMX order" onClick={() => moveSlot(mi, i, -1)}>
                          ↑
                        </button>
                        <button className="px-1 text-dim hover:text-ink disabled:opacity-30" disabled={i === mode.channels.length - 1} data-tip="Move this channel down: later in the DMX order" onClick={() => moveSlot(mi, i, 1)}>
                          ↓
                        </button>
                        <button
                          className="px-1 text-dim hover:text-ink disabled:opacity-30"
                          disabled={mode.channels.length === 1}
                          data-tip="Remove this channel from the layout"
                          onClick={() => edit((x) => x.modes[mi].channels.splice(i, 1))}
                        >
                          ✕
                        </button>
                      </span>
                    </div>
                  )
                })}
                          <div className="mt-1">
                            <Button onClick={() => edit((x) => x.modes[mi].channels.push({ name: null, value: 0 }))} tip="Append a constant channel (value 0) at the end of this mode's layout">
                              Add channel
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                  <div>
                    <Button onClick={addMode} tip="Add a mode: it starts as a copy of the last one, since a mode is mostly the one before it with a channel more or less">
                      Add mode
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </Section>

      <Section
        index="03"
        title="Channel map"
        right={t && t.transport === 'dmx' && (t.modes.length > 1 ? `${t.modes.length} modes` : `${count} channels`)}
        bodyClassName="p-3 min-h-0 overflow-auto"
        tip="The DMX channels of one fixture in each mode, counted from its address, and how many fit one universe (512 channels)"
      >
        {t && t.transport === 'dmx' && (
          <div className="flex flex-col gap-3">
            {t.modes.map((mode) => {
              const n = channelCount(t, mode.id)
              return (
                <div key={mode.id}>
                  <p className="lbl mb-1 flex justify-between text-[10px] text-dim">
                    <span>
                      {mode.name}
                      {mode.id === t.default_mode && ' · default'}
                    </span>
                    <span>{n} channels</span>
                  </p>
                  <div className="flex flex-col gap-px font-mono text-[12px]">
                    {channelMap(mode).map((r, i) => (
                      <div key={i} className="flex gap-3 bg-panel-2 px-2 py-1">
                        <span className="w-16 flex-none text-dim">{r.from === r.to ? r.from : `${r.from}–${r.to}`}</span>
                        <span className="min-w-0 flex-1 truncate" data-tip={r.text}>
                          {r.text}
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="lbl mt-1 text-[10px] text-dim">{Math.floor(512 / Math.max(n, 1))} fixtures in this mode fit one universe</p>
                </div>
              )
            })}
          </div>
        )}
        {t && t.transport === 'pitchpls_v2' && (
          <p className="text-[12px] text-dim">
            v2 serial: {t.modes[0].pixels} pixels × 3 bytes, sent on the PitchPlease v2 output (Connections → Serial).
          </p>
        )}
      </Section>
    </div>
    {importing && (
      <FixtureImportDialog
        kind={importing}
        types={types}
        origins={status.origins}
        usage={status.usage}
        openLink={openLink}
        onClose={() => setImporting(null)}
        onDone={(name, text) => {
          setImporting(null)
          run(async () => (setMessage(text), name))
        }}
      />
    )}
    </>
  )
}
