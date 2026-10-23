// Help → About → Report a problem: a new GitHub issue with the version and the system filled in. The app sends
// nothing itself; the user sees and edits the issue on GitHub before submitting it.

export const ISSUES_NEW = 'https://github.com/hlavamir/PitchControl/issues/new'

/** Where the UI runs: the desktop app, a browser on the computer that runs PitchControl (from source), another device. */
export type Client = 'desktop' | 'browser' | 'network'

export interface ReportInfo {
  version: string // "1.6.0+3 (abc1234)"
  system: string // the computer that runs PitchControl: "Windows 11 (10.0.26300, AMD64)"
  client: Client
  userAgent?: string // the browser's, for 'browser' and 'network'
}

/** From ``/api/app-info``: ``desktop`` = the server is the desktop app, ``local`` = this UI runs on that computer. */
export function clientOf(info: { desktop?: boolean; local?: boolean }): Client {
  if (info.local === false) return 'network'
  return info.desktop ? 'desktop' : 'browser'
}

const CLIENT_LABEL: Record<Client, string> = {
  desktop: 'desktop app',
  browser: 'browser on the same computer (run from source)',
  network: 'browser on another device on the network',
}

// the newest log is on the computer that runs PitchControl; from source the logs are in the Computer folder's logs/
const LOG_HINT: Record<Client, string> = {
  desktop: 'File → Open logs folder',
  browser: 'the logs folder inside the Computer folder shown in Help → About',
  network: 'on the computer that runs PitchControl: File → Open logs folder',
}

/** The issue text: what we know about the app, then the headings for the user to fill in, then the log request. */
export function issueBody(info: ReportInfo): string {
  const lines = [
    `**PitchControl:** ${info.version || 'unknown'}`,
    `**System:** ${info.system || 'unknown'}`,
    `**Opened from:** ${CLIENT_LABEL[info.client]}`,
  ]
  if (info.client !== 'desktop' && info.userAgent) lines.push(`**Browser:** ${info.userAgent.slice(0, 200)}`)
  return [
    lines.join('\n'),
    '### What happened\n',
    '### What you expected\n',
    '### Steps\n\n1. ',
    `Please attach the newest log file (drag it into this box): ${LOG_HINT[info.client]}. The newest file is the current run.`,
  ].join('\n\n')
}

/** ``…/issues/new?body=…``, title empty; URLSearchParams encodes the line breaks, the stars and the arrows. */
export function issueUrl(info: ReportInfo): string {
  return `${ISSUES_NEW}?${new URLSearchParams({ title: '', body: issueBody(info) })}`
}
