// Settings → Network: other devices (a phone, an iPad) opening the UI over the network.

export interface NetworkAddress {
  name: string // the adapter
  ip: string
  url: string
  listening: boolean
}

export interface NetworkStatus {
  enabled: boolean
  port: number
  pin: string // empty = none
  listening: boolean
  error: string | null // the port is taken, say
  addresses: NetworkAddress[]
}

/** An address of a home or office network (10.x, 172.16–31.x, 192.168.x): the one a phone on the same wifi reaches. */
export function isPrivate(ip: string): boolean {
  const [a, b] = ip.split('.').map(Number)
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
}

/** The addresses with the private ones first (a VPN or a virtual adapter after them), each group in its own order. */
export function sortAddresses(list: NetworkAddress[]): NetworkAddress[] {
  return [...list].sort((x, y) => Number(isPrivate(y.ip)) - Number(isPrivate(x.ip)))
}

export const PIN_MIN = 4
export const PIN_MAX = 8
export const PORT_MIN = 1024
export const PORT_MAX = 65535

/** What is wrong with a PIN, or null: empty (no PIN) or 4 to 8 digits. */
export function pinProblem(pin: string): string | null {
  if (pin === '' || (/^[0-9]+$/.test(pin) && pin.length >= PIN_MIN && pin.length <= PIN_MAX)) return null
  return `The PIN is ${PIN_MIN} to ${PIN_MAX} digits, or empty for none`
}

export function portProblem(text: string): string | null {
  const n = Number(text)
  return /^[0-9]+$/.test(text) && n >= PORT_MIN && n <= PORT_MAX ? null : `The port is a number from ${PORT_MIN} to ${PORT_MAX}`
}

/** The empty border round a QR code, in modules: the standard asks for four, and a scanner that is given less may not find the code. */
export const QR_QUIET = 4

/** The code as pixels, ``scale`` pixels a module, the quiet zone included (RGBA, row by row): modules in ``module``, the rest in ``ground``. */
export function qrPixels(matrix: boolean[][], scale: number, module: [number, number, number], ground: [number, number, number]): { width: number; data: Uint8ClampedArray } {
  const width = (matrix.length + 2 * QR_QUIET) * scale
  const data = new Uint8ClampedArray(width * width * 4)
  for (let y = 0; y < width; y++)
    for (let x = 0; x < width; x++) {
      const my = Math.floor(y / scale) - QR_QUIET
      const mx = Math.floor(x / scale) - QR_QUIET
      const [r, g, b] = matrix[my]?.[mx] ? module : ground
      data.set([r, g, b, 255], (y * width + x) * 4)
    }
  return { width, data }
}

/** One SVG path for the dark modules of a QR code (a unit square each). */
export function qrPath(matrix: boolean[][]): string {
  let d = ''
  matrix.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) d += `M${x} ${y}h1v1h-1z`
    }),
  )
  return d
}
