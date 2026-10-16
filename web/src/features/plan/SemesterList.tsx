import type { Placement, PlanState } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { usePlanUI } from './store'
import { groupByYear } from './years'

const yearLabel = (start: number) => `20${String(start).padStart(2, '0')}–${String((start + 1) % 100).padStart(2, '0')}`

/** The semesters view: one row per academic year, Fall beside Spring, so a year reads at a glance. */
export default function SemesterList({ state }: { state: PlanState }) {
  const { plan } = state
  const now = plan.terms.indexOf(plan.current_term)
  const years = groupByYear(plan.terms)
  const past = (term: string) => plan.terms.indexOf(term) < now
  return (
    <div className="@container flex flex-col gap-3 p-3 sm:p-4">
      {years.map((year, i) => {
        const terms = [year.fall, year.spring, ...year.other].filter((t): t is string => t !== null)
        const done = terms.every(past)
        return (
          <section
            key={year.start}
            aria-label={`Year ${i + 1}, ${yearLabel(year.start)}`}
            className="grid grid-cols-1 gap-2 @[560px]:grid-cols-[76px_minmax(0,1fr)_minmax(0,1fr)] @[560px]:gap-3"
          >
            <h3 className="m-0 flex items-baseline gap-2 text-[12.5px] font-normal text-muted @[560px]:flex-col @[560px]:gap-0 @[560px]:pt-2">
              <span className="text-[13.5px] font-bold text-ink">Year {i + 1}</span>
              <span>
                {yearLabel(year.start)}
                {done && <span className="sr-only">, completed</span>}
                {done && <span aria-hidden="true"> ✓</span>}
              </span>
            </h3>
            {/* keep Spring in its column when a plan starts in the spring */}
            {!year.fall && <div aria-hidden="true" className="hidden @[560px]:block" />}
            {terms.map((term) => (
              <Term key={term} term={term} items={plan.placements.filter((p) => p.term === term)} status={past(term) ? 'done' : term === plan.current_term ? 'now' : 'planned'} />
            ))}
          </section>
        )
      })}
    </div>
  )
}

const frame = {
  done: 'border border-[#BFC6B8] bg-done/45',
  now: 'border-[1.5px] border-ink bg-white',
  planned: 'border border-line bg-white',
}

function Term({ term, items, status }: { term: string; items: Placement[]; status: keyof typeof frame }) {
  const { selected, select } = usePlanUI()
  const credits = items.reduce((n, p) => n + p.credits, 0)
  const courses = items.filter((p) => p.course)
  const slots = items.filter((p) => !p.course)
  const toggle = (id: string) => (e: React.MouseEvent<HTMLButtonElement>) => {
    if (selected !== id) return select(id)
    select(null)
    if (e.detail) e.currentTarget.blur() // mouse click, not Enter/Space
  }
  return (
    <div className={`min-w-0 rounded-lg ${frame[status]}`}>
      <h4 className="m-0 flex items-center justify-between gap-2 px-3 pt-2 pb-1 text-[13px] font-semibold">
        <span className="flex items-center gap-1.5">
          {termLabel(term)}
          {status === 'now' && <span className="rounded-full bg-ink px-1.5 py-px text-[10.5px] font-semibold text-paper">Now</span>}
        </span>
        <span className="font-mono text-[11.5px] font-normal text-muted">
          {credits} cr{slots.length > 0 && ` · ${slots.length} open`}
        </span>
      </h4>
      {courses.length > 0 && (
        <ul className="m-0 list-none p-0 pb-1">
          {courses.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={toggle(p.id)}
                aria-current={selected === p.id || undefined}
                title={p.title ?? undefined}
                className={`flex w-full items-baseline gap-2 border-0 px-3 py-1 text-left ${selected === p.id ? 'bg-chip' : 'bg-transparent hover:bg-ground'}`}
              >
                <span className="w-[76px] shrink-0 font-mono text-[11.5px] font-semibold whitespace-nowrap">{p.course}</span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-soft">{p.title}</span>
                <span className="shrink-0 font-mono text-[11px] text-muted">{p.credits}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {slots.length > 0 && (
        <ul className="m-0 flex list-none flex-wrap gap-1.5 px-3 pt-0.5 pb-2.5" aria-label="Open slots">
          {slots.map((p) => (
            <li key={p.id} className="flex">
              <button
                type="button"
                onClick={toggle(p.id)}
                aria-current={selected === p.id || undefined}
                aria-label={`Open slot: ${p.slot_label}, ${p.credits} credits`}
                className={`rounded-full border border-dashed border-[#8C9488] px-2 py-0.5 text-[12px] ${selected === p.id ? 'border-ink bg-chip text-ink' : 'bg-transparent text-muted hover:text-ink'}`}
              >
                {p.slot_label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {items.length === 0 && <p className="m-0 px-3 pb-2.5 text-[12.5px] text-faint">Nothing planned</p>}
    </div>
  )
}
