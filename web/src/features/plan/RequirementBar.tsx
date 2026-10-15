import { useId, useState } from 'react'
import type { AuditResult } from '../../api/types'
import { usePlanUI } from './store'
import { summarizeRequirements } from './summary'

const dot: Record<string, string> = {
  done: 'bg-ink',
  planned: 'bg-white border border-ink',
  missing: 'bg-accent',
  flagged: 'bg-highlight border border-ink',
}

export default function RequirementBar({ audit, problems = 0 }: { audit: AuditResult; problems?: number }) {
  const { highlightReq, setHighlightReq } = usePlanUI()
  const [open, setOpen] = useState(false)
  const listId = useId()
  const summary = summarizeRequirements(audit, problems)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-white px-3 py-2 text-[13px] md:hidden">
        <p className="m-0 min-w-0">
          <span className="font-semibold">{summary.headline}</span>
          {summary.details.map((d) => (
            <span key={d} className="text-muted"> · {d}</span>
          ))}
        </p>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
          className="h-8 shrink-0 rounded-md border border-line bg-white px-2.5 text-[12.5px] font-semibold"
        >
          {open ? 'Hide' : 'Details'}
        </button>
      </div>
      <ul id={listId} className={`${open ? 'flex' : 'hidden'} m-0 list-none flex-wrap gap-1.5 p-0 md:flex`} role="list" aria-label="Requirements">
        {audit.requirements.map((r) => {
          const covered = r.children.length
            ? r.children.filter((c) => c.status !== 'missing').length
            : Math.min(r.filled.length, r.needed)
          // open slots hold a seat in the plan but no course has been picked yet
          const chosen = covered - r.open_slots
          const flagged = r.status === 'flagged'
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
                    : r.open_slots
                      ? `${chosen} chosen, ${r.open_slots} open slot${r.open_slots > 1 ? 's' : ''} still to fill`
                      : r.status
                }
                className={`flex h-8 items-center gap-2 rounded-full border px-3 text-[12.5px] ${active ? 'border-ink bg-ink text-paper' : 'border-line bg-white'}`}
              >
                <span className={`h-2 w-2 rounded-full ${dot[r.status]}`} />
                <span className="font-semibold">{r.label}</span>
                <span className={`font-mono text-[11px] ${active ? 'text-paper' : 'text-muted'}`}>
                  {flagged ? 'check' : `${chosen}/${r.children.length || r.needed}`}
                  {!flagged && r.open_slots > 0 && ` · ${r.open_slots} open`}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
