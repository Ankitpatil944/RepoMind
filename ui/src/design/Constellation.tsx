/** Decorative call graph for empty states: edges draw in, packets travel from
 *  the entry node outward. Purely ornamental, hidden from assistive tech. */
const NODES = [
  { id: 'route', x: 24, y: 90, r: 9, hot: true },
  { id: 'auth', x: 100, y: 40, r: 6 },
  { id: 'svc', x: 100, y: 140, r: 6 },
  { id: 'db', x: 180, y: 90, r: 7 },
  { id: 'ext', x: 250, y: 40, r: 5 },
  { id: 'log', x: 250, y: 140, r: 5 },
]
const EDGES: [string, string][] = [
  ['route', 'auth'],
  ['route', 'svc'],
  ['auth', 'db'],
  ['svc', 'db'],
  ['db', 'ext'],
  ['db', 'log'],
]

export function Constellation() {
  const at = (id: string) => NODES.find((n) => n.id === id) as (typeof NODES)[number]
  return (
    <svg width="280" height="180" viewBox="0 0 280 180" className="hero-float" aria-hidden>
      {EDGES.map(([a, b], i) => {
        const A = at(a)
        const B = at(b)
        const d = `M${A.x} ${A.y} C${(A.x + B.x) / 2} ${A.y}, ${(A.x + B.x) / 2} ${B.y}, ${B.x} ${B.y}`
        return (
          <g key={a + b}>
            <path
              d={d}
              fill="none"
              stroke="var(--border-control)"
              strokeWidth="1.5"
              className="hero-draw"
              style={{ animationDelay: `${i * 140}ms` }}
            />
            <circle r="2.5" fill="var(--accent-400)">
              <animateMotion dur="2.6s" begin={`${1.2 + i * 0.4}s`} repeatCount="indefinite" path={d} />
            </circle>
          </g>
        )
      })}
      {NODES.map((n, i) => (
        <circle
          key={n.id}
          cx={n.x}
          cy={n.y}
          r={n.r}
          fill={n.hot ? 'var(--accent-500)' : 'var(--bg-3)'}
          stroke={n.hot ? 'var(--accent-400)' : 'var(--border-control)'}
          strokeWidth="1.5"
          className="node-enter"
          style={{ animationDelay: `${i * 90}ms`, transformBox: 'fill-box', transformOrigin: 'center' }}
        />
      ))}
    </svg>
  )
}
