// The phone layout (item 46): General and Dimmers only, for a phone that opens the UI over the network.
import { createContext, useEffect, useState } from 'react'

// A screen whose shorter side is below this (in CSS px) is a phone, in portrait and in landscape. Phones are
// 320–440 px on their short side, the smallest iPad (mini) is 744 px, a laptop or monitor 768 px and more.
// The screen, not the window: a phone that shows the full UI widens its window to the page (925 px for the Rig
// page), and a narrow browser window on the laptop is still the laptop.
export const PHONE_MAX = 600

export type LayoutChoice = 'phone' | 'full' // 'full': the user asked for the laptop UI on this phone
const CHOICE_KEY = 'pc.layout'

export function isPhoneSize(width: number, height: number): boolean {
  return Math.min(width, height) < PHONE_MAX
}

/** Which UI to show: the phone layout on a phone-sized viewport, unless this device asked for the full UI. */
export function pickLayout(width: number, height: number, choice: LayoutChoice | null): LayoutChoice {
  return isPhoneSize(width, height) && choice !== 'full' ? 'phone' : 'full'
}

function readChoice(): LayoutChoice | null {
  try {
    const v = localStorage.getItem(CHOICE_KEY)
    return v === 'full' ? 'full' : null
  } catch {
    return null
  }
}

/** The layout for this screen; follows a change of screen. ``choose`` remembers the user's choice on this device. */
export function useLayout(): { layout: LayoutChoice; phoneSize: boolean; choose: (c: LayoutChoice) => void } {
  const [size, setSize] = useState(() => ({ w: screen.width, h: screen.height }))
  const [choice, setChoice] = useState<LayoutChoice | null>(readChoice)
  useEffect(() => {
    // the screen changes when the window moves to another monitor (or with the browser's device emulation)
    const onResize = () => setSize({ w: screen.width, h: screen.height })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const choose = (c: LayoutChoice) => {
    try {
      if (c === 'full') localStorage.setItem(CHOICE_KEY, 'full')
      else localStorage.removeItem(CHOICE_KEY)
    } catch {
      // private mode: the choice lasts until the page is reloaded
    }
    setChoice(c === 'full' ? 'full' : null)
  }
  return { layout: pickLayout(size.w, size.h, choice), phoneSize: isPhoneSize(size.w, size.h), choose }
}

/** Switches this phone to the full UI (PhoneApp provides it, LaptopNote's button calls it). */
export const FullUiContext = createContext<() => void>(() => undefined)
