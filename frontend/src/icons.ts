// The app's small line icons (item 67), drawn by components/Icon.tsx: a 12 × 12 grid, 1 px strokes in the current text
// colour (the ink), square ends. An icon says something the text doesn't: the direction of a connection, into the app
// or out of it. The app is the bracket: the input arrow goes into it, the output arrow comes out of it.

export type IconName = 'in' | 'out'

export const ICON_PATHS: Record<IconName, string> = {
  in: 'M0.5 6H7.5M5 3.5L7.5 6L5 8.5M8.5 1.5H11.5V10.5H8.5',
  out: 'M3.5 1.5H0.5V10.5H3.5M4.5 6H11.5M9 3.5L11.5 6L9 8.5',
}

/** What each icon means: its tooltip and its name for a screen reader. */
export const ICON_MEANING: Record<IconName, string> = {
  in: 'input: into the app',
  out: 'output: out of the app',
}
