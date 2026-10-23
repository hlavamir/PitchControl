// Art-Net / DMX input (item 57), and the sources of the routes (items 58 and 59).

export const ARTNET_DEFAULT_PORT = 6454

export interface ArtNetInputSettings {
  enabled: boolean
  port: number
  adapter: string // an IPv4 address of this computer; empty = all adapters
}

export interface DmxInputSettings {
  enabled: boolean
  device: { serial_number?: string | null; vid?: number | null; pid?: number | null; description?: string | null; port?: string | null }
}

export interface LiveInputSettings {
  artnet: ArtNetInputSettings
  dmx: DmxInputSettings
}

/** One Art-Net universe that has sent something: ``universe`` is the raw wire value (the port address). */
export interface ArtNetUniverse {
  key: string
  universe: number
  sender: string
  pps: number
  age: number // seconds since its last packet
  packets: number
}

export interface LiveInputStatus {
  artnet: {
    enabled: boolean
    listening?: boolean
    error?: string | null
    port?: number
    adapter?: string
    packets?: number
    own_ignored?: number // packets of this app's own Art-Net output, dropped
    universes?: ArtNetUniverse[]
  }
  dmx: {
    enabled: boolean
    connected?: boolean
    error?: string | null
    port?: string | null
    damaged?: number
    pps?: number
    age?: number | null
    packets?: number
  }
}

export interface LiveInputView {
  settings: LiveInputSettings
  adapters: { name: string; ip: string }[]
  status: LiveInputStatus
}

/** A sender that was quiet for this long is shown as gone quiet (its values are still held). */
export const QUIET_AFTER_S = 2

export function portProblem(text: string): string | null {
  const n = Number(text)
  return /^[0-9]+$/.test(text) && n >= 1 && n <= 65535 ? null : 'The port is a number from 1 to 65535'
}

/** "now", "3 s ago", "2 min ago": how long ago the last packet came. */
export function lastSeen(age: number | null | undefined): string {
  if (age == null) return 'never'
  if (age < 1) return 'now'
  if (age < 60) return `${Math.floor(age)} s ago`
  if (age < 3600) return `${Math.floor(age / 60)} min ago`
  return `${Math.floor(age / 3600)} h ago`
}

/** Art-Net port address as net · sub-net · universe, for the tip beside the raw number. */
export function portAddressParts(address: number): string {
  return `net ${(address >> 8) & 0x7f} · sub-net ${(address >> 4) & 0xf} · universe ${address & 0xf}`
}

/** The universes, those still sending first (by number), the quiet ones after them. */
export function sortUniverses(list: ArtNetUniverse[]): ArtNetUniverse[] {
  return [...list].sort((a, b) => Number(a.age > QUIET_AFTER_S) - Number(b.age > QUIET_AFTER_S) || a.universe - b.universe)
}
