/** Squarified treemap (Bruls et al.). Pure and deterministic so layouts are
 *  stable between renders and easy to test. */
export interface TreemapItem {
  id: string
  value: number
}

export interface TreemapRect {
  id: string
  x: number
  y: number
  w: number
  h: number
}

function worst(row: number[], side: number): number {
  const sum = row.reduce((a, b) => a + b, 0)
  const max = Math.max(...row)
  const min = Math.min(...row)
  const s2 = side * side
  return Math.max((s2 * max) / (sum * sum), (sum * sum) / (s2 * min))
}

export function layoutTreemap(
  items: TreemapItem[],
  width: number,
  height: number,
): TreemapRect[] {
  const clean = items.filter((i) => i.value > 0).sort((a, b) => b.value - a.value || a.id.localeCompare(b.id))
  const total = clean.reduce((a, i) => a + i.value, 0)
  if (!clean.length || width <= 0 || height <= 0 || total <= 0) return []

  // Scale values to area so rectangle area is proportional to value.
  const scale = (width * height) / total
  const areas = clean.map((i) => i.value * scale)
  const out: TreemapRect[] = []

  let x = 0
  let y = 0
  let w = width
  let h = height
  let i = 0

  while (i < clean.length) {
    const side = Math.min(w, h)
    const row: number[] = [areas[i]]
    let j = i + 1
    while (j < clean.length && worst([...row, areas[j]], side) <= worst(row, side)) {
      row.push(areas[j])
      j++
    }
    const rowSum = row.reduce((a, b) => a + b, 0)
    if (w >= h) {
      // lay the row as a column on the left
      const colW = rowSum / h
      let cy = y
      row.forEach((a, k) => {
        const rh = a / colW
        out.push({ id: clean[i + k].id, x, y: cy, w: colW, h: rh })
        cy += rh
      })
      x += colW
      w -= colW
    } else {
      const rowH = rowSum / w
      let cx = x
      row.forEach((a, k) => {
        const rw = a / rowH
        out.push({ id: clean[i + k].id, x: cx, y, w: rw, h: rowH })
        cx += rw
      })
      y += rowH
      h -= rowH
    }
    i = j
  }
  return out
}
