import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { api } from '../api'
import { actionFor, clashOf, clashText, filterKeys, groupSkipped, makersOf, modelsOf, type Converted, type ImportKind, type QlcLibrary } from '../fixtureImport'
import type { Origin } from './RigPanel'
import { Button } from './forms'

type Source = 'file' | 'online' | 'installed'

interface Manufacturers {
  commit: string
  manufacturers: { key: string; name: string }[]
}

/**
 * File → Import Fixture → Open Fixture Library… (item 53) and → QLC+… (item 54): pick a fixture (OFL: a .json file, or a
 * manufacturer and fixture from the Open Fixture Library on GitHub; QLC+: a .qxf file, or one of the fixtures in QLC+'s own folders
 * on this computer), read the import report, name the type and save it. Nothing is written before the last button. The conversion,
 * the report and the kept original data are the backend's (``ofl/importer.py``, ``ofl/qlcplus.py``).
 */
export function FixtureImportDialog({
  kind,
  types,
  origins,
  usage,
  openLink,
  onDone,
  onClose,
}: {
  kind: ImportKind
  types: Record<string, unknown>
  origins: Record<string, Origin>
  usage: Record<string, string[]>
  openLink: (e: MouseEvent, url: string) => void
  onDone: (name: string, message: string) => void
  onClose: () => void
}) {
  const [source, setSource] = useState<Source>('file')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [converted, setConverted] = useState<Converted | null>(null)
  const [name, setName] = useState('')
  // online
  const [list, setList] = useState<Manufacturers | null>(null)
  const [maker, setMaker] = useState('')
  const [fixtures, setFixtures] = useState<string[]>([])
  const [filter, setFilter] = useState('')
  const [fixture, setFixture] = useState('')
  const [address, setAddress] = useState('')
  const [fileName, setFileName] = useState('')
  // QLC+'s own folders on this computer
  const [library, setLibrary] = useState<QlcLibrary | null>(null)
  const [qMaker, setQMaker] = useState('')
  const [qFilter, setQFilter] = useState('')
  const [qFile, setQFile] = useState('')
  const [qSearch, setQSearch] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const qlc = kind === 'qlc'
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => root.current?.querySelector<HTMLElement>('[data-first]')?.focus(), [source, converted])

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))
  const work = async (what: string, fn: () => Promise<void>) => {
    setBusy(what)
    setError(null)
    try {
      await fn()
    } catch (e) {
      fail(e)
    } finally {
      setBusy(null)
    }
  }
  const show = (c: Converted) => {
    setConverted(c)
    setName(c.name)
  }

  const pickFile = (file: File | undefined) => {
    if (!file) return
    setFileName(file.name)
    work('Converting…', async () => show(await api.post<Converted>(qlc ? '/api/qlcplus/convert' : '/api/ofl/convert', { text: await file.text(), file: file.name })))
  }

  const openInstalled = () => {
    setSource('installed')
    setError(null)
    if (library) return
    work('Looking for QLC+ on this computer…', async () => setLibrary(await api.get<QlcLibrary>('/api/qlcplus/fixtures')))
  }
  const makers = library ? makersOf(library.fixtures, qSearch) : []
  const models = library && qMaker ? modelsOf(library.fixtures, qMaker, qFilter) : []
  const convertInstalled = (folder: number, file: string) => work('Converting…', async () => show(await api.post<Converted>('/api/qlcplus/convert', { folder, file })))

  const openOnline = () => {
    setSource('online')
    setError(null)
    if (list) return
    work('Asking the Open Fixture Library…', async () => {
      const l = await api.get<Manufacturers>('/api/ofl/manufacturers')
      setList(l)
    })
  }
  const chooseMaker = (key: string) => {
    setMaker(key)
    setFixtures([])
    setFixture('')
    if (!key || !list) return
    work('Reading the manufacturer’s fixtures…', async () => setFixtures((await api.get<{ fixtures: string[] }>(`/api/ofl/manufacturers/${encodeURIComponent(key)}?commit=${list.commit}`)).fixtures))
  }
  const convertOnline = (what: string) =>
    work('Fetching and converting…', async () => show(await api.post<Converted>('/api/ofl/convert', { fixture: what, commit: list?.commit })))

  const clash = converted ? clashOf(name, types, origins, usage) : null
  const action = actionFor(name, converted, clash)
  const save = () =>
    work('Saving…', async () => {
      if (!converted?.type || action.kind === 'blocked') return
      const res = await api.post<{ name: string; replaced: boolean; problems: string[] }>('/api/fixture-types/import', { name: name.trim(), type: converted.type, replace: action.kind === 'replace' })
      const rig = res.problems.length ? ` · rig: ${res.problems.join('; ')}` : ''
      onDone(res.name, `${res.replaced ? 'Replaced' : 'Imported'} “${res.name}”: check it against the manual${rig}`)
    })

  const shown = filterKeys(fixtures, filter)
  const report = converted?.report

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/60 px-3 pt-14 pb-6" role="dialog" aria-label={qlc ? 'Import fixture from QLC+' : 'Import fixture from the Open Fixture Library'}>
      <div
        ref={root}
        className="flex w-full max-w-3xl flex-col border border-ink bg-panel shadow-[0_0_30px_rgb(0_0_0/0.6)]"
        onKeyDown={(e) => {
          // the dialog's own keys: nothing reaches the page behind it (the number keys switch pages)
          e.stopPropagation()
          if (e.key === 'Escape') onClose()
        }}
      >
        <div className="flex h-[26px] flex-none items-center justify-between border-b border-edge px-2.5 text-[11px]">
          <h2 className="lbl font-medium">{qlc ? 'Import fixture / QLC+' : 'Import fixture / Open Fixture Library'}</h2>
          <button className="lbl px-1 text-dim hover:text-ink" onClick={onClose} data-tip="Close without importing (Esc)">
            ✕ close
          </button>
        </div>

        <div className="flex flex-col gap-3 p-3 text-[12px]">
          {!converted ? (
            <>
              <p className="text-dim">
                {qlc
                  ? 'QLC+ (qlcplus.org) is a lighting program with thousands of fixture definitions. PitchControl reads a definition (.qxf) the way the Open Fixture Library does, makes pixels of the heads, converts the modes it can drive, tells you what it left out, and keeps the QLC+ data in the type file.'
                  : 'The Open Fixture Library (open-fixture-library.org) describes thousands of lights. PitchControl converts the modes it can drive, tells you what it left out, and keeps the library’s original data in the type file.'}
              </p>
              <div className="flex gap-1.5">
                {(qlc ? (['file', 'installed'] as const) : (['file', 'online'] as const)).map((s) => (
                  <button
                    key={s}
                    onClick={() => (s === 'online' ? openOnline() : s === 'installed' ? openInstalled() : (setSource('file'), setError(null)))}
                    className={`lbl h-8 px-3 text-[11px] font-medium ${source === s ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge bg-panel text-ink'}`}
                    data-tip={
                      s === 'file'
                        ? qlc
                          ? 'Import a QLC+ fixture definition (.qxf) from any folder: works offline'
                          : 'Import a fixture file (.json) you downloaded from the Open Fixture Library: works offline'
                        : s === 'installed'
                          ? 'Pick one of the fixtures in the folders of QLC+ on this computer'
                          : 'Pick the manufacturer and fixture from the Open Fixture Library on GitHub: needs the internet'
                    }
                  >
                    {s === 'file' ? 'From a file' : s === 'installed' ? 'From QLC+ on this computer' : 'From the library (online)'}
                  </button>
                ))}
              </div>

              {source === 'file' && (
                <div className="flex flex-wrap items-center gap-2">
                  <input ref={fileInput} type="file" accept={qlc ? '.qxf,.xml,application/xml,text/xml' : '.json,application/json'} className="hidden" onChange={(e) => (pickFile(e.target.files?.[0]), (e.target.value = ''))} />
                  <Button
                    primary
                    onClick={() => fileInput.current?.click()}
                    tip={qlc ? 'Choose a QLC+ fixture definition (a .qxf file, e.g. from QLC+’s Fixtures folder or the QLC+ forum)' : 'Choose a fixture file of the Open Fixture Library (a .json file, e.g. from the Download button of a fixture’s page)'}
                  >
                    {qlc ? 'Choose a .qxf file…' : 'Choose a .json file…'}
                  </Button>
                  <span className="text-dim">
                    {fileName || (qlc ? 'A QLC+ fixture definition: a file ending in .qxf' : 'On the fixture’s page of the library, “Download as” → “Open Fixture Library JSON”')}
                  </span>
                </div>
              )}

              {source === 'installed' && (
                <div className="flex flex-col gap-2">
                  {library && library.folders.length === 0 && (
                    <p className="border border-edge p-2 text-dim">
                      No QLC+ fixture folder was found on this computer (QLC+ keeps its definitions in a “Fixtures” folder of its installation and of your user folder). Is QLC+ installed? You can still
                      choose a .qxf file.
                    </p>
                  )}
                  {library && library.folders.length > 0 && (
                    <>
                      <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-2">
                        <span className="lbl text-[11px] text-dim">Manufacturer</span>
                        <span className="flex min-w-0 gap-2">
                          <input data-first type="text" className="w-36 flex-none" placeholder="filter" value={qSearch} onChange={(e) => setQSearch(e.target.value)} data-tip="Type part of the manufacturer's name to narrow the list" />
                          <select
                            className="min-w-0 flex-1"
                            value={qMaker}
                            onChange={(e) => {
                              setQMaker(e.target.value)
                              setQFile('')
                              setQFilter('')
                            }}
                            data-tip="The manufacturers of the fixtures in QLC+'s folders"
                          >
                            <option value="">{`choose one (${makers.length})`}</option>
                            {makers.map((m) => (
                              <option key={m.name} value={m.name}>
                                {m.name} ({m.count})
                              </option>
                            ))}
                          </select>
                        </span>
                        <span className="lbl text-[11px] text-dim">Fixture</span>
                        <span className="flex min-w-0 gap-2">
                          <input type="text" className="w-36 flex-none" placeholder="filter" value={qFilter} disabled={!qMaker} onChange={(e) => setQFilter(e.target.value)} data-tip="Type part of the fixture's name or type to narrow the list" />
                          <select className="min-w-0 flex-1" value={qFile} disabled={!qMaker} onChange={(e) => setQFile(e.target.value)} data-tip="The fixtures of this manufacturer; a folder other than QLC+'s own is named">
                            <option value="">{qMaker ? `${models.length} fixtures` : '—'}</option>
                            {models.map((f) => (
                              <option key={`${f.folder}/${f.file}`} value={`${f.folder}/${f.file}`}>
                                {f.model}
                                {f.type ? ` · ${f.type}` : ''}
                                {library.folders.length > 1 ? ` · ${library.folders[f.folder].label}` : ''}
                              </option>
                            ))}
                          </select>
                        </span>
                      </div>
                      <div>
                        <Button
                          primary
                          disabled={!qFile || !!busy}
                          onClick={() => {
                            const at = qFile.indexOf('/')
                            convertInstalled(Number(qFile.slice(0, at)), qFile.slice(at + 1))
                          }}
                          tip="Read the fixture definition and show what would be imported"
                        >
                          Show the import report
                        </Button>
                      </div>
                      <p className="lbl text-[10px] text-dim">
                        {library.fixtures.length} fixtures in {library.folders.map((f) => f.path).join(' and ')}
                      </p>
                    </>
                  )}
                </div>
              )}

              {source === 'online' && (
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-2">
                    <span className="lbl text-[11px] text-dim">Manufacturer</span>
                    <select data-first value={maker} disabled={!list} onChange={(e) => chooseMaker(e.target.value)} data-tip="The manufacturers of the Open Fixture Library">
                      <option value="">{list ? `choose one (${list.manufacturers.length})` : '…'}</option>
                      {list?.manufacturers.map((m) => (
                        <option key={m.key} value={m.key}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                    <span className="lbl text-[11px] text-dim">Fixture</span>
                    <span className="flex min-w-0 gap-2">
                      <input type="text" className="w-36 flex-none" placeholder="filter" value={filter} disabled={!fixtures.length} onChange={(e) => setFilter(e.target.value)} data-tip="Type part of the fixture's name to narrow the list" />
                      <select
                        className="min-w-0 flex-1"
                        value={fixture}
                        disabled={!fixtures.length}
                        onChange={(e) => setFixture(e.target.value)}
                        data-tip="The fixtures of this manufacturer, by their key in the library"
                      >
                        <option value="">{fixtures.length ? `${shown.length} of ${fixtures.length}` : '—'}</option>
                        {shown.map((k) => (
                          <option key={k} value={k}>
                            {k}
                          </option>
                        ))}
                      </select>
                    </span>
                  </div>
                  <div>
                    <Button primary disabled={!fixture || !!busy} onClick={() => convertOnline(`${maker}/${fixture}`)} tip="Fetch the fixture from the Open Fixture Library and show what would be imported">
                      Show the import report
                    </Button>
                  </div>
                  <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-2 border-t border-seam pt-2">
                    <span className="lbl text-[11px] text-dim">Or its address</span>
                    <span className="flex min-w-0 gap-2">
                      <input
                        type="text"
                        className="min-w-0 flex-1"
                        placeholder="open-fixture-library.org/stairville/led-bar-240-8"
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && address.trim() && !busy && convertOnline(address)}
                        data-tip="The address of a fixture’s page on open-fixture-library.org, or its key (manufacturer/fixture); ⏎ fetches it"
                      />
                      <Button disabled={!address.trim() || !!busy} onClick={() => convertOnline(address)} tip="Fetch the fixture with this address">
                        Fetch
                      </Button>
                    </span>
                  </div>
                  {list && <p className="lbl text-[10px] text-dim">read at commit {list.commit.slice(0, 7)} of the library on GitHub</p>}
                </div>
              )}
            </>
          ) : (
            report && (
              <>
                <div>
                  <p className="text-[14px] font-medium">
                    {report.fixture.manufacturer ? `${report.fixture.manufacturer} ` : ''}
                    {report.fixture.name}
                  </p>
                  <p className="lbl text-[10px] text-dim">
                    import report
                    {report.fixture.url && (
                      <>
                        {' · '}
                        <a href={report.fixture.url} target="_blank" rel="noreferrer" className="underline" onClick={(e) => openLink(e, report.fixture.url!)}>
                          its page in the library ›
                        </a>
                      </>
                    )}
                  </p>
                </div>

                {report.modes.length > 0 && (
                  <div className="flex flex-col gap-px">
                    <p className="lbl text-[10px] text-dim">
                      {report.modes.length} {report.modes.length === 1 ? 'mode' : 'modes'} taken
                    </p>
                    <div className="flex max-h-64 flex-col gap-px overflow-auto">
                    {report.modes.map((m) => (
                      <div key={m.name} className="grid grid-cols-[minmax(0,11rem)_5.5rem_minmax(0,1fr)] gap-3 bg-panel-2 px-2 py-1" data-tip={m.description}>
                        <span className="truncate font-mono">{m.name}</span>
                        <span className="font-mono text-dim">
                          {m.pixels} px · {m.channels} ch
                        </span>
                        <span className="truncate text-dim">{m.description}</span>
                      </div>
                    ))}
                    </div>
                  </div>
                )}

                {report.skipped.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="lbl text-[10px] text-dim">
                      {report.skipped.length} {report.skipped.length === 1 ? 'mode' : 'modes'} left out (PitchControl can’t express them; the original is kept in the file)
                    </p>
                    <div className="flex max-h-40 flex-col gap-1 overflow-auto">
                      {groupSkipped(report.skipped).map((g) => (
                        <p key={g.reason} className="border-l border-ink pl-2">
                          <span className="text-dim">{g.reason}: </span>
                          {g.modes.join(', ')}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
                {!converted.type && <p className="border border-ink p-2">None of this fixture’s modes can be imported, so there is nothing to save.</p>}

                {report.dropped && report.dropped.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="lbl text-[10px] text-dim">in the QLC+ file but not in OFL’s model (kept in the type file under “qlcplus”)</p>
                    <div className="flex max-h-32 flex-col gap-1 overflow-auto">
                      {report.dropped.map((d) => (
                        <p key={d} className="border-l border-edge pl-2 text-dim">
                          {d}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

                {(report.assumptions.length > 0 || report.notes.length > 0) && (
                  <div className="flex flex-col gap-1">
                    <p className="lbl text-[10px] text-dim">assumptions and notes</p>
                    {[...report.assumptions, ...report.notes].map((a) => (
                      <p key={a} className="border-l border-edge pl-2 text-dim">
                        {a}
                      </p>
                    ))}
                  </div>
                )}

                <div className="border border-edge p-2">
                  <p>{report.check}</p>
                  {report.manual.length > 0 && (
                    <p className="mt-1 flex flex-wrap gap-x-3">
                      {report.manual.map((u, i) => (
                        <a key={u} href={u} target="_blank" rel="noreferrer" className="underline" onClick={(e) => openLink(e, u)}>
                          {report.manual.length > 1 ? `Manual ${i + 1}` : 'Manual'} ›
                        </a>
                      ))}
                    </p>
                  )}
                </div>

                {converted.type && (
                  <div className="flex flex-col gap-2">
                    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-2">
                      <span className="lbl text-[11px] text-dim">Type name</span>
                      <input
                        data-first
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && action.kind !== 'blocked' && !busy && !clash && save()}
                        data-tip="The name of the fixture type (its file name, and its name in rigs): letters, digits, space, - _ . ; add the manufacturer if you like"
                      />
                    </div>
                    {clash && <p className="border border-ink p-2">{clashText(clash)} Replace it, or change the name above.</p>}
                    {action.kind === 'blocked' && !clash && name.trim() !== '' && <p className="text-dim">{action.why}</p>}
                  </div>
                )}
              </>
            )
          )}

          {busy && <p className="text-dim">{busy}</p>}
          {error && <p className="border border-ink p-2">{error}</p>}

          <div className="flex flex-wrap gap-1.5 border-t border-seam pt-3">
            {converted && action.kind !== 'blocked' && (
              <Button primary disabled={!!busy} onClick={save} tip={action.kind === 'replace' ? `Overwrite the fixture type “${action.existing.name}” with this one` : 'Save the type: a file in your data folder (fixtures/types); nothing is written before this'}>
                {action.kind === 'replace' ? `Replace “${action.existing.name}”` : 'Import'}
              </Button>
            )}
            {converted && (
              <Button
                onClick={() => {
                  setConverted(null)
                  setError(null)
                }}
                tip="Back to the choice of the fixture"
              >
                Back
              </Button>
            )}
            <Button onClick={onClose} tip="Close without importing (Esc)">
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
