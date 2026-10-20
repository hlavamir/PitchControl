import { encode } from 'uqr'
import { useMemo } from 'react'
import { qrPath } from '../network'

/** A QR code of ``text``: dark modules on a light square with a quiet zone, which is what a phone's camera reads. */
export function QrCode({ text, size = 132, label }: { text: string; size?: number; label?: string }) {
  const { path, modules } = useMemo(() => {
    const qr = encode(text, { ecc: 'M', border: 0 })
    return { path: qrPath(qr.data), modules: qr.size }
  }, [text])
  const quiet = 2
  const span = modules + quiet * 2
  return (
    <svg viewBox={`0 0 ${span} ${span}`} width={size} height={size} role="img" aria-label={label ?? `QR code of ${text}`} shapeRendering="crispEdges" className="flex-none">
      <rect width={span} height={span} fill="#f4f4f0" />
      <path transform={`translate(${quiet} ${quiet})`} d={path} fill="#0e0f12" />
    </svg>
  )
}
