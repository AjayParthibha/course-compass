import type { AuditResult } from '../../api/types'
import { usePlanUI } from './store'

const dot: Record<string, string> = {
  done: 'bg-ink',
  planned: 'bg-white border border-ink',
  missing: 'bg-accent',
  flagged: 'bg-highlight border border-ink',
}

export default function RequirementBar({ audit }: { audit: AuditResult }) {
  const { highlightReq, setHighlightReq } = usePlanUI()
  return (
    <div className="flex flex-wrap gap-1.5" role="list" aria-label="Requirements">
      {audit.requirements.map((r) => {
        const count = r.children.length
          ? r.children.filter((c) => c.status !== 'missing').length
          : Math.min(r.filled.length, r.needed)
        const active = highlightReq === r.id
        return (
          <button
            key={r.id}
            role="listitem"
            type="button"
            onClick={() => setHighlightReq(active ? null : r.id)}
            aria-pressed={active}
            title={r.status === 'flagged' ? 'Needs sign-off; not checked automatically' : r.status}
            className={`flex h-8 items-center gap-2 rounded-full border px-3 text-[12.5px] ${active ? 'border-ink bg-ink text-paper' : 'border-line bg-white'}`}
          >
            <span className={`h-2 w-2 rounded-full ${dot[r.status]}`} />
            <span className="font-semibold">{r.label}</span>
            <span className={`font-mono text-[11px] ${active ? 'text-paper' : 'text-muted'}`}>
              {count}/{r.children.length || r.needed}
            </span>
          </button>
        )
      })}
    </div>
  )
}
