// The controls of the General page, shared by the laptop page and the phone layout.

// same order as the LCXL3: the bottom knob row, then the faders
export const FADERS = [
  'Strobo Decay',
  'Idle Attack',
  'Mask Param A',
  'Mask Param B',
  'Hue A',
  'Saturation A',
  'Hue B',
  'Saturation B',
  'Audio Reactivity',
  'Strobo',
  'Strobo Brightness',
  'Idle Brightness',
  'Strobo Bright. A',
  'Idle Bright. A',
  'Strobo Bright. B',
  'Idle Bright. B',
]
export const BUTTONS: [string, string, string][] = [
  ['Manual Strobo', 'HOLD', 'Man. strobo'],
  ['Fog Machine', 'HOLD', 'Fog'],
  ['Invert Discoball', 'TGL', 'Invert disco'],
  ['Vertical Symmetry', 'TGL', 'V. symmetry'],
  ['Auto Color Change', 'TGL', 'Auto color'],
  ['Swap Colors', 'TGL', 'Swap colors'],
]
export const MASKS: [string, string, string][] = [
  ['Mask A', 'Gradient', 'A'],
  ['Mask B', 'Back & Forth', 'B'],
  ['Mask C', 'Rotating Line', 'C'],
  ['Mask D', 'Noise', 'D'],
]

export interface SceneInfo {
  index: number
  name: string | null
  exists: boolean
}
