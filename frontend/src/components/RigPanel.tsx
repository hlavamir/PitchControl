import { useState } from 'react'
import { api } from '../api'
import { Button, Section } from './forms'

/** default: shipped with the app, unchanged; user: the user's own; modified: a shipped one the user changed */
export type Origin = 'default' | 'user' | 'modified'

export interface RigList {
  active: string
  available: string[]
  origins?: Record<string, Origin>
}

type NameAction = 'rename' | 'duplicate' | 'new'

type Prompt =
  | { kind: 'name'; action: NameAction }
  | { kind: 'unsaved'; what: string; then: () => void | Promise<void> }
  | { kind: 'delete' }
  | { kind: 'reset' }

const NAME_TITLE: Record<NameAction, string> = {
  rename: 'Rename rig',
  duplicate: 'Duplicate rig — saves the current state as a new rig and switches to it',
  new: 'New empty rig',
}

/**
 * The rig as a whole (the file): load, save, revert, rename, duplicate, new, delete and the
 * description. Editing the lights in the rig is the job of the fixture list below it.
 */
export function RigPanel({
  index,
  rigs,
  dirty,
  description,
  problems,
  onDescription,
  onDescriptionCommit,
  save,
  revert,
  settle,
  changed,
}: {
  index: string
  rigs: RigList
  dirty: boolean
  description: string
  problems: string[]
  onDescription: (text: string) => void
  onDescriptionCommit: () => void
  save: () => Promise<void>
  revert: () => Promise<void>
  settle: () => Promise<unknown> // resolves once pending live edits reached the engine
  changed: () => void // the active rig or the rig list changed: reload everything
}) {
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const active = rigs.active
  const origin: Origin = rigs.origins?.[active] ?? 'user'

  const close = () => {
    setPrompt(null)
    setError(null)
  }

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await settle()
      await fn()
      close()
      changed()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  /** Run ``then`` directly, or first ask what to do with the unsaved changes. */
  const guard = (what: string, then: () => void | Promise<void>) => {
    setError(null)
    if (dirty) setPrompt({ kind: 'unsaved', what, then })
    else then()
  }

  const askName = (action: NameAction) => {
    setError(null)
    setName(action === 'rename' ? active : action === 'duplicate' ? `${active} copy` : '')
    setPrompt({ kind: 'name', action })
  }

  const load = (target: string) => guard(`loading “${target}”`, () => run(() => api.post('/api/rig/activate', { name: target })))

  const submitName = (action: NameAction) => {
    const body = { name: name.trim() }
    return run(() => api.post(`/api/rig/${action}`, body))
  }

  return (
    <Section
      index={index}
      title="Rig"
      right={
        dirty ? (
          <span className="inline-flex items-center gap-1.5 text-ink" data-hint="info" data-tip="Edits are live in the engine but not written to the rig file yet: Save writes them">
            <span className="dot-on inline-block size-[7px]" />
            unsaved
          </span>
        ) : (
          'saved'
        )
      }
      bodyClassName="p-2.5 gap-2"
      tip="A rig is one file of lights (rigs/ in your data folder). Only one rig is active; the others are kept for other venues or setups"
    >
      <select
        className="w-full"
        value={active}
        onChange={(e) => load(e.target.value)}
        disabled={prompt !== null}
        data-tip="Active rig: choosing another loads it (asks first when this one has unsaved changes)"
      >
        {rigs.available.map((r) => (
          <option key={r} value={r}>
            {r}
            {rigs.origins?.[r] === 'default' ? ' · shipped' : rigs.origins?.[r] === 'modified' ? ' · modified' : ''}
          </option>
        ))}
      </select>
      {origin !== 'user' && (
        <div className="flex items-center justify-between gap-2 text-[11px] text-dim" data-hint="info" data-tip={origin === 'default' ? 'This rig comes with the app. Saving it keeps your copy in your data folder; the app’s version stays untouched' : 'A rig that comes with the app, changed by you: your copy is in your data folder. Reset to default deletes it'}>
          <span className="lbl min-w-0 text-[10px]">{origin === 'default' ? 'shipped with the app' : 'shipped · modified by you'}</span>
          {origin === 'modified' && prompt === null && (
            <button className="lbl glow-hover h-[18px] flex-none border border-edge px-2 text-[10px] whitespace-nowrap text-ink" onClick={() => setPrompt({ kind: 'reset' })}>
              Reset
            </button>
          )}
        </div>
      )}
      <textarea
        rows={5}
        className="w-full resize-y text-[11px] leading-snug"
        placeholder="description"
        data-tip="Free text about this rig (venue, setup); saved in the rig file"
        value={description}
        onChange={(e) => onDescription(e.target.value)}
        onBlur={onDescriptionCommit}
      />

      {prompt === null && (
        <>
          <div className="flex gap-1.5">
            <Button onClick={save} primary disabled={!dirty} tip="Write the rig, with all edits, to its file in your data folder (rigs/)">
              Save
            </Button>
            <Button onClick={revert} disabled={!dirty} tip="Throw away the unsaved edits and reload the rig from its file">
              Revert
            </Button>
            {/* destructive: kept apart at the right end */}
            <span className="ml-auto">
              <Button
                onClick={() => setPrompt({ kind: 'delete' })}
                disabled={rigs.available.length < 2 || origin !== 'user'}
                tip={origin !== 'user' ? 'A rig that comes with the app cannot be deleted (Reset to default removes your changes to it)' : "Delete this rig's file (asks first); the last rig cannot be deleted"}
              >
                Delete
              </Button>
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Button onClick={() => askName('rename')} tip="Rename the rig file (letters, digits, space, - _ .; unique ignoring case)">
              Rename
            </Button>
            <Button onClick={() => askName('duplicate')} tip="Save as: the current state, unsaved edits included, becomes a new rig and the active one">
              Duplicate
            </Button>
            <Button onClick={() => guard('creating a new rig', () => askName('new'))} tip="Create a new empty rig and make it active">
              New
            </Button>
          </div>
        </>
      )}

      {prompt?.kind === 'name' && (
        <div className="flex flex-col gap-1.5 border border-edge p-2">
          <span className="lbl text-[10px] text-dim">{NAME_TITLE[prompt.action]}</span>
          <input
            type="text"
            className="w-full"
            autoFocus
            onFocus={(e) => e.currentTarget.select()}
            value={name}
            placeholder="rig name"
            data-tip="Name of the rig file: letters, digits, space, - _ . ; ⏎ confirms, Esc cancels"
            onChange={(e) => {
              setName(e.target.value)
              setError(null)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitName(prompt.action)
              else if (e.key === 'Escape') close()
            }}
          />
          <div className="flex gap-1.5">
            <Button onClick={() => submitName(prompt.action)} primary disabled={!name.trim()}>
              {prompt.action === 'new' ? 'Create' : prompt.action === 'rename' ? 'Rename' : 'Duplicate'}
            </Button>
            <Button onClick={close}>Cancel</Button>
          </div>
        </div>
      )}

      {prompt?.kind === 'unsaved' && (
        <div className="flex flex-col gap-1.5 border border-ink p-2">
          <span className="text-[11px]">
            “{active}” has unsaved changes. Save them before {prompt.what}?
          </span>
          <div className="flex gap-1.5">
            <Button
              primary
              onClick={async () => {
                await save()
                setPrompt(null)
                await prompt.then()
              }}
            >
              Save
            </Button>
            <Button
              onClick={async () => {
                setPrompt(null)
                await prompt.then()
              }}
            >
              Discard
            </Button>
            <Button onClick={close}>Cancel</Button>
          </div>
        </div>
      )}

      {prompt?.kind === 'delete' && (
        <div className="flex flex-col gap-1.5 border border-ink p-2">
          <span className="text-[11px]">
            Delete the rig file “{active}”{dirty ? ' and its unsaved changes' : ''}? The next rig is loaded.
          </span>
          <div className="flex gap-1.5">
            <Button primary onClick={() => run(() => api.delete('/api/rig'))}>
              Delete
            </Button>
            <Button onClick={close}>Cancel</Button>
          </div>
        </div>
      )}

      {prompt?.kind === 'reset' && (
        <div className="flex flex-col gap-1.5 border border-ink p-2">
          <span className="text-[11px]">
            Reset “{active}” to the version that comes with the app? Your changes to it{dirty ? ', including the unsaved ones,' : ''} are lost.
          </span>
          <div className="flex gap-1.5">
            <Button primary onClick={() => run(() => api.post('/api/rig/reset'))}>
              Reset
            </Button>
            <Button onClick={close}>Cancel</Button>
          </div>
        </div>
      )}

      {error && <p className="text-[11px] text-ink">✕ {error}</p>}
      {problems.length > 0 && (
        <ul className="list-disc pl-5 text-[11px] text-ink">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </Section>
  )
}
