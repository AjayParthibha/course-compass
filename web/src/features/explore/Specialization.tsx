import { useId, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useAreas, useCandidates, useSetApproval } from '../../api/hooks'
import type { Area, Candidate, PlanState, SlotAreas, SlotCandidates } from '../../api/types'
import { Button, Tag } from '../../ui'
import { cureviewsUrl } from '../../ui/links'
import { termLabel } from '../../ui/terms'
import { useAdvisor } from '../advisor/store'
import { areaHint, basisLabel } from './reasons'

type CourseSummary = Candidate['course']

type Props = {
  slotId: string
  term: string
  placementId: string | null
  state: PlanState | undefined
  canPick: boolean
  onPick: (code: string) => void
  onHide: (course: CourseSummary) => void
  hiding: string[]
}

const SHOWN = 8

/**
 * Options for a rule whose courses must share a subject (the external specialization).
 * The real decision is the area, so the student picks one first, then courses within it.
 * The chosen area lives in the URL (?area=ORIE); an empty value means "show me the areas".
 */
export default function Specialization({ slotId, term, placementId, state, ...rest }: Props) {
  const [params, setParams] = useSearchParams()
  const { data: areas, error } = useAreas(slotId, term, placementId)
  const asked = params.get('area')
  const area = asked === '' ? null : (asked ?? areas?.chosen ?? null)
  const setArea = (subject: string | null) =>
    setParams((p) => {
      const next = new URLSearchParams(p)
      next.set('area', subject ?? '')
      return next
    })

  return (
    <div className="flex flex-col gap-4">
      {areas && <Rule areas={areas} />}
      {state && <Progress slotId={slotId} placementId={placementId} state={state} area={area} />}
      {error && <p className="m-0 text-accent">{error.message}</p>}
      {!areas && !error && <p className="m-0 text-muted">Finding areas…</p>}
      {areas &&
        (area ? (
          <AreaCourses
            slotId={slotId}
            term={term}
            placementId={placementId}
            areas={areas}
            area={area}
            onChange={() => setArea(null)}
            {...rest}
          />
        ) : (
          <AreaList areas={areas} term={term} onPick={setArea} />
        ))}
    </div>
  )
}

function Rule({ areas }: { areas: SlotAreas }) {
  const caps = Object.entries(areas.caps)
  return (
    <div className="flex max-w-3xl flex-col gap-1">
      <p className="m-0 text-muted">
        {areas.needed} courses from one subject
        {caps.map(([s, n]) => `, at most ${n} cross-listed with ${s}`).join('')}. Pick the area first, then the
        courses.
      </p>
      {areas.approval && <Approval slotId={areas.slot_id} approval={areas.approval} />}
    </div>
  )
}

/**
 * The catalog lets an advisor approve a mix of subjects on one topic. Saying so drops the
 * one-subject rule for this student, so the slot lists every course that fits instead of areas.
 */
export function Approval({ slotId, approval }: { slotId: string; approval: NonNullable<SlotCandidates['approval']> }) {
  const set = useSetApproval()
  const toggle = () => set.mutate({ requirement: slotId, approved: !approval.approved })
  return (
    <p role="status" className="m-0 flex flex-wrap items-baseline gap-x-2 text-[13.5px] text-muted">
      {approval.approved ? (
        <span title={approval.label}>Your advisor approved a mix of subjects on one topic, so courses from any subject can count here.</span>
      ) : (
        <span>A mix of subjects on one topic can count with your advisor’s approval.</span>
      )}
      <Button variant="link" disabled={set.isPending} onClick={toggle}>
        {approval.approved ? 'Back to one subject' : 'My advisor approved a mix'}
      </Button>
      {set.error && <span className="text-accent">{set.error.message}</span>}
    </p>
  )
}

/** The slots this rule fills across the plan, so picking one is seen as part of three. */
function Progress({ slotId, placementId, state, area }: { slotId: string; placementId: string | null; state: PlanState; area: string | null }) {
  const order = state.plan.terms
  const parts = state.plan.placements
    .filter((p) => (p.slot === slotId && !p.course) || p.counts_as.includes(slotId))
    .sort((a, b) => order.indexOf(a.term) - order.indexOf(b.term))
  if (parts.length < 2) return null
  return (
    <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2 p-0" aria-label="Your external specialization">
      {parts.map((p) => {
        const now = p.id === placementId
        return (
          <li
            key={p.id}
            aria-current={now ? 'step' : undefined}
            className={`flex flex-col rounded-lg px-3 py-2 text-[13px] ${
              p.course ? 'border border-line bg-white' : now ? 'border-[1.5px] border-ink bg-white' : 'border border-dashed border-[#8C9488]'
            }`}
          >
            <span className="text-[12px] text-muted">{termLabel(p.term)}</span>
            <span className={p.course ? 'font-mono font-semibold' : now ? 'font-semibold' : 'text-muted'}>
              {p.course ?? (now ? `Choosing${area ? ` in ${area}` : ''}` : 'Open')}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function why(a: Area, term: string) {
  const parts: string[] = []
  if (a.counted.length) parts.push(`${a.counted.join(', ')} already count${a.counted.length === 1 ? 's' : ''}`)
  else if (a.builds_on.length) parts.push(`Builds on ${a.builds_on.slice(-2).join(' and ')}`)
  parts.push(a.ready ? `${a.ready} you could take in ${termLabel(term)}` : `None open in ${termLabel(term)} yet`)
  return parts.join(' · ')
}

function AreaList({ areas, term, onPick }: { areas: SlotAreas; term: string; onPick: (subject: string) => void }) {
  const [query, setQuery] = useState('')
  const [all, setAll] = useState(false)
  const searchId = useId()
  const ask = useAdvisor((s) => s.ask)
  const q = query.trim().toLowerCase()
  const matching = q
    ? areas.areas.filter((a) => a.subject.toLowerCase().startsWith(q) || a.name.toLowerCase().includes(q))
    : areas.areas
  const shown = q || all ? matching : matching.slice(0, SHOWN)

  return (
    <section aria-label="Areas" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-[17px] font-extrabold">Choose an area</h2>
        <div className="flex items-center gap-2">
          <label htmlFor={searchId} className="sr-only">Search areas</label>
          <input
            id={searchId}
            type="search"
            value={query}
            placeholder="Search areas, e.g. ECON"
            onChange={(e) => setQuery(e.target.value)}
            className="h-9 w-56 max-w-full rounded-md border border-[#C3C9BC] bg-white px-2.5 text-[14px]"
          />
        </div>
      </div>
      {!q && <p className="m-0 text-[13px] text-muted">{areaHint(areas.areas)}</p>}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {shown.map((a) => (
          <li key={a.subject}>
            <button
              type="button"
              onClick={() => onPick(a.subject)}
              className={`grid w-full grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg bg-white px-3.5 py-2.5 text-left hover:border-line-strong ${
                a.subject === areas.chosen ? 'border-[1.5px] border-ink' : 'border border-line'
              }`}
            >
              <span className="font-mono text-[14px] font-semibold">{a.subject}</span>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2 font-semibold">
                  {a.name}
                  {a.subject === areas.chosen && (
                    <span className="rounded-full bg-ink px-2 py-px text-[11px] font-semibold text-paper">In your plan</span>
                  )}
                </span>
                {a.reasons.map((r) => (
                  <span key={r.text} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[13px]">
                    <span>{r.text}</span>
                    <Tag kind={basisLabel(r).kind}>{basisLabel(r).text}</Tag>
                  </span>
                ))}
                <span className="text-[13px] text-muted">{why(a, term)}</span>
                {a.sample.length > 0 && (
                  <span className="truncate font-mono text-[12px] text-faint">{a.sample.map((c) => c.code).join(' · ')}</span>
                )}
              </span>
              <span aria-hidden="true" className="text-muted">›</span>
            </button>
          </li>
        ))}
      </ul>
      {q && matching.length === 0 && <p className="m-0 text-muted">No area matches “{query}”.</p>}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {!q && !all && matching.length > SHOWN && (
          <Button variant="link" className="self-start" onClick={() => setAll(true)}>
            Show all {matching.length} areas
          </Button>
        )}
        <Button
          variant="link"
          onClick={() =>
            ask('Help me choose an area for my external specialization. Ask me what I’m interested in, then suggest areas that fit my plan.')
          }
        >
          Ask the advisor to help choose
        </Button>
      </div>
    </section>
  )
}

type CoursesProps = Omit<Props, 'state'> & { areas: SlotAreas; area: string; onChange: () => void }

function AreaCourses({ slotId, term, placementId, areas, area, onChange, canPick, onPick, onHide, hiding }: CoursesProps) {
  const { data, isLoading, error } = useCandidates(slotId, term, 50, { subject: area, placement: placementId })
  const info = areas.areas.find((a) => a.subject === area)
  const visible = data?.candidates.filter((c) => !hiding.includes(c.course.code)) ?? []
  // courses the plan already counts under another subject wouldn't count alongside these
  const leftBehind = areas.chosen && areas.chosen !== area ? areas.counted : []

  return (
    <section aria-label={`Courses in ${area}`} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="m-0 text-[17px] font-extrabold">
          {info?.name ?? area} <span className="font-mono text-[14px] font-semibold text-muted">{area}</span>
        </h2>
        <Button variant="link" onClick={onChange}>
          Change area
        </Button>
      </div>
      {leftBehind.length > 0 && (
        <p role="status" className="m-0 rounded-lg bg-highlight/40 px-3.5 py-2 text-[13.5px]">
          Your plan counts {leftBehind.map((c) => c.code).join(', ')} under {areas.chosen}. Those won’t count alongside{' '}
          {area} courses unless your advisor approves the mix.
        </p>
      )}
      {error && <p className="m-0 text-accent">{error.message}</p>}
      {isLoading && <p className="m-0 text-muted">Loading…</p>}
      {data && (
        <p className="m-0 text-[13px] text-muted">
          {visible.length
            ? `${visible.length} ${area} course${visible.length === 1 ? '' : 's'} you could take in ${termLabel(term, true)}. Undergraduate courses offered most often come first.`
            : `No ${area} course is open to you in ${termLabel(term, true)}. See why below, or change area.`}
        </p>
      )}
      {visible.length > 0 && (
        <ul className="m-0 flex list-none flex-col rounded-xl border border-line bg-white p-0">
          {visible.map((c) => (
            <CourseRow key={c.course.code} c={c} term={term} canPick={canPick} onPick={() => onPick(c.course.code)} onHide={() => onHide(c.course)} />
          ))}
        </ul>
      )}
      {data && data.blocked.length > 0 && (
        <details className="rounded-xl border border-line-soft px-3.5 py-2.5">
          <summary className="cursor-pointer text-[13.5px] font-semibold">
            Not open to you in {termLabel(term)} · {data.blocked.length}
          </summary>
          <ul className="m-0 mt-2 flex list-none flex-col p-0">
            {data.blocked.map((b) => (
              <li key={b.course.code} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-t border-line-soft py-1.5 text-[13px] first:border-t-0">
                <span className="w-24 shrink-0 font-mono font-semibold text-muted">{b.course.code}</span>
                <span className="min-w-0 flex-1 text-muted">{b.course.title}</span>
                <span className="text-[12.5px] text-faint">{b.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function CourseRow({ c, term, canPick, onPick, onHide }: { c: Candidate; term: string; canPick: boolean; onPick: () => void; onHide: () => void }) {
  const titleId = useId()
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line-soft px-3.5 py-3 first:border-t-0">
      <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-0.5">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-mono text-[13px] font-semibold">{c.course.code}</span>
          <span id={titleId} className="font-semibold">{c.course.title}</span>
          <span className="font-mono text-[12px] text-muted">{c.course.credits} cr</span>
        </span>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-muted">
          {c.official.offering_note}
          {c.official.assumed && ` · ${termLabel(term)} assumed from history`}
          {c.capped_cross_listings.map((s) => (
            <span key={s} className="rounded-full bg-chip px-2 py-px text-[11.5px] font-semibold text-ink-soft">
              Cross-listed with {s} · only 1 counts
            </span>
          ))}
          <a href={cureviewsUrl(c.course.code)} target="_blank" rel="noopener noreferrer" aria-label={`Reviews for ${c.course.code} on CUReviews (opens in a new tab)`}>
            Reviews
          </a>
        </span>
      </div>
      <div className="flex gap-2">
        <Button aria-describedby={titleId} disabled={!canPick} onClick={onPick}>
          Put it in {termLabel(term)}
        </Button>
        <Button variant="quiet" aria-describedby={titleId} onClick={onHide}>
          Not for me
        </Button>
      </div>
    </li>
  )
}
