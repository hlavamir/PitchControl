import { useEffect, useState } from 'react'
import type { AudioFrame } from '../api'
import type { EngineConnection } from '../useEngine'

/**
 * The latest audio frame (item 81), once per engine frame while the component is mounted. The frame lives in this hook's
 * own state, so only the band display re-renders at that rate, not the page around it.
 */
export function useAudioFrame(engine: EngineConnection): AudioFrame | null {
  const [frame, setFrame] = useState<AudioFrame | null>(null)
  const { subscribeAudio } = engine
  useEffect(() => subscribeAudio(setFrame), [subscribeAudio])
  return frame
}
