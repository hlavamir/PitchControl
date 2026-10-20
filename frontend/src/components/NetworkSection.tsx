import { useEffect, useState, type MouseEvent } from 'react'
import { api } from '../api'
import { PORT_MAX, PORT_MIN, pinProblem, portProblem, sortAddresses, type NetworkStatus } from '../network'
import { usePolling } from '../usePolling'
import { Button, Section } from './forms'
import { QrCode } from './QrCode'

const POLL_MS = 3000 // the addresses change when the wifi does; a port that was taken may be free again

/**
 * Settings → Network: other devices (a phone, an iPad) on the same network open this UI in their browser.
 * Off by default; only the computer that runs PitchControl changes it. The switch applies at once (no restart);
 * the port and the PIN apply with their button.
 */
export function NetworkSection({ index, desktop }: { index: string; desktop?: boolean }) {
  const [status, setStatus] = useState<NetworkStatus | null>(null)
  const [remote, setRemote] = useState(false) // opened from another device: it can't change these
  const [port, setPort] = useState('')
  const [pin, setPin] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const read = async () => {
    const info = await api.get<{ local?: boolean }>('/api/app-info')
    if (info.local === false) {
      setRemote(true)
      return
    }
    setStatus(await api.get<NetworkStatus>('/api/network'))
  }
  useEffect(() => {
    api.get<{ local?: boolean }>('/api/app-info')
      .then(async (info) => {
        if (info.local === false) return setRemote(true)
        const s = await api.get<NetworkStatus>('/api/network')
        setStatus(s)
        setPort(String(s.port))
        setPin(s.pin)
      })
      .catch((e) => setProblem(String(e.message ?? e)))
  }, [])
  usePolling(read, POLL_MS)

  const save = async (patch: Partial<Pick<NetworkStatus, 'enabled' | 'port' | 'pin'>>) => {
    if (!status) return
    setProblem(null)
    try {
      setStatus(await api.put<NetworkStatus>('/api/network', { enabled: status.enabled, port: status.port, pin: status.pin, ...patch }))
    } catch (e) {
      setProblem(String((e as Error).message ?? e))
    }
  }

  const applyDrafts = () => {
    const bad = portProblem(port) ?? pinProblem(pin)
    if (bad) return setProblem(bad)
    void save({ port: Number(port), pin })
  }

  const openLink = (e: MouseEvent, url: string) => {
    if (!desktop) return // a browser follows the link itself
    e.preventDefault()
    api.post('/api/open-url', { url }).catch(() => undefined)
  }
  const copy = (url: string) => {
    void navigator.clipboard?.writeText(url).then(() => {
      setCopied(url)
      window.setTimeout(() => setCopied((c) => (c === url ? null : c)), 1500)
    })
  }

  const addresses = status ? sortAddresses(status.addresses) : []
  const shown = addresses.find((a) => a.ip === picked) ?? addresses[0]
  const dirty = !!status && (port !== String(status.port) || pin !== status.pin)
  const draftProblem = dirty ? (portProblem(port) ?? pinProblem(pin)) : null

  return (
    <Section
      index={index}
      title="Network"
      right={remote ? 'this device' : status?.enabled ? (status.listening ? 'listening' : status.error ? 'port taken' : 'no address') : 'off'}
      bodyClassName="p-3.5 gap-3"
      tip="Open this UI on a phone or an iPad on the same network. Off unless you turn it on here, on this computer"
    >
      {remote && <p className="text-[12px] leading-snug text-dim">The network settings can only be changed on the computer that runs PitchControl.</p>}
      {!remote && !status && !problem && <p className="lbl text-[11px] text-dim">…</p>}
      {status && (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="flex flex-col gap-1">
              <span className="lbl text-[12px]">Allow other devices on this network</span>
              <span className="lbl text-[10px] text-dim">Applies at once, no restart</span>
            </span>
            <button
              data-hint="toggle"
              data-tip="Let a phone or an iPad on the same wifi or cable network open this UI. Off: only this computer can"
              aria-pressed={status.enabled}
              onClick={() => save({ enabled: !status.enabled })}
              className={`lbl h-[34px] flex-none px-4 text-[12px] ${status.enabled ? 'glow-on bg-ink text-ground' : 'glow-hover border border-edge'}`}
            >
              {status.enabled ? 'On' : 'Off'}
            </button>
          </div>

          <p role="note" className="border border-edge px-2.5 py-2 text-[12px] leading-snug text-dim" data-tip="Everyone who can reach this computer on the network can use the UI while this is on">
            <span className="text-ink">Anyone on this network can then control the lights and change the rig.</span> Don't turn it on on a network you don't trust, such as a venue's shared wifi, without a PIN.
          </p>

          <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
            <label className="flex flex-col gap-1" data-tip={`The port other devices use, ${PORT_MIN} to ${PORT_MAX}. It stays where you put it: if another program has it, it is reported here and PitchControl doesn't move`}>
              <span className="lbl text-[10px] text-dim">Port</span>
              <input type="text" inputMode="numeric" className="w-24" value={port} onChange={(e) => setPort(e.target.value.trim())} onKeyDown={(e) => e.key === 'Enter' && applyDrafts()} />
            </label>
            <label className="flex flex-col gap-1" data-tip="4 to 8 digits, or empty for none. A device on the network enters it once; this computer is never asked">
              <span className="lbl text-[10px] text-dim">PIN (4–8 digits, empty = none)</span>
              <input type="text" inputMode="numeric" autoComplete="off" maxLength={8} className="w-36" value={pin} onChange={(e) => setPin(e.target.value.trim())} onKeyDown={(e) => e.key === 'Enter' && applyDrafts()} />
            </label>
            <Button onClick={applyDrafts} disabled={!dirty || !!draftProblem} tip="Use this port and PIN. Devices that entered the old PIN are asked again">
              Apply
            </Button>
          </div>

          {(problem || draftProblem) && <p className="text-[12px] leading-snug text-ink" role="alert">{problem ?? draftProblem}</p>}
          {status.enabled && status.error && <p className="border border-ink px-2.5 py-2 text-[12px] leading-snug" role="alert">{status.error}</p>}

          {status.enabled && !status.error && addresses.length === 0 && (
            <p className="text-[12px] leading-snug text-dim">No network address found. Connect this computer to the wifi or a cable; the address shows here as soon as there is one.</p>
          )}

          {status.enabled && !status.error && addresses.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-seam pt-3">
              <span className="lbl text-[10px] text-dim">Open one of these on the other device (the one on the same network as it)</span>
              <div className="flex flex-wrap items-start gap-4">
                <ul className="flex min-w-[15rem] flex-1 flex-col gap-1">
                  {addresses.map((a) => (
                    <li key={a.ip} className={`flex items-center gap-2 border px-2 py-1.5 ${shown?.ip === a.ip ? 'border-ink' : 'border-edge'}`}>
                      <span className="min-w-0 flex-1">
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => openLink(e, a.url)}
                          className="block truncate font-mono text-[13px] underline decoration-dotted underline-offset-2"
                          data-tip="Open this address in the browser of this computer to try it"
                        >
                          {a.url}
                        </a>
                        <span className="lbl block truncate text-[10px] text-dim">
                          {a.name}
                          {a.listening ? '' : ' · not listening'}
                        </span>
                      </span>
                      <Button onClick={() => setPicked(a.ip)} disabled={shown?.ip === a.ip} tip="Show the QR code of this address">
                        QR
                      </Button>
                      <Button onClick={() => copy(a.url)} tip="Copy this address">
                        {copied === a.url ? 'Copied' : 'Copy'}
                      </Button>
                    </li>
                  ))}
                </ul>
                {shown && (
                  <div className="flex flex-col items-center gap-1">
                    <QrCode text={shown.url} />
                    <span className="lbl text-[10px] text-dim">Scan with the camera</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
      {!remote && !status && problem && <p className="text-[12px] leading-snug" role="alert">{problem}</p>}
    </Section>
  )
}
