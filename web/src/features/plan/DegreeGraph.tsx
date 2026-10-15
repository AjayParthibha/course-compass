import {
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './graph.css'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Placement, PlanState } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { COL_W, LEFT, NODE_H, NODE_W, ROW_H, TOP, chain, columnAt, graphWidth, initialScrollX, layoutPlan } from './layout'

type CourseData = {
  placement: Placement
  state: 'completed' | 'in_progress' | 'planned' | 'open' | 'ghost'
  selected: boolean
  dim: boolean
  moved: boolean
  problem: boolean
}

type TermData = { label: string; credits: number; current: boolean }

const nodeStyles: Record<CourseData['state'], string> = {
  completed: 'bg-done border border-[#BFC6B8]',
  in_progress: 'bg-white border-[1.5px] border-ink',
  planned: 'bg-white border border-line-strong',
  open: 'bg-paper/70 border-[1.5px] border-dashed border-[#8C9488]',
  ghost: 'bg-transparent border-[1.5px] border-dashed border-accent',
}

const stateLabel: Record<CourseData['state'], string> = {
  completed: 'completed',
  in_progress: 'in progress',
  planned: 'planned',
  open: 'not chosen yet',
  ghost: 'previous position',
}

function nodeLabel(p: Placement, state: CourseData['state'], problem: boolean) {
  const parts = p.course
    ? [p.course, p.title, termLabel(p.term, true), stateLabel[state]]
    : ['Open slot', p.slot_label, termLabel(p.term, true), `${p.credits} credits`]
  if (problem) parts.push('has a problem')
  return parts.filter(Boolean).join(', ')
}

const a11yHelp = 'Press Enter or Space to see details. Planned courses can be moved from the details panel.'

function CourseNode({ data }: NodeProps<Node<CourseData>>) {
  const { placement: p, state, selected, dim, moved, problem } = data
  const code = p.course ?? 'Open slot'
  const title = p.course ? p.title : p.slot_label
  let cls = nodeStyles[state]
  if (moved) cls = 'bg-highlight border-[1.5px] border-ink shadow-[0_2px_0_#171B17]'
  if (selected) cls += ' outline-2 outline-offset-2 outline-accent'
  if (problem) cls += ' ring-2 ring-accent'
  return (
    <div
      className={`box-border flex flex-col gap-0.5 overflow-hidden rounded-[7px] px-2 py-1.5 ${cls} ${dim ? 'border-line-soft! [&>*]:opacity-35' : ''}`}
      style={{ width: NODE_W, height: NODE_H }}
      title={`${code}${title ? ` · ${title}` : ''}`}
    >
      <Handle type="target" position={Position.Left} className="opacity-0!" isConnectable={false} />
      <div className="flex flex-nowrap items-baseline justify-between gap-1 leading-[17px]">
        <span
          className={`shrink-0 font-mono text-[11.5px] font-semibold whitespace-nowrap ${state === 'ghost' ? 'text-accent line-through' : state === 'open' ? 'text-[#5B6358]' : ''}`}
        >
          {code}
        </span>
        <span className="shrink-0 font-mono text-[10px] text-muted">{state === 'ghost' ? 'was' : `${p.credits} cr`}</span>
      </div>
      <span className="line-clamp-2 text-[11px] leading-[14px] text-ink-soft">{title}</span>
      <Handle type="source" position={Position.Right} className="opacity-0!" isConnectable={false} />
    </div>
  )
}

function TermNode({ data }: NodeProps<Node<TermData>>) {
  return (
    <div className="flex items-baseline justify-between" style={{ width: NODE_W }}>
      <span className={`text-[12.5px] ${data.current ? 'font-bold' : 'font-semibold text-muted'}`}>
        {data.label}
      </span>
      <span className="font-mono text-[11px] text-muted">{data.credits} cr</span>
    </div>
  )
}

const nodeTypes = { course: CourseNode, term: TermNode }
const NO_GHOSTS: Placement[] = []

type Props = {
  state: PlanState
  selected?: string | null
  highlight?: Set<string> | null
  moved?: Set<string>
  ghosts?: Placement[]
  readOnly?: boolean
  onSelect?: (id: string | null) => void
  onMove?: (placement: Placement, term: string) => void
}

export default function DegreeGraph({
  state,
  selected = null,
  highlight = null,
  moved,
  ghosts = NO_GHOSTS,
  readOnly,
  onSelect,
  onMove,
}: Props) {
  const { plan, audit, edges } = state
  const wrap = useRef<HTMLDivElement>(null)
  const [startX, setStartX] = useState<number | null>(null)
  const { positions, height } = useMemo(
    () => layoutPlan(plan.placements, plan.terms, audit),
    [plan.placements, plan.terms, audit],
  )
  const problems = useMemo(
    () => new Set(state.violations.filter((v) => v.blocking).flatMap((v) => v.placement_ids)),
    [state.violations],
  )

  const focus = useMemo(() => {
    if (highlight) return highlight
    if (!selected) return null
    const { up, down } = chain(selected, edges)
    return new Set([...up, ...down])
  }, [selected, highlight, edges])

  const builtNodes = useMemo(() => {
    const nodes: Node[] = plan.terms.map((term, col) => ({
      id: `term-${term}`,
      type: 'term',
      position: { x: LEFT + col * COL_W, y: 16 },
      focusable: false,
      data: {
        label: termLabel(term),
        credits: plan.placements.filter((p) => p.term === term).reduce((n, p) => n + p.credits, 0),
        current: term === plan.current_term,
      },
      draggable: false,
      selectable: false,
    }))
    for (const p of plan.placements) {
      const pos = positions.get(p.id)!
      const data: CourseData = {
        placement: p,
        state: p.course ? p.status : 'open',
        selected: p.id === selected,
        dim: (focus != null && !focus.has(p.id)) || (moved != null && moved.size > 0 && !moved.has(p.id)),
        moved: moved?.has(p.id) ?? false,
        problem: problems.has(p.id),
      }
      nodes.push({
        id: p.id,
        type: 'course',
        position: { x: pos.x, y: pos.y },
        data,
        draggable: !readOnly && p.status === 'planned',
        ariaLabel: nodeLabel(p, data.state, data.problem),
        ariaRole: onSelect ? 'button' : 'group',
        domAttributes: { 'aria-roledescription': undefined },
      })
    }
    ghosts.forEach((g, i) => {
      const col = plan.terms.indexOf(g.term)
      const rows = plan.placements.filter((p) => p.term === g.term).length
      nodes.push({
        id: `ghost-${g.id}`,
        type: 'course',
        position: { x: LEFT + col * COL_W, y: TOP + (rows + i) * ROW_H },
        data: { placement: g, state: 'ghost', selected: false, dim: false, moved: false, problem: false },
        draggable: false,
        selectable: false,
        focusable: false,
      })
    })
    return nodes
  }, [plan, positions, selected, focus, moved, ghosts, problems, readOnly, onSelect])

  const [nodes, setNodes, onNodesChange] = useNodesState(builtNodes)
  useEffect(() => setNodes(builtNodes), [builtNodes, setNodes])

  const flowEdges: Edge[] = useMemo(
    () =>
      edges.map((e) => {
        const lit = focus
          ? focus.has(e.source) && focus.has(e.target)
          : !!moved?.size && (moved.has(e.source) || moved.has(e.target))
        const faded = focus != null || !!moved?.size
        return {
          id: `${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          selectable: false,
          style: {
            stroke: lit ? '#171B17' : '#9EA698',
            strokeWidth: lit ? 1.75 : 1.1,
            opacity: faded && !lit ? 0.25 : 1,
          },
        }
      }),
    [edges, focus, moved],
  )

  const graphHeight = Math.max(height + ghosts.length * ROW_H, 360)
  const currentIndex = plan.terms.indexOf(plan.current_term)
  const termCount = plan.terms.length

  // React Flow only reads the viewport once, so measure before mounting it.
  useLayoutEffect(() => {
    if (startX == null && wrap.current) {
      setStartX(initialScrollX(termCount, currentIndex, wrap.current.clientWidth))
    }
  }, [startX, termCount, currentIndex])

  return (
    <div ref={wrap} className="overflow-hidden" style={{ height: graphHeight }}>
      {startX != null && (
        <ReactFlow
          className="degree-graph"
          nodes={nodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeClick={(_, node) => node.type === 'course' && !node.id.startsWith('ghost-') && onSelect?.(node.id)}
          onPaneClick={() => onSelect?.(null)}
          onKeyDown={(e) => {
            const el = e.target as HTMLElement
            const id = el.classList.contains('react-flow__node') ? el.dataset.id : undefined
            if (!onSelect || !id || !plan.placements.some((p) => p.id === id)) return
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onSelect(id)
            } else if (e.key === 'Escape') {
              onSelect(null)
            }
          }}
          onNodeDragStop={(_, node) => {
            const placement = plan.placements.find((p) => p.id === node.id)
            const term = plan.terms[columnAt(node.position.x, plan.terms.length)]
            if (placement && term !== placement.term) onMove?.(placement, term)
            else setNodes(builtNodes)
          }}
          defaultViewport={{ x: -startX, y: 0, zoom: 1 }}
          translateExtent={[
            [0, 0],
            [Math.max(graphWidth(termCount), 600), graphHeight],
          ]}
          nodesConnectable={false}
          elementsSelectable={false}
          deleteKeyCode={null}
          panActivationKeyCode={null}
          ariaLabelConfig={{
            'node.a11yDescription.default': a11yHelp,
            'node.a11yDescription.keyboardDisabled': a11yHelp,
          }}
          zoomOnScroll={false}
          zoomOnDoubleClick={false}
          panOnScroll={false}
          preventScrolling={false}
          minZoom={0.5}
          maxZoom={1.5}
        />
      )}
    </div>
  )
}
