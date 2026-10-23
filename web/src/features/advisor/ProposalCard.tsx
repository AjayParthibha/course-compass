import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useSearchParams } from 'react-router'
import { proposalPreviewQuery, usePlan, useRestoreProposal } from '../../api/hooks'
import type { Proposal } from '../../api/types'
import { Button } from '../../ui'
import { proposalQuery } from './proposalQuery'
import { isOutdated, proposalCardState, type ProposalCardState } from './proposalState'
import { useAdvisor } from './store'

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

// what the student can say about a suggestion they discarded; each one is sent as their next message
const REASONS = [
  { label: 'Too many credits', message: 'I discarded that because it’s too many credits.' },
  { label: 'Not those courses', message: 'I discarded that because I don’t want those courses.' },
  { label: 'Different term', message: 'I discarded that because I want it in a different term.' },
]

type Props = {
  initial: Proposal
  latestId: number | null
  /** set while the student can still reply to this message: says why they discarded it */
  onReason?: (message: string) => void
}

export default function ProposalCard({ initial, latestId, onReason }: Props) {
  const [params, setParams] = useSearchParams()
  const { data: plan } = usePlan()
  const restore = useRestoreProposal()
  const { data: proposal } = useQuery(proposalQuery(initial))
  const version = plan?.plan.version
  const state = proposalCardState(proposal, version, latestId)
  // fetch the preview while the student reads the card, so opening it doesn't wait
  const qc = useQueryClient()
  useEffect(() => {
    if (state === 'ready' && version !== undefined) qc.prefetchQuery(proposalPreviewQuery(proposal.id, version))
  }, [state, proposal.id, version, qc])
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
        {params.get('proposal') === String(proposal.id) ? (
          <span className="text-[12.5px] text-muted">Showing in the graph. Apply or discard it there.</span>
        ) : (
          <Button variant="primary" className="self-start" onClick={preview}>
            Preview in the graph
          </Button>
        )}
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
      {state === 'discarded' && proposal.base_version === version && (
        <Button
          variant="link"
          className="self-start text-[12.5px]"
          disabled={restore.isPending}
          onClick={() => restore.mutate(proposal.id)}
        >
          Restore
        </Button>
      )}
      {restore.error && <span className="text-[12.5px] text-accent">{restore.error.message}</span>}
      {state === 'discarded' && onReason && (
        <div className="mt-1 flex flex-col gap-1.5 border-t border-line-soft pt-2">
          <span className="text-[12.5px] font-semibold">What was off? The advisor will try again.</span>
          <div className="flex flex-wrap gap-1.5">
            {REASONS.map((r) => (
              <button
                key={r.label}
                type="button"
                onClick={() => onReason(r.message)}
                className="min-h-8 rounded-2xl border border-line bg-white px-3 py-1 text-[12.5px] leading-snug enabled:hover:border-line-strong"
              >
                {r.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => useAdvisor.getState().setDraft('I discarded that because ')}
              className="min-h-8 rounded-2xl border border-line bg-white px-3 py-1 text-[12.5px] leading-snug enabled:hover:border-line-strong"
            >
              Something else…
            </button>
          </div>
        </div>
      )}
      {state === 'replaced' && !isOutdated(proposal, version) && (
        <Button variant="link" className="self-start text-[12.5px]" onClick={preview}>
          Preview anyway
        </Button>
      )}
    </section>
  )
}
