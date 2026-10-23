import { describe, expect, it } from 'vitest'
import jsQR from 'jsqr'
import { encode } from 'uqr'
import { QR_QUIET, isPrivate, pinProblem, portProblem, qrPath, qrPixels, sortAddresses, type NetworkAddress } from './network'

const addr = (ip: string): NetworkAddress => ({ name: ip, ip, url: `http://${ip}:8420`, listening: true })

describe('sortAddresses', () => {
  it('puts the addresses of a home or office network first', () => {
    const sorted = sortAddresses([addr('100.64.0.2'), addr('192.168.1.5'), addr('172.20.0.1'), addr('8.8.4.4'), addr('10.0.0.7')]).map((a) => a.ip)
    expect(sorted).toEqual(['192.168.1.5', '172.20.0.1', '10.0.0.7', '100.64.0.2', '8.8.4.4'])
  })

  it('knows the private ranges', () => {
    expect(['10.1.2.3', '172.16.0.1', '172.31.255.1', '192.168.0.9'].every(isPrivate)).toBe(true)
    expect(['172.15.0.1', '172.32.0.1', '192.169.0.1', '11.0.0.1'].some(isPrivate)).toBe(false)
  })
})

describe('pinProblem', () => {
  it('takes none, or 4 to 8 digits', () => {
    for (const ok of ['', '1234', '12345678']) expect(pinProblem(ok)).toBeNull()
    for (const bad of ['1', '123', '123456789', '12a4', '12 34']) expect(pinProblem(bad)).not.toBeNull()
  })
})

describe('portProblem', () => {
  it('takes 1024 to 65535', () => {
    for (const ok of ['1024', '8420', '65535']) expect(portProblem(ok)).toBeNull()
    for (const bad of ['', '80', '1023', '65536', '84.2', 'abc']) expect(portProblem(bad)).not.toBeNull()
  })
})

describe('qrPath', () => {
  it('draws a square per dark module', () => {
    expect(qrPath([[true, false], [false, true]])).toBe('M0 0h1v1h-1zM1 1h1v1h-1z')
  })
})

describe('the QR code in the app colours, inverted', () => {
  const INK: [number, number, number] = [233, 196, 106] // amber
  const GROUND: [number, number, number] = [15, 16, 17]
  const url = 'http://192.168.1.23:8420'
  const matrix = encode(url, { ecc: 'M', border: 0 }).data

  it('has a quiet zone of four modules', () => {
    expect(QR_QUIET).toBeGreaterThanOrEqual(4)
    const { width, data } = qrPixels(matrix, 4, INK, GROUND)
    expect(width).toBe((matrix.length + 2 * QR_QUIET) * 4)
    for (let i = 0; i < QR_QUIET * 4 * width; i++) expect([...data.slice(i * 4, i * 4 + 3)]).toEqual(GROUND) // the rows above the code
  })

  it('reads back as the address once it is inverted again (light modules on dark, as drawn)', () => {
    const { width, data } = qrPixels(matrix, 6, INK, GROUND)
    // what a scanner that can't read inverted codes would do first: swap light and dark
    const inverted = new Uint8ClampedArray(data.length)
    for (let i = 0; i < data.length; i += 4) {
      const dark = data[i] + data[i + 1] + data[i + 2] < 255 // the ground is dark, the amber module light
      inverted.set(dark ? [255, 255, 255, 255] : [0, 0, 0, 255], i)
    }
    expect(jsQR(inverted, width, width)?.data).toBe(url)
    // and the code as drawn is read by a scanner that tries both polarities
    expect(jsQR(data, width, width, { inversionAttempts: 'attemptBoth' })?.data).toBe(url)
  })
})
