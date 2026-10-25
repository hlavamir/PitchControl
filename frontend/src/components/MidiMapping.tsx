import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, byName, type ControllerFile, type MacroDef, type MidiMappingEntry, type Rig } from '../api'
import type { EngineConnection } from '../useEngine'
import { clashes as findClashes, channelOf, deadMappings, defaultMode, detectedNote, learnedMapping, newMapping, outChannelOf } from '../midiMapping'
import { midiNotice } from '../midiDevices'
import { createSaveQueue } from '../saveQueue'
import { unchanged, usePolling } from '../usePolling'
import { Button, Row, Section, TextInput } from './forms'
import { MAPPING_COLUMNS, MidiMappingRow } from './MidiMappingRow'
import { placeOrder } from '../macroPlace'

// MIDI mapping: one row per macro with the control (CC or note) and channel that drives it, whatever device it comes
// from (items 89, 90). "Learn" listens for the next message. Every change is written at once, to the user's copy of the
// controller file (the one that comes with the app is never changed): no Save (item 90, like Connections in item 88).

type Tab = 'general' | 'dimmers' | 'scenes' | 'controller'
const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'dimmers', label: 'Dimmers' },
  { id: 'scenes', label: 'Scenes & pages' },
  { id: 'controller', label: 'Controller' },
]

interface Learning {
  /** the row waiting for a control: an existing mapping, or a new one to be created from ``template`` */
  index: number | null
  template: MidiMappingEntry
  /** the engine's id of this Learn, once the start was answered: its result is taken by this id, once */
  id: number | null
  /** how long the engine waits (it ends Learn by itself) */
  seconds: number
}

type Prompt = { kind: 'name'; action: 'new' | 'duplicate' } | { kind: 'delete' } | { kind: 'reset' } | null

export function MidiMappingSection({
  index: sectionIndex,
  className = '',
  engine,
  onActiveChanged,
}: {
  index: string
  className?: string
  engine: EngineConnection
  onActiveChanged: (name: string | null) => void
}) {
  const [list, setList] = useState<{ active: string | null; available: string[]; origins: Record<string, string>; labels: Record<string, string> } | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [draft, setDraft] = useState<ControllerFile | null>(null)
  const draftRef = useRef<ControllerFile | null>(null) // the latest draft: edits that follow each other before a render build on it
  const selectedRef = useRef<string | null>(null)
  const version = useRef(0) // counts the edits, so a late reload doesn't overwrite a newer one
  const [defs, setDefs] = useState<MacroDef[]>([])
  const [dimmerNames, setDimmerNames] = useState<Record<string, string>>({})
  const [tab, setTab] = useState<Tab>('general')
  const [learning, setLearning] = useState<Learning | null>(null)
  // the default in channel was changed while some rows carry the old one as their own
  const [moveAsk, setMoveAsk] = useState<{ from: number; to: number; count: number } | null>(null)
  const [prompt, setPrompt] = useState<Prompt>(null)
  const [name, setName] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  // Learn refused because nothing would arrive: what to do about it
  const [learnBlock, setLearnBlock] = useState<{ why: string; fix: 'use' | null } | null>(null)
  const learnSeen = useRef(false) // the state has shown the engine's Learn with this id
  // what Learn found the hardware of a row to be (item 93), shown on that row until the row is changed; not saved in the file
  const [detected, setDetected] = useState<{ index: number; text: string } | null>(null)

  const midi = engine.state?.io.midi
  const origin = selected && list ? (list.origins[selected] ?? 'user') : 'user'
  const isActive = !!selected && list?.active?.toLowerCase() === selected.toLowerCase()

  const say = (text: string) => {
    setMessage(text)
    window.setTimeout(() => setMessage(null), 4000)
  }
  const fail = (e: unknown) => say(e instanceof Error ? e.message : String(e))
  const show = (c: ControllerFile | null) => {
    draftRef.current = c
    setDraft(c)
  }
  selectedRef.current = selected
  // the PUTs go one after the other, the latest draft winning (saveQueue.ts); the answer carries the edit time the file got
  const queue = useRef(
    createSaveQueue(async (job: { name: string; data: ControllerFile }) => {
      const c = await api.put<ControllerFile>(`/api/controllers/${encodeURIComponent(job.name)}`, job.data)
      const cur = draftRef.current
      if (cur && selectedRef.current === job.name) show({ ...cur, modified: c.modified, app_version: c.app_version })
    }),
  )

  // The list of controller files is read again every few seconds while the page is open (item 34: a file added or
  // removed outside the app shows up without a button). An answer that was overtaken by a later read is dropped, so
  // that a slow poll can't undo the choice a "new" or "duplicate" just made.
  const listRead = useRef(0)
  const loadList = useCallback(async (select?: string) => {
    const mine = ++listRead.current
    const l = await api.get<NonNullable<typeof list>>('/api/controllers')
    if (mine !== listRead.current) return l
    setList((prev) => unchanged(prev, l))
    setSelected((cur) => select ?? (cur && l.available.includes(cur) ? cur : (l.active ?? l.available[0] ?? null)))
    return l
  }, [])
  usePolling(() => loadList())

  useEffect(() => {
    loadList().catch(fail)
    api.get<MacroDef[]>('/api/macros/defs').then(setDefs)
    api.get<Rig>('/api/rig').then((r) => setDimmerNames(r.dimmer_names ?? {}))
  }, [loadList])

  // the file as saved replaces the draft: on a change of the selection, and after a PUT that failed
  const reload = useCallback((name: string, seen?: number) => {
    return api
      .get<ControllerFile>(`/api/controllers/${encodeURIComponent(name)}`)
      .then((c) => {
        if (selectedRef.current !== name || (seen !== undefined && seen !== version.current)) return
        show(c)
      })
      .catch(fail)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    version.current++
    setLearning(null)
    setMoveAsk(null)
    setLearnBlock(null)
    setDetected(null)
    if (!selected) {
      show(null)
      return
    }
    reload(selected)
  }, [selected, reload])

  const defOf = useMemo(() => new Map(defs.map((d) => [d.name, d])), [defs])
  const labelOf = (macro: string) => {
    const d = defOf.get(macro)
    const base = d?.label ?? macro
    return dimmerNames[macro] ? `${base} — ${dimmerNames[macro]}` : base
  }

  // -- edits
  // Every edit is written at once. A shipped mapping is copied into the user's folder by its first one (the list is read
  // again then, for the "app" / "modified" label). A PUT that fails shows its message and loads what is saved.
  const edit = (fn: (c: ControllerFile) => void) => {
    const cur = draftRef.current
    const name = selectedRef.current
    if (!cur || !name) return
    const next = structuredClone(cur)
    fn(next)
    version.current++
    show(next)
    const first = origin === 'default'
    queue.current.push({ name, data: next }).then((r) => {
      if (r.ok) {
        if (first) loadList().catch(fail)
        return
      }
      fail(r.error)
      version.current++ // what is shown is wrong now; the saved file replaces it
      reload(name)
    })
  }
  const patch = (index: number, over: Partial<MidiMappingEntry>) => {
    if (detected?.index === index) setDetected(null)
    edit((c) => void Object.assign(c.mappings[index], over))
  }
  const remove = (index: number) => {
    setDetected(null)
    // Learn remembers its row by index: a row removed above it moves it up, the row itself being removed ends Learn
    if (learning?.index === index) stopLearning()
    else if (learning?.index != null && learning.index > index) setLearning({ ...learning, index: learning.index - 1 })
    edit((c) => void c.mappings.splice(index, 1))
  }

  const mappingLabel = (m: MidiMappingEntry) => (m.mode === 'shift' ? 'shift' : labelOf(m.macro ?? '?'))

  // a mapping on the same control (kind, number, channel) as a shift button never fires: the shift button wins
  const dead = useMemo(() => {
    const ms = draft?.mappings ?? []
    const out = new Map<number, string>()
    deadMappings(ms, draft?.channel ?? 1).forEach((v, i) =>
      out.set(i, v === 'self' ? 'never fires: this control is the shift button' : `also mapped to ${v.map((k) => `${mappingLabel(ms[k])} (never fires)`).join(', ')}`),
    )
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, defs, dimmerNames])

  // controls used twice where their pages and shift settings overlap ("any" overlaps with everything): a warning only. Where both apply,
  // shift is checked first, then page: with shift and page > with shift only > page only > neither; the same settings: the first in the list.
  const clashes = useMemo(() => {
    const ms = draft?.mappings ?? []
    const out = new Map<number, string[]>()
    findClashes(ms, draft?.channel ?? 1).forEach((others, i) => out.set(i, others.map((k) => mappingLabel(ms[k]))))
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, defs, dimmerNames])

  // -- learn
  const stopLearning = useCallback(() => {
    setLearning(null)
    api.post('/api/midi/learning', { on: false }).catch(() => {})
  }, [])

  // Learn listens to the engine's one MidiInput: the active controller's mapping, as of its last save, and every device that is on (item 89)
  const learnProblem = (): { why: string; fix: 'use' | null } | null => {
    if (!selected || !draft) return null
    if (!isActive) {
      const now = list?.active ? `the active controller (${list.labels?.[list.active] ?? list.active})` : 'no controller'
      return { why: `This controller isn't the active one: Learn would listen for ${now}.`, fix: 'use' }
    }
    if (!midi?.connected_devices) return { why: midiNotice(midi)?.text ?? 'No MIDI device is connected.', fix: null }
    return null
  }

  const startLearning = async (l: Pick<Learning, 'index' | 'template'>) => {
    const block = learnProblem()
    setLearnBlock(block)
    if (block || !draft) return
    setMoveAsk(null)
    setDetected(null)
    learnSeen.current = false
    setLearning({ ...l, id: null, seconds: 20 }) // waiting for the engine's answer
    // the engine judges what is learnable against the mapping being edited
    const shifts = draft.mappings.filter((m) => m.mode === 'shift').map((m) => ({ type: m.type, number: m.number, channel: channelOf(m, draft.channel) }))
    const row = l.index !== null ? draft.mappings[l.index] : l.template
    const shiftRow = row.mode === 'shift'
    try {
      // the macro of the row: the mode Learn sets depends on what the hardware does on it (item 93)
      const r = await api.post<{ learn_id: number | null; seconds: number }>('/api/midi/learning', { on: true, shifts, shift_row: shiftRow, macro: row.macro })
      if (r.learn_id === null) throw new Error('Learn: no MIDI input is running')
      setLearning((cur) => (cur && cur.id === null ? { ...cur, id: r.learn_id, seconds: r.seconds } : cur))
    } catch (e) {
      setLearning(null)
      fail(e)
    }
  }

  // the engine ends Learn by itself (a capture, or its timeout); this is only a fallback if its state never shows it
  useEffect(() => {
    if (!learning || learning.id === null) return
    const timer = window.setTimeout(() => {
      stopLearning()
      say('Learn: the MIDI input did not answer, click Learn again')
    }, (learning.seconds + 3) * 1000)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [learning?.id])
  useEffect(() => () => void api.post('/api/midi/learning', { on: false }).catch(() => {}), [])

  const commit = (index: number | null, proposal: MidiMappingEntry) =>
    edit((c) => {
      if (index === null) c.mappings.push(proposal)
      else c.mappings[index] = proposal
    })

  // the engine's answer to Learn: the first control it got (taken once, by the id of this Learn), or its timeout
  useEffect(() => {
    if (!learning || learning.id === null || !draft) return
    if (midi?.learn_id !== learning.id) {
      // the state showed this Learn before and doesn't any more: the input was restarted (a save of the active controller)
      if (learnSeen.current) {
        stopLearning()
        say('Learn was interrupted: the MIDI input was restarted. Click Learn again')
      }
      return
    }
    learnSeen.current = true
    const e = midi.learned
    if (e && e.id !== learning.id) {
      // a control captured under another Learn than the one waiting (the ids are set before Learn starts, so this is not expected)
      stopLearning()
      say('Learn: try again')
      return
    }
    if (!e) {
      if (!midi.learning) {
        setLearning(null)
        const open = midi.connected_devices ?? 0
        say(open ? `Learn: ${open} MIDI device${open > 1 ? 's are' : ' is'} open, but no control arrived (does the controller send MIDI, and is its In on?)` : 'Learn: no MIDI device is open, so nothing can arrive')
      }
      return
    }
    setLearning(null)
    if (e.id !== learning.id) return
    const base = learning.index !== null ? draft.mappings[learning.index] : learning.template
    if (!base) return
    // the control and kind, and its own channel only when it isn't the default in channel (item 90), with the mode and
    // encoder the engine found from the hardware (item 93); written at once
    const note = detectedNote(e.detected)
    setDetected(note ? { index: learning.index ?? draftRef.current?.mappings.length ?? 0, text: note } : null)
    commit(learning.index, learnedMapping(base, e, draft.channel))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [midi?.learn_id, midi?.learned, midi?.learning, learning])

  // -- the monitor lights up the row that the control moved
  useEffect(() => {
    const e = midi?.recent?.[0]
    if (!e?.macro) return
    setFlash(e.macro)
    const t = window.setTimeout(() => setFlash(null), 350)
    return () => window.clearTimeout(t)
  }, [midi?.recent?.[0]?.seq]) // eslint-disable-line react-hooks/exhaustive-deps

  // -- files
  const submitName = async (action: 'new' | 'duplicate') => {
    try {
      const res = await api.post<{ name: string }>('/api/controllers', { name: name.trim(), copy_of: action === 'duplicate' ? selected : undefined })
      setPrompt(null)
      await loadList(res.name)
    } catch (e) {
      fail(e)
    }
  }
  const resetFile = async () => {
    if (!selected) return
    try {
      await api.post(`/api/controllers/${encodeURIComponent(selected)}/reset`)
      setPrompt(null)
      version.current++
      await loadList(selected)
      await reload(selected)
    } catch (e) {
      fail(e)
    }
  }
  const deleteFile = async () => {
    if (!selected) return
    try {
      await api.delete(`/api/controllers/${encodeURIComponent(selected)}`)
      setPrompt(null)
      setSelected(null)
      await loadList()
    } catch (e) {
      fail(e)
    }
  }
  const useAndRetry = async () => {
    if (!isActive && !(await useIt())) return
    setLearnBlock(null)
    say('Ready: click Learn again')
  }
  // the active controller is set through the settings (GET and PUT, so unsaved edits in sections 01/02 aren't touched);
  // null closes the MIDI port, so another program can open it
  const setActive = async (name: string | null): Promise<boolean> => {
    try {
      const s = await api.get<Record<string, unknown>>('/api/settings')
      await api.put('/api/settings', { ...s, active_controller: name })
      await loadList(name ?? undefined)
      onActiveChanged(name)
      return true
    } catch (e) {
      fail(e)
      return false
    }
  }
  const useIt = async (): Promise<boolean> => (selected ? setActive(selected) : true)
  const stopUsing = async () => {
    stopLearning()
    if (await setActive(null)) say('No controller is used: the MIDI port is closed')
  }

  // -- rows
  const index = (macro: string) => (draft?.mappings ?? []).map((m, i) => (m.macro === macro && m.mode !== 'shift' ? i : -1)).filter((i) => i >= 0)

  const row = (key: string, label: string, hint: string | undefined, i: number | null, d: MacroDef | null, template: MidiMappingEntry, subgrid = false) => {
    const m = i !== null && draft ? draft.mappings[i] : null
    const waiting = learning !== null && learning.index === i && (i !== null || (learning.template.macro === template.macro && learning.template.mode === template.mode))
    return (
      <MidiMappingRow
        key={key}
        label={label}
        hint={hint}
        index={i}
        mapping={m}
        def={d}
        template={template}
        controllerChannel={draft?.channel ?? 1}
        waiting={waiting}
        ask={waiting && midi?.learn_ask ? midi.learn_ask : null}
        watching={waiting && !!midi?.learn_watching}
        detectedText={i !== null && detected?.index === i ? detected.text : undefined}
        clashes={i !== null ? clashes.get(i) : undefined}
        deadText={i !== null ? dead.get(i) : undefined}
        highlighted={!!flash && flash === m?.macro}
        subgrid={subgrid}
        patch={patch}
        remove={remove}
        onAdd={(number) => edit((c) => void c.mappings.push({ ...template, number }))}
        onLearn={() => (waiting ? stopLearning() : startLearning({ index: i, template }))}
      />
    )
  }

  const macroRows = (macros: MacroDef[]) =>
    macros.flatMap((d) => {
      const idx = index(d.name)
      const template = newMapping({ macro: d.name, mode: defaultMode(d) })
      const label = labelOf(d.name)
      return (idx.length ? idx : [null]).map((i, n) => row(`${d.name}-${n}`, label, undefined, i, d, template, true))
    })

  // in the order of their places on the pages: fader 01, 02, …, then the buttons (item 96)
  const inTab = (t: Tab) =>
    defs.filter((d) => (t === 'scenes' ? d.page === 'scenes' || d.page === 'system' : d.page === t)).sort((a, b) => placeOrder(a.name) - placeOrder(b.name))
  const unknown = (draft?.mappings ?? []).map((m, i) => ({ m, i })).filter(({ m }) => m.macro && !defOf.has(m.macro))

  // -- the controller tab
  const controllerTab = () => {
    if (!draft) return null
    const shift = draft.mappings.findIndex((m) => m.mode === 'shift')
    const set = <K extends keyof ControllerFile>(k: K, v: ControllerFile[K]) => edit((c) => void (c[k] = v))
    const channels = (value: number, onChange: (n: number) => void) => (
      <select value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {Array.from({ length: 16 }, (_, c) => (
          <option key={c} value={c + 1}>
            {c + 1}
          </option>
        ))}
      </select>
    )
    // the default in channel: rows on "default" move along; ones that name the new channel themselves now follow it;
    // ones that name the old channel themselves are asked about. The default out channel follows it unless it was set apart.
    const changeChannel = (to: number) => {
      const from = draft.channel
      if (to === from) return
      const own = draft.mappings.filter((m) => m.channel === from).length
      edit((c) => {
        if (outChannelOf(c) === from) delete c.channel_out
        c.channel = to
        c.mappings.forEach((m) => {
          if (m.channel === to) m.channel = null
        })
      })
      setMoveAsk(own > 0 ? { from, to, count: own } : null)
    }
    const shiftTemplate = newMapping({ mode: 'shift' })
    return (
      <div className="flex flex-col gap-3">
        <div className="grid gap-x-6 gap-y-0.5 wide:grid-cols-2">
          <Row label="Name" hint="The name of this MIDI mapping, as shown in lists">
            <TextInput value={draft.name} onCommit={(v) => set('name', v)} />
          </Row>
          <Row label="Author" hint="Who made this mapping">
            <TextInput value={draft.author} onCommit={(v) => set('author', v)} />
          </Row>
          <Row label="Contact" hint="An email address or a website, for questions about this mapping">
            <TextInput value={draft.contact} onCommit={(v) => set('contact', v)} />
          </Row>
          <Row label="Last edited" hint="Written by the app every time the mapping changes">
            <span className="text-[12px] text-dim">
              {draft.modified ? new Date(draft.modified).toLocaleString() : 'never (as shipped)'}
              {draft.app_version ? ` · PitchControl ${draft.app_version}` : ''}
            </span>
          </Row>
          <Row label="Designed for" hint="The device this mapping was made for, as a note (any MIDI device that is switched on in Connections → MIDI can play it)">
            <TextInput value={draft.designed_for} onCommit={(v) => set('designed_for', v)} placeholder="e.g. Novation Launch Control XL 3" />
          </Row>
          <Row label="Mode" hint="How the device must be set up for this mapping: a template, a MIDI mode, a preset. A note for you, nothing is checked">
            <TextInput value={draft.mode} onCommit={(v) => set('mode', v)} placeholder="e.g. factory template 1" />
          </Row>
          <Row label="Default in channel" hint="The MIDI channel the controls send on. A row says 'default' or names its own channel (some controllers use a channel per track)">
            {channels(draft.channel, changeChannel)}
          </Row>
          <Row label="Default out channel" hint="The channel for LED feedback to the controller: not used yet, the app only stores it. Follows the in channel until you pick another">
            <div className="flex items-center gap-2">
              {channels(outChannelOf(draft), (n) => edit((c) => (n === c.channel ? void delete c.channel_out : void (c.channel_out = n))))}
              <span className="text-[11px] text-dim">for LED feedback, not used yet</span>
            </div>
          </Row>
          <div className="wide:col-span-2">
            <Row label="Description" hint="Notes on the mapping: which controller, what is where">
              <textarea
                key={`${selected}-${draft.description}`}
                className="h-20 w-full resize-y"
                defaultValue={draft.description}
                onBlur={(e) => e.target.value !== draft.description && set('description', e.target.value)}
              />
            </Row>
          </div>
        </div>
        <div>
          <div className="lbl mb-1 text-[10px] text-dim">Shift</div>
          <div className="border border-edge/60" data-tip="The shift button changes what the other buttons do: set 'with shift' / 'no shift' on a mapping">
            {row('shift', 'Shift button', undefined, shift >= 0 ? shift : null, null, shiftTemplate)}
          </div>
        </div>
        {unknown.length > 0 && (
          <div>
            <div className="lbl mb-1 text-[10px] text-dim">Mapped to macros that don't exist (typo, or from a newer version)</div>
            <div className="border border-edge/60">{unknown.map(({ m, i }) => row(`unknown-${i}`, m.macro ?? '?', undefined, i, null, m))}</div>
          </div>
        )}
      </div>
    )
  }

  const prompts = () => (
    <>
      {prompt?.kind === 'name' && (
        <div className="flex flex-wrap items-center gap-1.5 border border-edge p-2">
          <span className="lbl text-[10px] text-dim">{prompt.action === 'new' ? 'New empty controller' : `Duplicate “${selected}”`}</span>
          <input
            type="text"
            autoFocus
            value={name}
            placeholder="file name"
            data-tip="Name of the controller file: letters, digits, space, - _ . ; ⏎ confirms, Esc cancels"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitName(prompt.action)
              else if (e.key === 'Escape') setPrompt(null)
            }}
          />
          <Button primary onClick={() => submitName(prompt.action)} disabled={!name.trim()}>
            {prompt.action === 'new' ? 'Create' : 'Duplicate'}
          </Button>
          <Button onClick={() => setPrompt(null)}>Cancel</Button>
        </div>
      )}
      {prompt?.kind === 'delete' && (
        <div className="flex flex-wrap items-center gap-1.5 border border-ink p-2">
          <span className="text-[11px]">Delete the controller file “{selected}”?</span>
          <Button primary onClick={deleteFile}>
            Delete
          </Button>
          <Button onClick={() => setPrompt(null)}>Cancel</Button>
        </div>
      )}
      {prompt?.kind === 'reset' && (
        <div className="flex flex-wrap items-center gap-1.5 border border-ink p-2">
          <span className="text-[11px]">Reset “{selected}” to the version that comes with the app? Your changes to it are lost.</span>
          <Button primary onClick={resetFile}>
            Reset
          </Button>
          <Button onClick={() => setPrompt(null)}>Cancel</Button>
        </div>
      )}
      {moveAsk && (
        <div className="flex flex-wrap items-center gap-1.5 border border-ink p-2">
          <span className="text-[11px]">
            {moveAsk.count} control{moveAsk.count > 1 ? 's' : ''} {moveAsk.count > 1 ? 'have' : 'has'} channel {moveAsk.from} as {moveAsk.count > 1 ? 'their' : 'its'} own, the old channel of the controller. Move {moveAsk.count > 1 ? 'them' : 'it'} to channel{' '}
            {moveAsk.to} too?
          </span>
          <Button
            primary
            onClick={() => {
              edit((c) =>
                c.mappings.forEach((m) => {
                  if (m.channel === moveAsk.from) m.channel = null
                }),
              )
              setMoveAsk(null)
            }}
            tip="They follow the controller's channel from now on"
          >
            Move {moveAsk.count > 1 ? 'them' : 'it'}
          </Button>
          <Button onClick={() => setMoveAsk(null)} tip={`They stay on channel ${moveAsk.from}`}>
            Leave {moveAsk.count > 1 ? 'them' : 'it'}
          </Button>
        </div>
      )}
    </>
  )

  const names = (list?.available ?? []).slice().sort((a, b) => byName(list?.labels?.[a] ?? a, list?.labels?.[b] ?? b))

  return (
    <Section
      index={sectionIndex}
      title="MIDI mapping"
      className={className}
      bodyClassName="p-3 gap-2"
      right={
        <>
          {midi?.shift && <span className="text-ink">shift held</span>}
          {message && <span>{message}</span>}
        </>
      }
      tip="Which control on the controller drives which macro. Learn listens for the next message; every change is written at once, to your own copy of the mapping file"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <select
          value={selected ?? ''}
          onChange={(e) => setSelected(e.target.value || null)}
          data-tip="The MIDI mapping to edit"
        >
          {names.length === 0 && <option value="">no controller files</option>}
          {names.map((n) => (
            <option key={n} value={n}>
              {list?.labels?.[n] ?? n}
              {list?.active === n ? ' (active)' : ''}
            </option>
          ))}
        </select>
        {selected && (
          <span className="lbl text-[9px] text-dim" data-hint="info" data-tip={origin === 'default' ? 'Comes with the app. Saving keeps your copy in your data folder; the app’s version stays untouched' : origin === 'modified' ? 'Comes with the app, changed by you (your copy is in your data folder)' : 'Your own file'}>
            {origin === 'default' ? 'app' : origin === 'modified' ? 'modified' : 'yours'}
          </span>
        )}
        {selected && !isActive && (
          <Button onClick={useIt} tip="Make this the controller that is listened to (saves the setting)">
            Use this controller
          </Button>
        )}
        {selected && isActive && (
          <Button onClick={stopUsing} tip="No mapping in use: MIDI moves no macros. The devices stay open for the monitor and the routes; switch a device's In off to free it for another program (saves the setting)">
            Stop using it
          </Button>
        )}
        <span className="flex-1" />
        <Button onClick={() => { setName(''); setPrompt({ kind: 'name', action: 'new' }) }} disabled={prompt !== null} tip="Start an empty mapping for another controller">
          New
        </Button>
        <Button onClick={() => { setName(selected ? `${selected} copy` : ''); setPrompt({ kind: 'name', action: 'duplicate' }) }} disabled={!selected || prompt !== null} tip="Copy this mapping under a new name, as a starting point">
          Duplicate
        </Button>
        {origin === 'modified' ? (
          <Button onClick={() => setPrompt({ kind: 'reset' })} disabled={prompt !== null} tip="Back to the version that comes with the app: your changes are deleted (asks first)">
            Reset to default
          </Button>
        ) : (
          <Button onClick={() => setPrompt({ kind: 'delete' })} disabled={!selected || origin !== 'user' || isActive || prompt !== null} tip={origin === 'default' ? 'Comes with the app: it cannot be deleted' : isActive ? 'The active controller cannot be deleted: choose another one first' : 'Delete this controller file (asks first)'}>
            Delete
          </Button>
        )}
      </div>
      {prompts()}
      {learnBlock && (
        <div className="flex flex-wrap items-center gap-1.5 border border-edge px-2 py-1.5 text-[12px]" role="alert">
          <span>{learnBlock.why}</span>
          {learnBlock.fix && (
            <Button primary onClick={useAndRetry} tip="Make this the controller that is listened to, then click Learn again">
              Use this controller
            </Button>
          )}
          <Button onClick={() => setLearnBlock(null)}>Dismiss</Button>
        </div>
      )}

      {!draft ? (
        <p className="text-[12px] text-dim">{names.length ? 'Loading…' : 'No controller files yet: create one with New.'}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`lbl h-7 px-3 text-[11px] ${tab === t.id ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge text-ink'}`}
              >
                {t.label}
                {t.id !== 'controller' && <span className="ml-1.5 font-mono opacity-60">{inTab(t.id).filter((d) => index(d.name).length).length}/{inTab(t.id).length}</span>}
              </button>
            ))}
          </div>
          {tab === 'controller' ? (
            <div className="wide:min-h-0 wide:flex-1 wide:overflow-y-auto">{controllerTab()}</div>
          ) : (
            // the table scrolls inside the section: the page fits the window (item 60)
            <div className="overflow-x-auto wide:min-h-0 wide:flex-1 wide:overflow-y-auto">
              <div className={`grid min-w-[880px] ${MAPPING_COLUMNS} gap-x-2 border border-edge/60`}>
                <div className="lbl sticky top-0 z-10 col-span-full grid grid-cols-subgrid gap-x-2 border-b border-edge bg-panel px-2 py-1 text-[10px] text-dim">
                  <span>Macro</span>
                  <span>Control</span>
                  <span>Channel</span>
                  <span>Behaviour</span>
                  <span>Page</span>
                  <span>Shift</span>
                  <span>Options</span>
                  <span />
                </div>
                {macroRows(inTab(tab))}
              </div>
            </div>
          )}
        </>
      )}
    </Section>
  )
}
