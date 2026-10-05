import { useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router'
import { useCandidates, usePlan, usePlanOps } from '../../api/hooks'
import type { Candidate } from '../../api/types'
import { Button, SectionLabel, Tag } from '../../ui'
import { termLabel } from '../../ui/terms'

const basisTag = (r: Candidate['reasons'][number]) => {
  if (r.basis === 'stated') return <Tag kind="said">You said{r.date ? ` · ${r.date}` : ''}</Tag>
  if (r.basis === 'plan') return <Tag kind="plan">Your plan</Tag>
  return <Tag kind="guess">My guess · not confirmed</Tag>
}

function CandidateCard({ c, term, onPick, onHide }: { c: Candidate; term: string; onPick: () => void; onHide: () => void }) {
  const top = c.rank === 1
  return (
    <article className={`flex flex-col gap-4 rounded-xl bg-white p-5 ${top ? 'border-[1.5px] border-ink' : 'border border-line'}`}>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <span className={`font-mono text-[40px] leading-[0.9] font-semibold ${top ? 'text-accent' : 'text-faint'}`}>{c.rank}</span>
        <div className="flex min-w-[220px] flex-1 flex-col gap-1">
          <span className="font-mono text-[13px] font-semibold">
            {c.course.code} · {c.course.credits} cr
          </span>
          <h2 className="m-0 text-xl font-extrabold tracking-tight">{c.course.title}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant={top ? 'primary' : 'secondary'} onClick={onPick}>
            Put it in {termLabel(term)}
          </Button>
          <Button onClick={onHide}>Not for me</Button>
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
        <div className="flex flex-col gap-2 rounded-lg border border-dashed border-[#9EA698] p-3.5">
          <SectionLabel className="text-ink!">Students say · CUReviews</SectionLabel>
          {c.reviews ? (
            <>
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
              <a href={c.reviews.url} target="_blank" rel="noreferrer" className="text-[13px] font-semibold">
                Read them on CUReviews
              </a>
            </>
          ) : (
            <span className="text-muted">No reviews found. We won’t guess.</span>
          )}
        </div>
      </div>
    </article>
  )
}

export default function ExplorePage() {
  const { slotId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { data: state } = usePlan()
  const ops = usePlanOps()
  const [limit, setLimit] = useState(3)
  const [hidden, setHidden] = useState<string[]>([])
  const term = params.get('term') ?? ''
  const placementId = params.get('placement')
  const { data, isLoading, error } = useCandidates(slotId ?? '', term, limit)

  if (!slotId && state) {
    const open = state.plan.placements.find((p) => p.slot && !p.course && p.term !== state.plan.current_term)
    if (open) return <Navigate to={`/explore/${open.slot}?term=${open.term}&placement=${open.id}`} replace />
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-2xl font-extrabold">No open slots</h1>
        <p className="text-muted">Every requirement in your plan has a course. Pick a course in the graph to look at alternatives.</p>
      </main>
    )
  }

  const pick = (code: string) => {
    const op = placementId
      ? { op: 'replace' as const, placement_id: placementId, course: code }
      : { op: 'add' as const, term, course: code }
    ops.mutate([op], { onSuccess: () => navigate('/plan') })
  }

  const visible = data?.candidates.filter((c) => !hidden.includes(c.course.code)) ?? []

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 pt-7 pb-12">
      <div className="flex flex-col gap-2.5">
        <nav aria-label="Breadcrumb" className="flex flex-wrap gap-2 text-[13px] text-muted">
          <Link to="/plan" className="text-muted">{state?.plan.name ?? 'Plan'}</Link>
          <span aria-hidden="true">/</span>
          <span>{termLabel(term)}</span>
          <span aria-hidden="true">/</span>
          <span className="font-semibold text-ink">{data?.slot_label ?? slotId}</span>
        </nav>
        <h1 className="m-0 max-w-3xl text-[34px] leading-tight font-extrabold tracking-tight">
          {data ? `Options for ${data.slot_label}` : 'Finding options…'}
        </h1>
        {data && (
          <p className="m-0 max-w-3xl text-base text-muted">
            {data.eligible_count} courses would satisfy this slot and fit your prerequisites.
          </p>
        )}
      </div>

      {error && <p className="text-accent">{error.message}</p>}
      {ops.error && <p className="text-accent">{ops.error.message}</p>}

      <div className="flex flex-wrap items-start gap-6">
        <main className="flex min-w-0 flex-[999_1_600px] flex-col gap-4">
          {isLoading && <p className="text-muted">Loading…</p>}
          {visible.map((c) => (
            <CandidateCard
              key={c.course.code}
              c={c}
              term={term}
              onPick={() => pick(c.course.code)}
              onHide={() => setHidden((h) => [...h, c.course.code])}
            />
          ))}
          {data && data.eligible_count > limit && (
            <Button variant="link" className="self-start" onClick={() => setLimit(50)}>
              See more of the {data.eligible_count} eligible courses
            </Button>
          )}
        </main>

        <aside aria-label="How these were ranked" className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
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
              <a href="https://www.cureviews.org/" target="_blank" rel="noreferrer" className="font-semibold">CUReviews</a>
              <span className="text-[12.5px] text-muted">Student opinion · shown separately</span>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
