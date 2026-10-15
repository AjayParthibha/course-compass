import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { usePlan } from '../../api/hooks'
import type { Proposal } from '../../api/types'
import { Button } from '../../ui'
import { proposalQuery } from './proposalQuery'
import { isOutdated, proposalCardState, type ProposalCardState } from './proposalState'

const STATUS: Record<Exclude<ProposalCardState, 'ready'>, { label: string; note?: string }> = {
  blocked: { label: 'Didn’t pass the planner check' },
  replaced: { label: 'Replaced by a newer suggestion' },
  outdated: {
    label: 'Outdated',
    note: 'Your plan has changed since this was suggested, so it can’t be applied as-is.',
  },
  applied: { label: 'Applied' },
  'applied-earlier': { label: 'Applied earlier', note: 'Your plan has changed since then.' },
  discarded: { label: 'Discarded' },
}

export default function ProposalCard({ initial, latestId }: { initial: Proposal; latestId: number | null }) {
  const [, setParams] = useSearchParams()
  const { data: plan } = usePlan()
  const { data: proposal } = useQuery(proposalQuery(initial))
  const version = plan?.plan.version
  const state = proposalCardState(proposal, version, latestId)
  const preview = () =>
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('proposal', String(proposal.id))
      return next
    })

  if (state === 'ready')
    return (
      <section aria-label="Proposed change" className="flex flex-col gap-2 rounded-lg border-[1.5px] border-ink bg-white p-3">
        <span className="text-[11px] font-bold tracking-[0.08em] uppercase">Proposed change</span>
        <span className="text-[13.5px]">{proposal.summary}</span>
        {proposal.rejected.length > 0 && (
          <details className="text-[13px]">
            <summary className="cursor-pointer font-semibold">What I didn’t do, and why</summary>
            <ul className="mt-1 mb-0 flex flex-col gap-1 pl-4">
              {proposal.rejected.map((r) => (
                <li key={r.title}>
                  <strong>{r.title}</strong> {r.reason}
                </li>
              ))}
            </ul>
          </details>
        )}
        <Button variant="primary" className="self-start" onClick={preview}>
          Preview in the graph
        </Button>
      </section>
    )

  const { label, note } = STATUS[state]
  const blocking = proposal.violations.filter((v) => v.blocking)
  return (
    <section
      aria-label={`Proposed change: ${label}`}
      className={`flex flex-col gap-1.5 rounded-lg border border-line p-3 ${state === 'blocked' ? 'bg-white' : 'bg-transparent'}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-[11px] font-bold tracking-[0.08em] text-faint uppercase">Proposed change</span>
        <span className={`text-[12px] font-semibold ${state === 'blocked' ? 'text-accent' : 'text-muted'}`}>{label}</span>
      </div>
      <span className="text-[13px] text-muted">{proposal.summary}</span>
      {note && <span className="text-[12.5px] text-faint">{note}</span>}
      {state === 'blocked' && blocking.length > 0 && (
        <details className="text-[12.5px] text-muted">
          <summary className="cursor-pointer font-semibold">See details</summary>
          <ul className="mt-1 mb-0 flex flex-col gap-1 pl-4">
            {blocking.map((v, i) => (
              <li key={i}>{v.message}</li>
            ))}
          </ul>
        </details>
      )}
      {state === 'replaced' && !isOutdated(proposal, version) && (
        <Button variant="link" className="self-start text-[12.5px]" onClick={preview}>
          Preview anyway
        </Button>
      )}
    </section>
  )
}
