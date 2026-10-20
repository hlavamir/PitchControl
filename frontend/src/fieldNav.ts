/** Moving from field to field in the Rig page's details by the keys, by where the fields are on the screen. */

export type Zone = 'list' | 'details'
export type FieldDir = 'up' | 'down' | 'left' | 'right'

export interface FieldBox {
  cx: number // centre
  cy: number
  h: number // height
  col: number // 0 = the left column of the details (the only one in a narrow window), 1 = the right one
}

/** Two fields sit on one row when their centres are less than half a field's height apart. */
const sameRow = (a: FieldBox, b: FieldBox) => Math.abs(a.cy - b.cy) < Math.min(a.h, b.h) / 2

/**
 * The field the key moves to, or null when there is none that way.
 *
 * Up / down go to the nearest row above / below in the same column (the closest field horizontally when the row
 * has several). Left / right go along the row, over both columns; with no neighbour in the row they go to the
 * field of the next column that is closest in height, so the right column is not a dead end.
 */
export function moveField(boxes: FieldBox[], from: number, dir: FieldDir): number | null {
  const cur = boxes[from]
  if (!cur) return null
  const others = boxes.map((b, j) => ({ b, j })).filter(({ j }) => j !== from)
  const best = (list: { b: FieldBox; j: number }[], score: (b: FieldBox) => number) =>
    list.length ? list.reduce((m, x) => (score(x.b) < score(m.b) ? x : m)).j : null
  if (dir === 'up' || dir === 'down') {
    const way = dir === 'up' ? -1 : 1
    const cand = others.filter(({ b }) => b.col === cur.col && !sameRow(b, cur) && Math.sign(b.cy - cur.cy) === way)
    if (!cand.length) return null
    const nearest = Math.min(...cand.map(({ b }) => Math.abs(b.cy - cur.cy)))
    const row = cand.filter(({ b }) => Math.abs(b.cy - cur.cy) - nearest < b.h / 2)
    return best(row, (b) => Math.abs(b.cx - cur.cx))
  }
  const way = dir === 'left' ? -1 : 1
  const inRow = others.filter(({ b }) => sameRow(b, cur) && Math.sign(b.cx - cur.cx) === way)
  if (inRow.length) return best(inRow, (b) => Math.abs(b.cx - cur.cx))
  const across = others.filter(({ b }) => (dir === 'left' ? b.col < cur.col : b.col > cur.col))
  return best(across, (b) => Math.abs(b.cy - cur.cy))
}
