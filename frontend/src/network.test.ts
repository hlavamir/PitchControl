import { describe, expect, it } from 'vitest'
import { isPrivate, pinProblem, portProblem, qrPath, sortAddresses, type NetworkAddress } from './network'

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
