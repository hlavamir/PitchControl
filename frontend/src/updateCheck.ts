// Help → About → Check for updates (item 82): the answer of GET /api/update-check and the sentence shown under the buttons.

export interface UpdateCheck {
  status: 'latest' | 'newer' | 'offline'
  current: string
  latest: string | null
  published: string | null
  notes: string | null
  url: string | null
  page: string | null
  error: string | null
}

/** "2026-11-01T10:00:00Z" -> "2026-11-01" (the date GitHub gives, not shifted into this computer's time zone). */
export function releaseDate(published: string | null): string {
  return /^\d{4}-\d{2}-\d{2}/.test(published ?? '') ? published!.slice(0, 10) : ''
}

/** The line under the buttons for an answer. */
export function updateText(r: UpdateCheck): string {
  if (r.status === 'offline') return `Couldn't reach GitHub: ${r.error || 'no answer'}.`
  if (r.status === 'latest') return `PitchControl ${r.current} is the latest version.`
  const date = releaseDate(r.published)
  return `PitchControl ${r.latest} is available${date ? ` (released ${date})` : ''}.`
}
