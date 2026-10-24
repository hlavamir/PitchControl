import type { EngineConnection } from '../useEngine'
import { BandMeter } from './BandMeter'
import { useAudioFrame } from './useAudioFrame'

/**
 * The band meter fed with the audio frames (item 81): it subscribes on its own, so only this component re-renders at the
 * engine frame rate, not the page around it. Until the first frame arrives it draws the state's bands (15 Hz).
 */
export function LiveBandMeter({ engine, weights, height, tip }: { engine: EngineConnection; weights?: number[]; height?: number | string; tip?: string }) {
  const a = useAudioFrame(engine)
  const state = engine.state
  return <BandMeter bands={a?.bands ?? state?.bands ?? []} max={a?.max} min={a?.min} peaks={a?.peaks ?? state?.band_peaks} weights={weights} height={height} tip={tip} />
}
