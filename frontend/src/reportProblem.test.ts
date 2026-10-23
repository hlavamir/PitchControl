import { describe, expect, it } from 'vitest'
import { ISSUES_NEW, clientOf, issueBody, issueUrl } from './reportProblem'

const info = { version: '1.6.0+3 (abc1234)', system: 'Windows 11 (10.0.26300, AMD64)', client: 'desktop' as const }

describe('issueUrl', () => {
  it('opens a new issue with the version and the system in the body', () => {
    const url = new URL(issueUrl(info))
    expect(`${url.origin}${url.pathname}`).toBe(ISSUES_NEW)
    expect(url.searchParams.get('title')).toBe('')
    const body = url.searchParams.get('body')!
    expect(body).toContain('**PitchControl:** 1.6.0+3 (abc1234)')
    expect(body).toContain('**System:** Windows 11 (10.0.26300, AMD64)')
    expect(body).toContain('**Opened from:** desktop app')
    for (const heading of ['### What happened', '### What you expected', '### Steps']) expect(body).toContain(heading)
    expect(body).toMatch(/attach the newest log file .*File → Open logs folder\. The newest file is the current run\.$/)
  })

  it('encodes what would break the query: + & # line breaks and non-ASCII', () => {
    const url = issueUrl({ ...info, version: '1.6.0+3 (abc1234, modified)', system: 'Linux & co #1 ü' })
    expect(url).not.toMatch(/[\s#]/)
    expect(url.split('?')[1].split('&').map((p) => p.split('=')[0])).toEqual(['title', 'body'])
    const body = new URL(url).searchParams.get('body')!
    expect(body).toContain('1.6.0+3 (abc1234, modified)')
    expect(body).toContain('Linux & co #1 ü')
    expect(body.split('\n').length).toBeGreaterThan(10)
  })

  it('stays well under the URL length a browser or Windows takes (2,000), even with a long user agent', () => {
    const long = { version: '1.10.12-dev (0123456789ab, modified)', system: 'Ubuntu 24.04.1 LTS with a very long name (6.8.0-45-generic, x86_64)', client: 'network' as const, userAgent: 'Mozilla/5.0 '.repeat(60) }
    expect(issueUrl(long).length).toBeLessThan(1500)
    expect(issueUrl(info).length).toBeLessThan(1000)
  })

  it('names the browser and where the log is for a device on the network', () => {
    const body = issueBody({ ...info, client: 'network', userAgent: 'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)' })
    expect(body).toContain('**Opened from:** browser on another device on the network')
    expect(body).toContain('**Browser:** Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)')
    expect(body).toContain('on the computer that runs PitchControl: File → Open logs folder')
    expect(issueBody({ ...info, userAgent: 'WebView2' })).not.toContain('**Browser:**') // the desktop app's own window
  })
})

describe('clientOf', () => {
  it('tells the desktop app, a local browser and another device apart', () => {
    expect(clientOf({ desktop: true, local: true })).toBe('desktop')
    expect(clientOf({ desktop: false, local: true })).toBe('browser')
    expect(clientOf({ desktop: true, local: false })).toBe('network')
    expect(clientOf({ desktop: false, local: false })).toBe('network')
  })
})
