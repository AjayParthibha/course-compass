import { memo, useMemo } from 'react'
import type { PlanEdge } from '../../api/types'
import { anchorYs, edgeKey, edgePath, gutters, tipPath, type Box } from './graphGeometry'

const STEP_MS = 90
const DRAW_MS = 380

type Props = {
  edges: PlanEdge[]
  boxes: Map<string, Box>
  width: number
  height: number
  /** Edge keys to emphasise; everything else fades. */
  lit: Set<string> | null
  /** Changes whenever a different chain lights up, replaying the draw-in. */
  litKey: string | null
  steps: Map<string, number> | null
}

/** Prerequisite lines, drawn in one SVG under the cards. Purely visual: the cards carry the meaning. */
export default memo(function GraphEdges({ edges, boxes, width, height, lit, litKey, steps }: Props) {
  const paths = useMemo(() => {
    const lines = gutters(boxes.values())
    const ends = anchorYs(edges, boxes)
    return edges.flatMap((e) => {
      const key = edgeKey(e)
      const end = ends.get(key)
      if (!end) return []
      return [{ key, ...edgePath(boxes.get(e.source)!, boxes.get(e.target)!, end.sy, end.ty, lines) }]
    })
  }, [edges, boxes])

  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className="pointer-events-none absolute top-0 left-0 overflow-visible"
      width={width}
      height={height}
    >
      <g fill="none" strokeLinecap="round" strokeWidth={1.25}>
        {paths.map((p) => (
          <path
            key={p.key}
            d={p.d}
            stroke={p.kind === 'backward' ? 'var(--color-accent)' : '#ADB3A8'}
            strokeDasharray={p.kind === 'backward' ? '3 3' : undefined}
            opacity={lit && !lit.has(p.key) ? 0.22 : 1}
            className="transition-opacity duration-200 motion-reduce:transition-none"
          />
        ))}
      </g>
      {lit && lit.size > 0 && (
        <g key={litKey} fill="none" stroke="var(--color-ink)" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75}>
          {paths
            .filter((p) => lit.has(p.key))
            .map((p) => {
              const delay = (steps?.get(p.key) ?? 0) * STEP_MS
              return (
                <g key={p.key}>
                  <path
                    d={p.d}
                    pathLength={1}
                    strokeDasharray="1"
                    className="animate-edge-draw motion-reduce:animate-none"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                  <path
                    d={tipPath(p.tip)}
                    className="animate-edge-tip motion-reduce:animate-none"
                    style={{ animationDelay: `${delay + DRAW_MS - 80}ms` }}
                  />
                </g>
              )
            })}
        </g>
      )}
    </svg>
  )
})
