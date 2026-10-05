import { Link } from 'react-router'
import { useCourse, usePlanOps } from '../../api/hooks'
import type { PlanState } from '../../api/types'
import { Button, SectionLabel } from '../../ui'
import { termLabel } from '../../ui/terms'
import { useAdvisor } from '../advisor/store'
import { usePlanUI } from './store'

const statusText = { completed: 'Done', in_progress: 'Taking now', planned: 'Planned' }

function requirementFor(state: PlanState, id: string) {
  for (const r of state.audit.requirements) {
    if (r.filled.includes(id)) return r.label
    for (const c of r.children) if (c.filled.includes(id)) return `${r.label} (${c.label})`
  }
  return null
}

export default function Inspector({ state }: { state: PlanState }) {
  const { selected, select } = usePlanUI()
  const setDraft = useAdvisor((s) => s.setDraft)
  const ops = usePlanOps()
  const placement = state.plan.placements.find((p) => p.id === selected)
  const { data: course } = useCourse(placement?.course)

  if (!placement) {
    return (
      <div className="flex flex-col gap-2 p-4 text-[13px] text-muted">
        <p className="m-0">Drag a course to move it. Every move is checked against your degree rules.</p>
        <p className="m-0">Click a course to see what it needs, what it unlocks and where its information comes from.</p>
      </div>
    )
  }

  const byId = new Map(state.plan.placements.map((p) => [p.id, p]))
  const needs = state.edges.filter((e) => e.target === placement.id).map((e) => byId.get(e.source)!)
  const unlocks = state.edges.filter((e) => e.source === placement.id).map((e) => byId.get(e.target)!)
  const req = requirementFor(state, placement.id)
  const later = state.plan.terms.slice(state.plan.terms.indexOf(state.plan.current_term) + 1)
  const issues = state.violations.filter((v) => v.placement_ids.includes(placement.id))

  if (!placement.course) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <div>
          <span className="font-mono text-[13px] font-semibold">Open slot · {placement.credits} cr</span>
          <h3 className="m-0 text-lg font-extrabold">{placement.slot_label}</h3>
          <span className="text-[13px] text-muted">{termLabel(placement.term)}</span>
        </div>
        <Link
          to={`/explore/${placement.slot}?term=${placement.term}&placement=${placement.id}`}
          className="inline-flex h-9 items-center justify-center rounded-md bg-ink px-3.5 font-semibold text-paper no-underline hover:text-paper"
        >
          See options for this slot
        </Link>
        <Button onClick={() => setDraft(`What should I take for the ${placement.slot_label?.toLowerCase()} slot in ${termLabel(placement.term, true)}?`)}>
          Ask the advisor
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <span className="font-mono text-[13px] font-semibold">
          {placement.course} · {placement.credits} cr
        </span>
        <h3 className="m-0 text-lg leading-tight font-extrabold">{placement.title}</h3>
        <span className="text-[13px] text-muted">
          {termLabel(placement.term)} · {req ? `counts toward ${req}` : 'not counted toward a requirement'}
        </span>
      </div>

      {issues.map((v) => (
        <p key={v.message} className="m-0 rounded-md bg-accent/10 px-3 py-2 text-[13px] text-accent">
          {v.message}
        </p>
      ))}

      <div className="flex flex-col gap-1.5">
        <SectionLabel>Needs</SectionLabel>
        {needs.length === 0 && <span className="text-[13px] text-muted">Nothing in this plan</span>}
        {needs.map((p) => (
          <button key={p.id} type="button" onClick={() => select(p.id)} className="flex justify-between border-0 bg-transparent p-0 text-left text-[13px]">
            <span className="font-mono font-semibold">{p.course}</span>
            <span className="text-muted">{statusText[p.status]} · {termLabel(p.term)}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-1.5">
        <SectionLabel>Unlocks</SectionLabel>
        {unlocks.length === 0 && <span className="text-[13px] text-muted">Nothing else in this plan</span>}
        {unlocks.map((p) => (
          <button key={p.id} type="button" onClick={() => select(p.id)} className="flex justify-between border-0 bg-transparent p-0 text-left text-[13px]">
            <span className="font-mono font-semibold">{p.course}</span>
            <span className="text-muted">{termLabel(p.term)}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-1 text-[13px]">
        <SectionLabel>Where this comes from</SectionLabel>
        <span>Cornell Class Roster{course?.prereqs_reviewed ? '' : ' · prerequisites not yet reviewed by us'}</span>
        {course?.prereq_text && <span className="text-muted">Listed prereqs: {course.prereq_text}</span>}
        <span className="text-muted">
          Offered: {course?.typical_seasons.length ? course.typical_seasons.map((s) => (s === 'FA' ? 'fall' : s === 'SP' ? 'spring' : s)).join(', ') : 'unknown'}
        </span>
      </div>

      {placement.status === 'planned' && (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-[13px]">
            <span className="font-semibold">Move to another term</span>
            <select
              value={placement.term}
              onChange={(e) => ops.mutate([{ op: 'move', placement_id: placement.id, term: e.target.value }])}
              className="h-9 rounded-md border border-[#C3C9BC] bg-white px-2"
            >
              {later.map((t) => (
                <option key={t} value={t}>{termLabel(t, true)}</option>
              ))}
            </select>
          </label>
          <Button
            onClick={() => {
              ops.mutate([{ op: 'remove', placement_id: placement.id }])
              select(null)
            }}
          >
            Remove from plan
          </Button>
        </div>
      )}
      <Button variant="link" className="self-start" onClick={() => setDraft(`Tell me about ${placement.course} in my plan.`)}>
        Ask the advisor about it
      </Button>
    </div>
  )
}
