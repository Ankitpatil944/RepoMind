import { useReactFlow, useStore } from '@xyflow/react'
import { useEffect } from 'react'

/** A set of nodes the camera could frame, with the size of that frame. */
export interface FitCandidate {
  /** node ids to frame; empty = everything */
  ids: string[]
  bounds: { width: number; height: number }
}

interface Props {
  /** ordered largest to smallest; the first that stays readable wins */
  candidates: FitCandidate[]
  /** changes whenever the camera should be re-framed (new root, depth, ...) */
  deps: string
}

const PADDING = 0.1
const READABLE = 0.72 // below this zoom card text is hard to read
const FLOOR = 0.75 // zoom used when even the smallest candidate is too big

/** Picks the biggest frame whose text is still legible, then animates there
 *  (instantly for reduced motion). Whatever is left out is a pan away. */
export function FitController({ candidates, deps }: Props) {
  const { fitView } = useReactFlow()
  const width = useStore((s) => s.width)
  const height = useStore((s) => s.height)

  useEffect(() => {
    if (!width || !height || candidates.length === 0) return
    const zoomFor = (c: FitCandidate) =>
      Math.min(
        (width * (1 - 2 * PADDING)) / Math.max(c.bounds.width, 1),
        (height * (1 - 2 * PADDING)) / Math.max(c.bounds.height, 1),
      )
    const chosen = candidates.find((c) => zoomFor(c) >= READABLE) ?? candidates[candidates.length - 1]
    const fits = zoomFor(chosen) >= READABLE
    const reduced = !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const t = setTimeout(() => {
      void fitView({
        ...(chosen.ids.length ? { nodes: chosen.ids.map((id) => ({ id })) } : {}),
        padding: PADDING,
        minZoom: fits ? 0.3 : FLOOR,
        maxZoom: 1,
        duration: reduced ? 0 : 450,
      })
    }, 60)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deps, width, height, candidates])

  return null
}
