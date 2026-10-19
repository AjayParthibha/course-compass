import { useId, useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router'
import { useCandidates, usePlan, usePlanOps } from '../../api/hooks'
import type { Candidate, SlotCandidates } from '../../api/types'
import { Button, SectionLabel, Tag } from '../../ui'
import { cureviewsUrl } from '../../ui/links'
import { termLabel } from '../../ui/terms'
import { useNotForMe } from './notForMe'
import SlotIndex from './SlotIndex'
import Specialization, { Approval } from './Specialization'
import { openSlots, slotHref } from './slots'

type CourseSummary = Candidate['course']

const touch = 'max-sm:h-11'

const basisTag = (r: Candidate['reasons'][number]) => {
  if (r.basis === 'stated') return <Tag kind="said">You said{r.date ? ` · ${r.date}` : ''}</Tag>
  if (r.basis === 'plan') return <Tag kind="plan">Your plan</Tag>
  return <Tag kind="guess">My guess · not confirmed</Tag>
}

type CardProps = { c: Candidate; term: string; canPick: boolean; onPick: () => void; onHide: () => void }

function CandidateCard({ c, term, canPick, onPick, onHide }: CardProps) {
  const titleId = useId()
  return (
    <article aria-labelledby={titleId} className="flex flex-col gap-4 rounded-xl border border-line bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-[1_1_220px] flex-col gap-1">
          <span className="font-mono text-[13px] font-semibold">
            {c.course.code} · {c.course.credits} cr
          </span>
          <h2 id={titleId} className="m-0 text-xl font-extrabold tracking-tight">{c.course.title}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" className={touch} aria-describedby={titleId} disabled={!canPick} onClick={onPick}>
            Put it in {termLabel(term)}
          </Button>
          <Button className={touch} aria-describedby={titleId} onClick={onHide}>
            Not for me
          </Button>
        </div>
      </div>
      {c.reasons.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {c.reasons.map((r) => (
            <li key={r.text} className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <span>{r.text}</span>
              {basisTag(r)}
            </li>
          ))}
        </ul>
      )}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-3">
        <div className="flex flex-col gap-2 rounded-lg bg-ground p-3.5">
          <SectionLabel className="text-ink!">Official · Class Roster</SectionLabel>
          <span>{c.official.prereq_note}</span>
          <span>{c.official.offering_note}</span>
          {c.official.assumed && (
            <span className="text-muted">{termLabel(term)} isn’t scheduled yet. Assumed from history.</span>
          )}
        </div>
        {c.reviews && (
          <div className="flex flex-col gap-2 rounded-lg border border-dashed border-[#9EA698] p-3.5">
            <SectionLabel className="text-ink!">Students say · CUReviews</SectionLabel>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ['Overall', c.reviews.overall],
                  ['Difficulty', c.reviews.difficulty],
                  ['Workload', c.reviews.workload],
                ] as const
              ).map(([label, v]) => (
                <div key={label} className="flex flex-col">
                  <span className="font-mono text-xl font-semibold">{v.toFixed(1)}</span>
                  <span className="text-[12px] text-muted">{label}</span>
                </div>
              ))}
            </div>
            <span className="text-[12.5px] text-muted">
              Out of 5 · {c.reviews.count} reviews · opinions, not official info
            </span>
            <ReviewsLink code={c.course.code} href={c.reviews.url} />
          </div>
        )}
      </div>
      {!c.reviews && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
          <span className="text-muted">Student opinion, not official:</span>
          <ReviewsLink code={c.course.code} />
        </div>
      )}
    </article>
  )
}

function ReviewsLink({ code, href }: { code: string; href?: string }) {
  return (
    <a
      href={href || cureviewsUrl(code)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Read reviews on CUReviews for ${code} (opens in a new tab)`}
      className="inline-flex min-h-11 items-center text-[13px] font-semibold sm:min-h-0"
    >
      Read reviews on CUReviews
    </a>
  )
}

function HiddenRow({ course, onUndo }: { course: CourseSummary; onUndo: () => void }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line-soft py-2 first:border-t-0">
      <span className="min-w-0">
        <span className="font-mono text-[13px] font-semibold">{course.code}</span>{' '}
        <span className="text-muted">{course.title}</span>
      </span>
      <Button variant="quiet" className={`${touch} font-semibold`} aria-label={`Show again: ${course.code}`} onClick={onUndo}>
        Show again
      </Button>
    </li>
  )
}

function Sidebar({ data }: { data: SlotCandidates | undefined }) {
  return (
    <aside aria-label="About this list" className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
      {data && data.factors.length > 0 && (
        <section className="flex flex-col gap-3.5 rounded-xl border border-line bg-white p-4">
          <SectionLabel>What shaped the ranking</SectionLabel>
          {data.factors.map((f) => (
            <div key={f.label} className="flex flex-col gap-1">
              <div className="flex justify-between gap-2">
                <span className={`font-semibold ${f.strength === 'not used' ? 'text-muted' : ''}`}>{f.label}</span>
                <span className="font-mono text-[12px]">{f.strength}</span>
              </div>
              {f.strength !== 'not used' && (
                <div className="h-1.5 rounded bg-chip">
                  <div
                    className="h-1.5 rounded bg-ink"
                    style={{ width: f.strength === 'strong' ? '90%' : f.strength === 'medium' ? '50%' : '25%' }}
                  />
                </div>
              )}
              <span className="text-[12.5px] text-muted">{f.basis}</span>
            </div>
          ))}
          <Link to="/profile" className="font-semibold">Edit what the advisor knows</Link>
        </section>
      )}
      <section className="flex flex-col gap-2.5 rounded-xl border border-line p-4">
        <SectionLabel>Sources</SectionLabel>
        <div className="flex flex-col">
          <a href="https://classes.cornell.edu/" target="_blank" rel="noreferrer" className="font-semibold">Cornell Class Roster</a>
          <span className="text-[12.5px] text-muted">Official · cached snapshot</span>
        </div>
        <div className="flex flex-col">
          <a href="https://www.cs.cornell.edu/undergrad" target="_blank" rel="noreferrer" className="font-semibold">CS degree requirements</a>
          <span className="text-[12.5px] text-muted">Official · decides what counts for this slot</span>
        </div>
        <div className="flex flex-col">
          <a href="https://www.cureviews.org/" target="_blank" rel="noopener noreferrer" className="font-semibold">CUReviews</a>
          <span className="text-[12.5px] text-muted">Student opinion · linked, not imported</span>
        </div>
      </section>
    </aside>
  )
}

const MORE = 50

function SlotOptions({ slotId, term: urlTerm, placementId }: { slotId: string; term: string; placementId: string | null }) {
  const navigate = useNavigate()
  const { data: state } = usePlan()
  const ops = usePlanOps()
  const { hide, unhide, hiding, undoing } = useNotForMe()
  const [limit, setLimit] = useState(3)
  const [lastHidden, setLastHidden] = useState<CourseSummary | null>(null)
  const switchId = useId()

  const slots = state ? openSlots(state) : []
  const here = slots.find((p) => p.id === placementId)
  // e.g. after going Back from the plan: the slot this page was opened for has a course now
  const placement = state?.plan.placements.find((p) => p.id === placementId)
  const stale = !!placementId && !!state && !here
  // the slot may have moved to another term since the link was made
  const term = here?.term ?? urlTerm
  const { data, isLoading, isPlaceholderData, error } = useCandidates(slotId, term, limit)
  const slotLabel = data?.slot_label ?? here?.slot_label ?? slotId

  const pick = (code: string) => {
    const op = placementId
      ? { op: 'replace' as const, placement_id: placementId, course: code }
      : { op: 'add' as const, term, course: code }
    ops.mutate([op], { onSuccess: () => navigate('/plan') })
  }

  const hideCourse = (course: CourseSummary) => {
    setLastHidden(course)
    hide.mutate(course.code)
  }

  const visible = data?.candidates.filter((c) => !hiding.includes(c.course.code)) ?? []
  const hidden = data?.hidden.filter((h) => !undoing.includes(h.fact_id)) ?? []
  const lastFact = lastHidden && hidden.find((h) => h.course.code === lastHidden.code)?.fact_id
  const showLast = lastHidden && (hiding.includes(lastHidden.code) || lastFact != null)
  const olderHidden = hidden.filter((h) => h.course.code !== (showLast ? lastHidden.code : null))
  const expanded = limit >= MORE
  const ranked = !!data && (data.factors.length > 0 || data.candidates.some((c) => c.reasons.length > 0))
  const mutationError = ops.error ?? hide.error ?? unhide.error

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 pt-7 pb-12 sm:px-6">
      <div className="flex flex-col gap-2.5">
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
          <Link to="/plan" className="text-muted">{state?.plan.name ?? 'Plan'}</Link>
          <span aria-hidden="true">/</span>
          <Link to="/explore" className="text-muted">Explore</Link>
          <span aria-hidden="true">/</span>
          <span>{termLabel(term)}</span>
          <span aria-hidden="true">/</span>
          <span aria-current="page" className="font-semibold text-ink">{slotLabel}</span>
        </nav>
        <h1 className="m-0 max-w-3xl text-[28px] leading-tight font-extrabold tracking-tight sm:text-[34px]">
          {data ? `Options for ${data.slot_label}` : 'Finding options…'}
        </h1>
        {stale && (
          <p role="status" className="m-0 flex max-w-3xl flex-wrap items-baseline gap-x-2 rounded-lg bg-chip px-3.5 py-2">
            <span>
              {placement?.course
                ? `This slot has been filled with ${placement.course}.`
                : 'This slot is no longer open in your plan.'}
            </span>
            <Link to="/explore" className="font-semibold">See open slots</Link>
          </p>
        )}
        {data && !data.same_subject && (
          <p className="m-0 max-w-3xl text-base text-muted">
            {data.eligible_count} {data.eligible_count === 1 ? 'course' : 'courses'} would satisfy this slot in{' '}
            {termLabel(term, true)} and fit your prerequisites.
          </p>
        )}
        {data && !data.same_subject && data.approval?.approved && (
          <Approval slotId={data.slot_id} approval={data.approval} />
        )}
        {slots.length > 1 && (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={switchId} className="text-[13px] font-semibold">Open slot</label>
            <select
              id={switchId}
              value={here?.id ?? ''}
              onChange={(e) => {
                const p = slots.find((s) => s.id === e.target.value)
                if (p) navigate(slotHref(p))
              }}
              className="h-11 max-w-full min-w-0 rounded-md border border-[#C3C9BC] bg-white px-2 sm:h-9"
            >
              {!here && <option value="">{termLabel(term)} · {slotLabel}</option>}
              {slots.map((p) => (
                <option key={p.id} value={p.id}>
                  {termLabel(p.term)} · {p.slot_label ?? p.slot} · {p.credits} cr
                </option>
              ))}
            </select>
            <Link to="/explore" className="inline-flex min-h-11 items-center text-[13px] font-semibold sm:min-h-0">
              All open slots
            </Link>
          </div>
        )}
      </div>

      {error && <p className="m-0 text-accent">{error.message}</p>}
      {mutationError && <p className="m-0 text-accent">{mutationError.message}</p>}

      <div className="flex flex-wrap items-start gap-6">
        <main className="flex min-w-0 flex-[999_1_600px] flex-col gap-4">
          {data?.ordering && !data.same_subject && visible.length > 0 && (
            <p className="m-0 text-[13px] text-muted">
              {data.ordering}.{!ranked && ' This isn’t a personal recommendation yet.'}
            </p>
          )}
          <div role="status" aria-live="polite">
            {showLast && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-chip px-3.5 py-2">
                <span className="min-w-0 flex-1">
                  Hidden <span className="font-mono font-semibold">{lastHidden.code}</span>. Saved to your{' '}
                  <Link to="/profile">profile</Link> so it stays out of your options.
                </span>
                <Button
                  variant="quiet"
                  className={`${touch} font-semibold`}
                  aria-label={`Undo hiding ${lastHidden.code}`}
                  disabled={lastFact == null}
                  onClick={() => lastFact != null && unhide.mutate(lastFact)}
                >
                  Undo
                </Button>
              </div>
            )}
          </div>
          {isLoading && <p className="m-0 text-muted">Loading…</p>}
          {data?.same_subject && (
            <Specialization
              slotId={slotId}
              term={term}
              placementId={placementId}
              state={state}
              canPick={!stale && !ops.isPending}
              onPick={pick}
              onHide={hideCourse}
              hiding={hiding}
            />
          )}
          {data && !data.same_subject && visible.length === 0 && (
            <p className="m-0 text-muted">
              {hidden.length > 0
                ? 'No other courses fit this slot. Bring back one you hid below.'
                : `Nothing fits this slot in ${termLabel(term, true)} yet. A course may need prerequisites you won’t have by then, or may not be offered that season.`}
            </p>
          )}
          {!data?.same_subject && visible.map((c) => (
            <CandidateCard
              key={c.course.code}
              c={c}
              term={term}
              canPick={!stale && !ops.isPending}
              onPick={() => pick(c.course.code)}
              onHide={() => hideCourse(c.course)}
            />
          ))}
          {isPlaceholderData && <p className="m-0 text-muted">Loading more…</p>}
          {data && !data.same_subject && !expanded && data.eligible_count > data.candidates.length && (
            <Button variant="link" className={`${touch} self-start`} onClick={() => setLimit(MORE)}>
              See more of the {data.eligible_count} eligible courses
            </Button>
          )}
          {data && !data.same_subject && expanded && !isPlaceholderData && data.eligible_count > data.candidates.length && (
            <p className="m-0 text-[13px] text-muted">
              Showing the first {data.candidates.length} of {data.eligible_count}.
            </p>
          )}
          {olderHidden.length > 0 && (
            <section aria-label="Courses you marked not for me" className="flex flex-col gap-1 rounded-xl border border-line p-4">
              <SectionLabel>Not for me · {olderHidden.length}</SectionLabel>
              <ul className="m-0 flex list-none flex-col p-0">
                {olderHidden.map((h) => (
                  <HiddenRow key={h.course.code} course={h.course} onUndo={() => unhide.mutate(h.fact_id)} />
                ))}
              </ul>
            </section>
          )}
        </main>
        <Sidebar data={data} />
      </div>
    </div>
  )
}

export default function ExplorePage() {
  const { slotId } = useParams()
  const [params] = useSearchParams()
  const { data: state } = usePlan()
  const term = params.get('term') ?? ''
  const placementId = params.get('placement')

  if (!slotId) return <SlotIndex />
  if (!term) {
    if (!state) return <div className="p-10 text-muted">Loading…</div>
    const open = openSlots(state)
    const p = open.find((s) => s.id === placementId) ?? open.find((s) => s.slot === slotId)
    return <Navigate to={p ? slotHref(p) : '/explore'} replace />
  }
  return <SlotOptions key={`${slotId}|${term}|${placementId}`} slotId={slotId} term={term} placementId={placementId} />
}
