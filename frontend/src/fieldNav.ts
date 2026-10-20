/** Moving from field to field on a page by the keys, by where the fields are on the screen. */

export type Zone = 'list' | 'details'
export type FieldDir = 'up' | 'down' | 'left' | 'right'

export interface FieldBox {
  l: number // left and right edge
  r: number
  cy: number // vertical centre
  h: number // height
}

const cx = (b: FieldBox) => (b.l + b.r) / 2

/** Two fields sit on one row when their centres are less than half a field's height apart. */
const sameRow = (a: FieldBox, b: FieldBox) => Math.abs(a.cy - b.cy) < Math.min(a.h, b.h) / 2

/** The horizontal gap between two fields: 0 when they overlap, so fields of one column count as one. */
const gap = (a: FieldBox, b: FieldBox) => Math.max(0, a.l - b.r, b.l - a.r)

/**
 * The field the key moves to, or null when there is none that way.
 *
 * Up / down go to the nearest field above / below, preferring one that overlaps horizontally (the same column),
 * so a second column of fields is not mistaken for the next row. Left / right go along the row; with no neighbour
 * in the row they go to the field on that side that is closest in height, so a column is not a dead end.
 */
export function moveField(boxes: FieldBox[], from: number, dir: FieldDir): number | null {
  const cur = boxes[from]
  if (!cur) return null
  const others = boxes.map((b, j) => ({ b, j })).filter(({ j }) => j !== from)
  const best = (list: { b: FieldBox; j: number }[], score: (b: FieldBox) => number) =>
    list.length ? list.reduce((m, x) => (score(x.b) < score(m.b) ? x : m)).j : null
  if (dir === 'up' || dir === 'down') {
    const way = dir === 'up' ? -1 : 1
    const cand = others.filter(({ b }) => !sameRow(b, cur) && Math.sign(b.cy - cur.cy) === way)
    // a field in another column is only taken when this column has nothing further that way
    return best(cand, (b) => Math.abs(b.cy - cur.cy) + 4 * gap(b, cur) + 0.001 * Math.abs(cx(b) - cx(cur)))
  }
  const way = dir === 'left' ? -1 : 1
  const side = (b: FieldBox) => Math.sign(cx(b) - cx(cur)) === way
  const inRow = others.filter(({ b }) => sameRow(b, cur) && side(b))
  if (inRow.length) return best(inRow, (b) => Math.abs(cx(b) - cx(cur)))
  const across = others.filter(({ b }) => side(b) && gap(b, cur) > 0)
  return best(across, (b) => Math.abs(b.cy - cur.cy))
}
