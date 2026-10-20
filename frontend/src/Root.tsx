import App from './App'
import { useLayout } from './phone'
import { PhoneApp } from './phone/PhoneApp'

/** The laptop UI, or on a phone-sized screen the phone layout (item 46); a phone can ask for the full UI and go back. */
export function Root() {
  const { layout, phoneSize, choose } = useLayout()
  if (layout === 'phone') return <PhoneApp onFullUi={() => choose('full')} />
  return (
    <>
      <App />
      {phoneSize && (
        <button className="lbl glow-on fixed right-2 bottom-2 z-50 h-11 bg-ink px-4 text-[12px] text-ground" onClick={() => choose('phone')}>
          Phone layout
        </button>
      )}
    </>
  )
}
