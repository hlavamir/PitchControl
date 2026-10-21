import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { api } from '../api'
import { Section } from '../components/forms'
import { clientOf, issueUrl } from '../reportProblem'
import { useFieldNav } from '../useFieldNav'

const KEYMAP: [string, string][] = [
  ['W  S', 'Up / down a row, or to the control above / below'],
  ['A  D', 'Left / right, or along a row'],
  ['↑  ↓', 'Change the selected value; in an edited field: the number'],
  ['SHIFT', 'Fine steps; on the Rig page: extends the selection'],
  ['⏎', 'Press the button, load the scene; edit the control (⏎ / Esc stops)'],
  ['SHIFT ⏎', 'Save the selected scene'],
  ['SPACE', 'Rig page: add / remove the current fixture'],
  ['D  →', 'Fixtures and Rig: from the list into the details'],
  ['ESC', 'Cancel a pending change, stop editing, back to the list'],
  ['1 – 9  0', 'Switch page (0 = Help; ⌘ 1 – 9 too in the macOS app)'],
  ['Q  E', 'Previous / next subpage (Control Desk)'],
  ['F', 'Full screen on / off (desktop app)'],
  ['⌘ / CTRL  + −', 'UI scale up / down (= works as +); 0 = 100 %'],
  ['⌘ / CTRL  S', "Save: what the page's Save button does, also while typing"],
  ['ALT  F10', 'Windows app: the menu bar (Alt + letter opens a menu; arrows, ⏎, Esc)'],
]


/** A link that looks like a button, the same everywhere on this page: the desktop app opens it in the default browser. */
function LinkButton({ href, open, label, tip }: { href: string; open: (e: MouseEvent, url: string) => void; label: string; tip: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => open(e, href)}
      data-hint="button"
      data-tip={tip}
      className="lbl glow-hover inline-flex h-8 flex-none items-center border border-edge bg-panel px-3 text-[11px] font-medium text-ink"
    >
      {label} ›
    </a>
  )
}

/**
 * Help (page 0): every key of the UI, About (version, folders, Report a problem, Discord, the project's links) and
 * Support. The menu bar's Help → Keyboard shortcuts and About PitchControl open it.
 */
export function Help({ desktop, version }: { desktop?: boolean; version?: string }) {
  const [folders, setFolders] = useState<{ data_dir?: string; machine_dir?: string; local?: boolean; system?: string }>({})
  useEffect(() => {
    api.get<{ data_dir?: string; machine_dir?: string; local?: boolean; system?: string }>('/api/app-info').then(setFolders).catch(() => undefined)
  }, [])

  // links of the project: the desktop app opens them in the default browser through the backend
  const openLink = (e: MouseEvent, url: string) => {
    if (!desktop || folders.local === false) return // a browser follows the link itself (a phone opens it on the phone)
    e.preventDefault()
    api.post('/api/open-url', { url }).catch(() => window.open(url, '_blank'))
  }

  // Report a problem: a new GitHub issue with the version and this computer's system filled in (reportProblem.ts)
  const reportUrl = issueUrl({ version: version ?? '', system: folders.system ?? '', client: clientOf({ desktop, local: folders.local }), userAgent: navigator.userAgent })

  // keys (rigKeys.ts, useFieldNav.ts): W S A D move over the links and buttons, ⏎ presses the highlighted one
  const pageRef = useRef<HTMLDivElement>(null)
  useFieldNav({ root: pageRef })

  return (
    <div ref={pageRef} className="grid gap-1.5 wide:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-1.5">
      <Section id="help-keyboard" index="01" title="Keyboard" right="no mouse needed" bodyClassName="px-3.5 pb-2.5 pt-1.5" tip="All keys of the UI. Every page can be used with the keys alone: General, Dimmers and Control Desk like a hardware device, the others control by control">
        {KEYMAP.map(([cap, what]) => (
          <div key={cap} className="flex min-h-[25px] items-center gap-3.5 border-b border-[#1d1f21] py-0.5">
            <span className="min-w-16 border border-ink px-1.5 text-center font-mono text-[12px]">{cap}</span>
            <span className="lbl text-[12px]">{what}</span>
          </div>
        ))}
      </Section>
      </div>

      <div className="flex min-w-0 flex-col gap-1.5">
      <Section id="help-about" index="02" title="About" right="version" tip="Which PitchControl this is, where its source and releases are, and where to report a problem">
        <div className="flex items-baseline justify-between gap-3">
          <span className="lbl text-[12px]">PitchControl</span>
          <span className="text-glow font-mono text-[16px]" data-hint="info" data-tip="Version; +N = commits after that release, (abc1234) = the commit, modified = unsaved changes in the source">
            {version || '…'}
          </span>
        </div>
        {folders.data_dir && (
          <div className="mt-3 flex flex-col gap-1 border-t border-seam pt-3 text-[11px]">
            <span className="flex gap-2" data-hint="info" data-tip="Your rigs, fixture types, scenes and settings: what you made or changed (the app's own defaults are never changed)">
              <span className="lbl w-20 flex-none text-[10px] text-dim">Data</span>
              <span className="truncate font-mono">{folders.data_dir}</span>
            </span>
            <span className="flex gap-2" data-hint="info" data-tip="This computer's settings (audio input, MIDI port, outputs, appearance), the macro autosave and the logs">
              <span className="lbl w-20 flex-none text-[10px] text-dim">Computer</span>
              <span className="truncate font-mono">{folders.machine_dir}</span>
            </span>
          </div>
        )}
        <div className="mt-3 flex flex-col gap-2 border-t border-seam pt-3 text-[11px]">
          <span className="flex items-center gap-2">
            <span className="lbl w-20 flex-none text-[10px] text-dim">Feedback</span>
            <span className="flex flex-wrap gap-1.5">
              <LinkButton
                href={reportUrl}
                open={openLink}
                label="Report a problem"
                tip="Open a new issue on GitHub in the browser, with the version and the system filled in: you see and edit everything before you send it. Attach the newest log file (Open logs folder)"
              />
              <LinkButton href="https://discord.gg/4nbBaQDKz4" open={openLink} label="Join the Discord" tip="Open the PitchControl Discord in the browser: questions, help and chat with other users" />
            </span>
          </span>
          <span className="flex gap-2">
            <span className="w-20 flex-none" />
            <span className="lbl text-[10px] leading-snug text-dim">A problem report is a GitHub issue with the version and the system filled in. Attach the newest log.</span>
          </span>
          <span className="flex items-center gap-2">
            <span className="lbl w-20 flex-none text-[10px] text-dim">Project</span>
            <span className="flex flex-wrap gap-1.5">
              <LinkButton href="https://github.com/hlavamir/PitchControl" open={openLink} label="Project on GitHub" tip="Open the project page on GitHub in the browser" />
              <LinkButton
                href="https://github.com/hlavamir/PitchControl/releases"
                open={openLink}
                label="Releases"
                tip="Open the list of releases (downloads for macOS and Windows) on GitHub"
              />
            </span>
          </span>
        </div>
      </Section>
      <Section
        index="03"
        title="Support"
        right="free and open source"
        tip="PitchControl is free (MIT licence). If it helps your shows, you can support its development with a donation"
      >
        <p className="text-[12px] leading-snug text-dim">
          PitchControl is free and open source. If it is useful to you, you can support the work on it and on the PitchPlease lights with a
          donation.
        </p>
        <div className="mt-3">
          <LinkButton href="https://ko-fi.com/zeys_hlvmr" open={openLink} label="Donate on Ko-fi" tip="Open the Ko-fi page of the project in the browser: one-off or monthly donations" />
        </div>
      </Section>
      </div>
    </div>
  )
}
