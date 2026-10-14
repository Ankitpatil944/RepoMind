import { BaseEdge, getSmoothStepPath, type Edge, type EdgeProps } from '@xyflow/react'

export type FlowEdgeData = { active: boolean; dim: boolean; delay: number } & Record<string, unknown>
export type RFEdge = Edge<FlowEdgeData, 'flow'>

/** Smooth-step edge with a packet travelling source → target, so the call
 *  direction is visible without reading arrowheads. Dimmed edges stay still. */
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
  const [path] = getSmoothStepPath({
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
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      {!dim && (
        <circle r={active ? 3.5 : 2.2} className={active ? 'edge-packet edge-packet-active' : 'edge-packet'}>
          <animateMotion
            dur={active ? '1.2s' : '3s'}
            begin={`${delay}s`}
            repeatCount="indefinite"
            path={path}
            calcMode="spline"
            keyTimes="0;1"
            keySplines="0.4 0 0.2 1"
          />
        </circle>
      )}
    </>
  )
}

export const edgeTypes = { flow: FlowEdge }
