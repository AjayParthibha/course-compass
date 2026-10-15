import { Link } from 'react-router'
import { useCourse } from '../../api/hooks'
import type { Placement, PlanState } from '../../api/types'
import { Button, SectionLabel } from '../../ui'
import { cureviewsUrl } from '../../ui/links'
import { termLabel } from '../../ui/terms'
import { useAdvisor } from '../advisor/store'
import { usePlanEdits } from './edits'
import { checkPrereqs, type CourseCheck, type PrereqCheck } from './prereqs'
import { usePlanUI } from './store'

const statusText = { completed: 'Done', in_progress: 'Taking now', planned: 'Planned' }


function requirementFor(state: PlanState, id: string) {
  for (const r of state.audit.requirements) {
    if (r.filled.includes(id)) return r.label
    for (const c of r.children) if (c.filled.includes(id)) return `${r.label} (${c.label})`
  }
  return null
}

const dot: Record<CourseCheck['state'], string> = {
  done: 'bg-ink',
  in_progress: 'bg-white border border-ink',
  planned: 'bg-white border border-ink',
  late: 'bg-accent',
  missing: 'bg-accent',
}

function courseStatus(c: CourseCheck) {
  const term = c.placement ? termLabel(c.placement.term) : ''
  switch (c.state) {
    case 'done':
      return `Done · ${term}`
    case 'in_progress':
      return `Taking now · ${term}`
    case 'planned':
      return `Planned · ${term}`
    case 'late':
      return `Too late · ${term}`
    default:
      return 'Not in plan'
  }
}

function metText(met: boolean | null) {
  return met === null ? 'needs a check' : met ? 'met' : 'not met yet'
}

type NodeProps = { check: PrereqCheck; onSelect: (id: string) => void; settled?: boolean }

/** `settled` means an enclosing "one of" is already met, so unmet alternatives aren't a problem. */
function PrereqNode({ check, onSelect, settled = false }: NodeProps) {
  if (check.kind === 'flag') {
    return <span className="text-[13px] text-muted italic">Needs: {check.text}</span>
  }
  if (check.kind === 'course') {
    const bad = !settled && (check.state === 'late' || check.state === 'missing')
    const body = (
      <>
        <span className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${bad || check.met ? dot[check.state] : 'border border-line-strong bg-white'}`} />
          <span className="font-mono font-semibold whitespace-nowrap">{check.code}</span>
          {check.concurrent && <span className="text-[12px] text-muted">or same term</span>}
        </span>
        <span className={`text-right ${bad ? 'text-accent' : 'text-muted'}`}>{courseStatus(check)}</span>
      </>
    )
    const placement = check.placement
    return placement ? (
      <button
        type="button"
        onClick={() => onSelect(placement.id)}
        className="flex w-full items-baseline justify-between gap-3 border-0 bg-transparent p-0 text-left text-[13px] hover:underline"
      >
        {body}
      </button>
    ) : (
      <span className="flex items-baseline justify-between gap-3 text-[13px]">{body}</span>
    )
  }
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[12.5px] font-semibold">
        {check.kind === 'all' ? 'All of' : 'One of'}
        <span className={`font-normal ${check.met === false && !settled ? 'text-accent' : 'text-muted'}`}> · {metText(check.met)}</span>
      </span>
      <ul className="m-0 flex list-none flex-col gap-1.5 border-l-2 border-line-soft py-0 pr-0 pl-3">
        {check.items.map((item, i) => (
          <li key={i}>
            <PrereqNode check={item} onSelect={onSelect} settled={settled || (check.kind === 'any' && check.met === true)} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function MoveSelect({ placement, state, onMove }: { placement: Placement; state: PlanState; onMove: (term: string) => void }) {
  const { terms, current_term } = state.plan
  const later = terms.slice(terms.indexOf(current_term) + 1)
  const options = later.includes(placement.term) ? later : [placement.term, ...later]
  return (
    <label className="flex flex-col gap-1 text-[13px]">
      <span className="font-semibold">Move to another term</span>
      <select
        value={placement.term}
        onChange={(e) => onMove(e.target.value)}
        className="h-9 rounded-md border border-[#C3C9BC] bg-white px-2"
      >
        {options.map((t) => (
          <option key={t} value={t}>{termLabel(t, true)}</option>
        ))}
      </select>
    </label>
  )
}

export default function Inspector({ state }: { state: PlanState }) {
  const { selected, select, view } = usePlanUI()
  const setDraft = useAdvisor((s) => s.setDraft)
  const edits = usePlanEdits()
  const placement = state.plan.placements.find((p) => p.id === selected)
  const { data: course, isLoading: courseLoading } = useCourse(placement?.course)

  if (!placement) {
    return (
      <div className="flex flex-col gap-2 p-4 text-[13px] text-muted">
        {view === 'graph' ? (
          <p className="m-0">Drag a course to move it. Every move is checked against your degree rules.</p>
        ) : (
          <p className="m-0">Every move is checked against your degree rules.</p>
        )}
        <p className="m-0">Select a course to see what it needs, what it unlocks and where its information comes from, or to move it.</p>
      </div>
    )
  }

  const byId = new Map(state.plan.placements.map((p) => [p.id, p]))
  const needs = state.edges.filter((e) => e.target === placement.id).map((e) => byId.get(e.source)!)
  const unlocks = state.edges.filter((e) => e.source === placement.id).map((e) => byId.get(e.target)!)
  const req = requirementFor(state, placement.id)
  const issues = state.violations.filter((v) => v.placement_ids.includes(placement.id))
  const movable = placement.status === 'planned'

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
        {movable && <MoveSelect placement={placement} state={state} onMove={(t) => edits.move(placement, t)} />}
      </div>
    )
  }

  const tree = course?.prereqs ? checkPrereqs(course.prereqs, placement, state.plan.placements, state.plan.terms) : null

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
        {tree ? (
          <PrereqNode check={tree} onSelect={select} />
        ) : courseLoading ? (
          <span className="text-[13px] text-muted">Checking prerequisites…</span>
        ) : (
          <>
            {needs.length === 0 && <span className="text-[13px] text-muted">Nothing in this plan</span>}
            {needs.map((p) => (
              <button key={p.id} type="button" onClick={() => select(p.id)} className="flex justify-between border-0 bg-transparent p-0 text-left text-[13px]">
                <span className="font-mono font-semibold">{p.course}</span>
                <span className="text-muted">{statusText[p.status]} · {termLabel(p.term)}</span>
              </button>
            ))}
          </>
        )}
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
        <span className="mt-1.5 flex flex-col gap-0.5 border-t border-line-soft pt-2">
          <span className="text-[12px] text-muted">Student opinion, not official</span>
          <a
            href={cureviewsUrl(placement.course)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Read reviews on CUReviews for ${placement.course} (opens in a new tab)`}
            className="self-start font-semibold text-ink underline underline-offset-3"
          >
            Read reviews on CUReviews
          </a>
        </span>
      </div>

      {movable && (
        <div className="flex flex-col gap-2">
          <MoveSelect placement={placement} state={state} onMove={(t) => edits.move(placement, t)} />
          <Button
            onClick={() => {
              edits.remove(placement)
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
