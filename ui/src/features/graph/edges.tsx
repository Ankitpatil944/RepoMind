import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from '@xyflow/react'

export type FlowEdgeData = {
  active: boolean
  dim: boolean
  delay: number
  /** source line of the call, shown as an `L42` chip while the edge is highlighted */
  line?: number | null
} & Record<string, unknown>
export type RFEdge = Edge<FlowEdgeData, 'flow'>

/** Smooth-step edge: a dark underlay, a flowing dashed line on top, and a packet
 *  travelling source -> target so the call direction is visible without
 *  arrowheads. Highlighted edges flow faster and carry a line-number chip. */
export function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  data,
}: EdgeProps<RFEdge>) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 10,
  })
  const active = !!data?.active
  const dim = !!data?.dim
  const delay = data?.delay ?? 0
  return (
    <>
      <path d={path} fill="none" stroke="var(--bg-0)" strokeWidth={active ? 5 : 4} strokeLinecap="round" />
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      {!dim && (
        <circle r={active ? 3.5 : 2.2} className={active ? 'edge-packet edge-packet-active' : 'edge-packet'}>
          <animateMotion
            dur={active ? '0.9s' : '3.2s'}
            begin={`${delay}s`}
            repeatCount="indefinite"
            path={path}
            calcMode="spline"
            keyTimes="0;1"
            keySplines="0.4 0 0.2 1"
          />
        </circle>
      )}
      {active && data?.line != null && (
        <EdgeLabelRenderer>
          <span
            className="pointer-events-none absolute rounded-[4px] border border-sage-border bg-bg-1 px-1.5 font-mono text-[10.5px] text-sage"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            L{data.line}
          </span>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

export const edgeTypes = { flow: FlowEdge }
