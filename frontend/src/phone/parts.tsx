import { useContext, type ReactNode } from 'react'
import { FullUiContext } from '../phone'

/** A panel of the phone layout: the laptop's section header, a size up. */
export function PhoneSection({ index, title, right, children }: { index: string; title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex flex-col border border-edge bg-panel">
      <div className="flex min-h-[34px] items-center justify-between gap-2 border-b border-edge px-3 text-[12px]">
        <h2 className="lbl truncate font-medium">
          <span className="font-mono opacity-55">{index} / </span>
          {title}
        </h2>
        <div className="lbl flex items-center gap-2 text-dim">{right}</div>
      </div>
      {children}
    </section>
  )
}

/** The end of a phone page: what stays on the laptop, and the way to the full UI on this phone. */
export function LaptopNote({ className = '' }: { className?: string }) {
  const fullUi = useContext(FullUiContext)
  return (
    <div className={`flex flex-col gap-2 border border-edge px-3 py-3 text-[12px] leading-snug text-dim ${className}`}>
      <span>Fixtures, Rig, Connections, Fog, the Control Desk and Settings stay on the laptop.</span>
      <button className="lbl h-11 self-start border border-edge px-4 text-[12px] text-ink [touch-action:manipulation]" onClick={fullUi}>
        Full UI on this phone
      </button>
    </div>
  )
}
