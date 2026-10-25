import { useState } from 'react'
import { api, type MidiDevice } from '../api'
import { deviceState } from '../midiDevices'
import { reconnectLine } from '../reconnect'
import { Section, Toggle } from './forms'

const OUT_TIP = 'For LED feedback to the controller, coming later'

/**
 * Connections → MIDI, section 01 (item 89): the MIDI devices of this computer as a matrix, a row each. In: the app listens
 * to the device (every message of every device that is on goes to the mapping, the routes and the monitor); a device seen
 * for the first time is on. Switching In off lets go of the port at once, so another program can take it. A device that is
 * not plugged in stays in the list, greyed, until it is removed with ×.
 */
export function MidiDevicesSection({ index, devices, className = '' }: { index: string; devices: MidiDevice[]; className?: string }) {
  const [message, setMessage] = useState<string | null>(null)
  const call = (run: () => Promise<unknown>) => {
    run()
      .then(() => setMessage(null))
      .catch((e) => {
        setMessage(String((e as Error)?.message ?? e))
        window.setTimeout(() => setMessage(null), 6000)
      })
  }
  const setIn = (d: MidiDevice, input: boolean) => call(() => api.put(`/api/midi/devices/${encodeURIComponent(d.key)}`, { input }))
  const remove = (d: MidiDevice) => call(() => api.delete(`/api/midi/devices/${encodeURIComponent(d.key)}`))
  const connected = devices.filter((d) => d.state === 'connected').length
  return (
    <Section
      index={index}
      title="MIDI devices"
      icon="in"
      className={className}
      right={<span>{connected} of {devices.length} connected</span>}
      tip="Every MIDI device of this computer. The app listens to the devices whose In is on: a message of any of them moves the mapping, the routes and shows in the MIDI monitor"
    >
      {devices.length === 0 && <div className="py-1 text-[12px] text-dim">No MIDI device found. Plug one in: it is listed here by itself and switched on.</div>}
      {devices.length > 0 && (
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_1rem] items-center gap-x-3 gap-y-1">
          <span />
          <span className="lbl text-[10px] text-dim">In</span>
          <span className="lbl text-[10px] text-dim">Out</span>
          <span />
          {devices.map((d) => {
            const st = deviceState(d)
            const line = reconnectLine(d)
            return (
              <div key={d.key} className={`contents ${st.greyed ? 'opacity-50' : ''}`}>
                <div className="min-w-0" data-tip={d.state === 'error' ? `${d.name}: ${d.error}` : undefined}>
                  <div className="truncate text-[13px]">{d.name}</div>
                  <div className={`truncate text-[11px] ${st.ok === false ? 'text-ink' : 'text-dim'}`}>
                    {st.ok === false && '✕ '}
                    {st.text}
                    {line && ` · ${line}`}
                  </div>
                </div>
                <Toggle checked={d.input} onChange={(v) => setIn(d, v)} tip={d.input ? 'In is on: the app listens to this device. Switch off to let go of it (another program can then use it)' : 'In is off: the app does not listen to this device'} />
                <Toggle checked={d.output} onChange={() => {}} disabled tip={OUT_TIP} />
                {d.state === 'missing' ? (
                  <button type="button" data-hint="button" aria-label={`Remove ${d.name}`} data-tip="Remove this device from the list (it is added again when it is plugged in)" className="glow-hover lbl text-[13px] leading-none text-dim" onClick={() => remove(d)}>
                    ×
                  </button>
                ) : (
                  <span />
                )}
              </div>
            )
          })}
        </div>
      )}
      {message && (
        <div className="mt-1 text-[11px]" role="alert">
          {message}
        </div>
      )}
    </Section>
  )
}
