import type { PlanState } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { usePlanUI } from './store'

export default function SemesterList({ state }: { state: PlanState }) {
  const { selected, select } = usePlanUI()
  const { plan } = state
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(min(250px,100%),1fr))] gap-3 p-3 sm:p-4">
      {plan.terms.map((term) => {
        const items = plan.placements.filter((p) => p.term === term)
        const credits = items.reduce((n, p) => n + p.credits, 0)
        return (
          <section key={term} className="rounded-lg border border-line bg-white">
            <h3 className="m-0 flex justify-between border-b border-line-soft px-3 py-2 text-[13px]">
              <span className={term === plan.current_term ? 'font-bold' : 'font-semibold'}>{termLabel(term)}</span>
              <span className="font-mono text-[12px] text-muted">{credits} cr</span>
            </h3>
            <ul className="m-0 list-none p-0">
              {items.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => select(p.id)}
                    aria-current={selected === p.id || undefined}
                    className={`flex w-full items-baseline gap-2 border-0 px-3 py-1.5 text-left ${selected === p.id ? 'bg-chip' : 'bg-transparent'}`}
                  >
                    <span className="w-[84px] shrink-0 font-mono text-[12px] font-semibold whitespace-nowrap">{p.course ?? 'Open slot'}</span>
                    <span className="line-clamp-2 min-w-0 flex-1 text-[12.5px] leading-snug text-ink-soft">{p.course ? p.title : p.slot_label}</span>
                    <span className="shrink-0 font-mono text-[11.5px] text-muted">{p.credits} cr</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
