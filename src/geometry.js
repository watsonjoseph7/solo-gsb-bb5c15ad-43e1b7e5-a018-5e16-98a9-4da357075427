/** 前端几何小工具与内置示例。 */

export const EXAMPLE_REQUEST = {
  kerf_width: 0.4,
  parts: [
    {
      id: 'bracket',
      outer: {
        id: 'outer-1',
        points: [
          { x: 0, y: 0 },
          { x: 40, y: 0 },
          { x: 40, y: 20 },
          { x: 0, y: 20 },
        ],
      },
      holes: [
        {
          id: 'mount-hole',
          points: [
            { x: 8, y: 6 },
            { x: 14, y: 6 },
            { x: 14, y: 12 },
            { x: 8, y: 12 },
          ],
        },
        {
          id: 'slot',
          points: [
            { x: 22, y: 8 },
            { x: 34, y: 8 },
            { x: 34, y: 13 },
            { x: 22, y: 13 },
          ],
        },
      ],
    },
  ],
}

export function squarePoints(cx, cy, half) {
  return [
    { x: cx - half, y: cy - half },
    { x: cx + half, y: cy - half },
    { x: cx + half, y: cy + half },
    { x: cx - half, y: cy + half },
  ]
}

export function circlePoints(cx, cy, r, n = 24) {
  const pts = []
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2
    pts.push({
      x: +(cx + r * Math.cos(a)).toFixed(4),
      y: +(cy + r * Math.sin(a)).toFixed(4),
    })
  }
  return pts
}

/** 鞋带公式有符号面积（>0 为 CCW）。 */
export function signedArea(points) {
  let s = 0
  for (let i = 0; i < points.length; i++) {
    const a = points[i]
    const b = points[(i + 1) % points.length]
    s += a.x * b.y - b.x * a.y
  }
  return s / 2
}

/** 多个点列的联合包围盒（用于画布自适应）。 */
export function boundsOf(rings) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const ring of rings) {
    for (const p of ring) {
      if (p.x < minX) minX = p.x
      if (p.y < minY) minY = p.y
      if (p.x > maxX) maxX = p.x
      if (p.y > maxY) maxY = p.y
    }
  }
  if (minX === Infinity) return null
  return { minX, minY, maxX, maxY }
}
