import { Link } from 'react-router'
import { usePlan } from '../../api/hooks'
import { Tag } from '../../ui'
import { termLabel } from '../../ui/terms'
import { openSlots, slotHref } from './slots'

export default function SlotIndex() {
  const { data: state, isLoading, error } = usePlan()

  if (isLoading) return <div className="p-10 text-muted">Loading…</div>
  if (error || !state) return <p className="p-10 text-accent">{error?.message ?? 'Couldn’t load your plan.'}</p>

  const slots = openSlots(state)
  const terms = state.plan.terms.filter((t) => slots.some((p) => p.term === t))

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pt-7 pb-12 sm:px-6">
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[28px] leading-tight font-extrabold tracking-tight sm:text-[34px]">Explore open slots</h1>
        <p className="m-0 text-base text-muted">
          {slots.length > 0
            ? `${slots.length} ${slots.length === 1 ? 'requirement in your plan still needs' : 'requirements in your plan still need'} a course. Pick one to see what could fill it.`
            : 'Every requirement in your plan has a course.'}
        </p>
      </div>

      {slots.length === 0 && (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-line bg-white p-5">
          <span className="text-[15.5px] font-semibold">Nothing to fill right now</span>
          <span className="text-muted">Pick a course in your plan to look at alternatives.</span>
          <Link
            to="/plan"
            className="inline-flex h-11 items-center justify-center rounded-md bg-ink px-3.5 font-semibold text-paper no-underline hover:text-paper sm:h-9"
          >
            Back to your plan
          </Link>
        </div>
      )}

      {terms.map((term) => (
        <section key={term} aria-labelledby={`term-${term}`} className="flex flex-col gap-2">
          <h2 id={`term-${term}`} className="m-0 flex items-center gap-2 text-[13px] font-bold tracking-[0.06em] uppercase text-muted">
            {termLabel(term, true)}
            {term === state.plan.current_term && <Tag kind="neutral">This term</Tag>}
          </h2>
          <ul className="m-0 flex list-none flex-col overflow-hidden rounded-xl border border-line bg-white p-0">
            {slots
              .filter((p) => p.term === term)
              .map((p) => (
                <li key={p.id} className="border-t border-line-soft first:border-t-0">
                  <Link
                    to={slotHref(p)}
                    className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-ink no-underline hover:bg-ground"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-[15.5px] font-semibold">{p.slot_label ?? p.slot}</span>
                      <span className="text-[12.5px] text-muted">
                        Open slot · {p.credits} cr
                      </span>
                    </span>
                    <span className="text-[13px] font-semibold underline underline-offset-3">See options</span>
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </main>
  )
}
