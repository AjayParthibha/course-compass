import { useId, useState } from 'react'
import type { AuditResult, RequirementStatus } from '../../api/types'
import { usePlanUI } from './store'
import { summarizeRequirements } from './summary'

const dot: Record<string, string> = {
  done: 'bg-ink',
  planned: 'bg-white border border-ink',
  missing: 'bg-accent',
  flagged: 'bg-highlight border border-ink',
}

/**
 * One line saying how the plan stands, a meter with a segment per requirement, and chips
 * only for the requirements that still need a course. The rest sit behind "Show all".
 */
export default function RequirementBar({ audit, problems = 0 }: { audit: AuditResult; problems?: number }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const summary = summarizeRequirements(audit, problems)
  const needsCourse = audit.requirements.filter((r) => r.status === 'missing')
  const segments: [number, string][] = [
    [summary.done, 'bg-ink'],
    [summary.planned, 'bg-line'],
    [summary.toConfirm, 'bg-highlight'],
    [summary.missing, 'bg-accent'],
  ]
  return (
    <section aria-label="Requirements" className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="m-0 text-[15px] font-semibold">{summary.headline}</h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
          className="shrink-0 border-0 bg-transparent p-0 text-[13px] font-semibold underline underline-offset-2"
        >
          {open ? 'Hide requirements' : `Show all ${summary.total}`}
        </button>
      </div>
      <div className="flex h-2 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
        {segments.map(([n, color]) => n > 0 && <span key={color} className={color} style={{ flexGrow: n }} />)}
      </div>
      {summary.details.length > 0 && <p className="m-0 text-[13px] text-muted">{summary.details.join(' · ')}</p>}
      {open ? (
        <ChipList id={listId} reqs={audit.requirements} label="All requirements" />
      ) : (
        needsCourse.length > 0 && <ChipList id={listId} reqs={needsCourse} label="Requirements that need a course" />
      )}
    </section>
  )
}

function ChipList({ id, reqs, label }: { id: string; reqs: RequirementStatus[]; label: string }) {
  const { highlightReq, setHighlightReq } = usePlanUI()
  return (
    <ul id={id} className="m-0 flex list-none flex-wrap gap-1.5 p-0" role="list" aria-label={label}>
      {reqs.map((r) => {
        const covered = r.children.length
          ? r.children.filter((c) => c.status !== 'missing').length
          : Math.min(r.filled.length, r.needed)
        // open slots hold a seat in the plan but no course has been picked yet
        const chosen = covered - r.open_slots
        const flagged = r.status === 'flagged'
        // a credit total (123 credits) shows credits, not courses
        const total = r.credits_needed != null
        const active = highlightReq === r.id
        return (
          <li key={r.id} className="flex">
            <button
              type="button"
              onClick={() => setHighlightReq(active ? null : r.id)}
              aria-pressed={active}
              title={
                flagged
                  ? 'Needs sign-off; not checked automatically'
                  : total
                    ? `${r.credits} of ${r.credits_needed} credits, open slots included`
                    : r.open_slots
                      ? `${chosen} chosen, ${r.open_slots} open slot${r.open_slots > 1 ? 's' : ''} still to fill`
                      : r.status
              }
              className={`flex h-8 items-center gap-2 rounded-full border px-3 text-[12.5px] ${active ? 'border-ink bg-ink text-paper' : 'border-line bg-white'}`}
            >
              <span className={`h-2 w-2 rounded-full ${dot[r.status]}`} />
              <span className="font-semibold">{r.label}</span>
              <span className={`font-mono text-[11px] ${active ? 'text-paper' : 'text-muted'}`}>
                {flagged
                  ? 'check'
                  : total
                    ? `${r.credits}/${r.credits_needed} cr`
                    : `${chosen}/${r.children.length || r.needed}`}
                {!flagged && !total && r.open_slots > 0 && ` · ${r.open_slots} open`}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
