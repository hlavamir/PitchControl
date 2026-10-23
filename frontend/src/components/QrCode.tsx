import { encode } from 'uqr'
import { useMemo } from 'react'
import { QR_QUIET, qrPath } from '../network'

/**
 * A QR code of ``text`` in the app's colours, inverted: modules in the ink (the accent: amber by default, it follows the theme)
 * on the dark ground, with the standard quiet zone. The current iPhone and Android cameras read inverted codes; some older
 * or third-party scanners don't.
 */
export function QrCode({ text, size = 132, label }: { text: string; size?: number; label?: string }) {
  const { path, modules } = useMemo(() => {
    const qr = encode(text, { ecc: 'M', border: 0 })
    return { path: qrPath(qr.data), modules: qr.size }
  }, [text])
  const quiet = QR_QUIET
  const span = modules + quiet * 2
  return (
    <svg viewBox={`0 0 ${span} ${span}`} width={size} height={size} role="img" aria-label={label ?? `QR code of ${text}`} shapeRendering="crispEdges" className="flex-none">
      <rect width={span} height={span} className="fill-ground" />
      <path transform={`translate(${quiet} ${quiet})`} d={path} className="fill-ink" />
    </svg>
  )
}
