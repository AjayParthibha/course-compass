import { useState } from 'react'
import { useSearchParams } from 'react-router'
import {
  useApplyProposal,
  useDiscardProposal,
  useProposal,
  useProposalPreview,
  useUndo,
} from '../../api/hooks'
import type { PlanState } from '../../api/types'
import { Button, SectionLabel } from '../../ui'
import { termLabel } from '../../ui/terms'
import DegreeGraph from './DegreeGraph'

export default function ProposalView({ id, current }: { id: number; current: PlanState }) {
  const [, setParams] = useSearchParams()
  const [showAfter, setShowAfter] = useState(true)
  const { data: proposal, error: proposalError } = useProposal(id)
  const { data: preview, error: previewError } = useProposalPreview(id)
  const apply = useApplyProposal()
  const discard = useDiscardProposal()
  const undo = useUndo()
  const close = () => setParams({})

  // an outdated or already-handled proposal can't be previewed; say so instead of loading forever
  const failed = proposalError ?? (proposal?.status === 'applied' ? null : previewError)
  if (failed) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-4">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-xl font-extrabold tracking-tight">This suggestion can’t be previewed</h1>
          <p className="m-0 text-[14px] text-muted">{failed.message}</p>
        </div>
        <Button onClick={close}>Back to plan</Button>
      </section>
    )
  }
  const applied = proposal?.status === 'applied'
  if (!proposal || (!preview && !applied)) return <div className="p-6 text-muted">Loading proposal…</div>

  const before = new Map(current.plan.placements.map((p) => [p.id, p]))
  const moved = new Set(
    (preview?.plan.placements ?? [])
      .filter((p) => before.get(p.id)?.term !== p.term)
      .map((p) => p.id),
  )
  const ghosts = current.plan.placements.filter((p) => moved.has(p.id))
  const shown = applied || !preview ? current : showAfter ? preview : current
  const blocking = proposal.violations.filter((v) => v.blocking)

  return (
    <div className="flex flex-col gap-4">
      <section className="min-w-0 rounded-xl border border-line bg-white">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line-soft p-4">
          <div className="flex max-w-xl flex-col gap-1">
            <h1 className="m-0 text-xl font-extrabold tracking-tight">Previewing the advisor’s proposal</h1>
            <p className="m-0 text-[14px] text-muted">{proposal.summary}</p>
          </div>
          {applied ? (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Applied.</span>
              <Button onClick={() => undo.mutate(undefined, { onSuccess: close })}>Undo</Button>
              <Button variant="primary" onClick={close}>Done</Button>
            </div>
          ) : proposal.status !== 'pending' ? (
            <div className="flex items-center gap-2">
              <span className="text-muted">This proposal is {proposal.status}.</span>
              <Button onClick={close}>Back to plan</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-md border border-line p-0.5" role="group" aria-label="Compare">
                {['Before', 'After'].map((label) => (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={showAfter === (label === 'After')}
                    onClick={() => setShowAfter(label === 'After')}
                    className={`h-8 rounded border-0 px-3 ${showAfter === (label === 'After') ? 'bg-ink text-paper' : 'bg-transparent'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <Button onClick={() => discard.mutate(id, { onSuccess: close })}>Discard</Button>
              <Button
                variant="primary"
                disabled={blocking.length > 0 || apply.isPending}
                onClick={() => apply.mutate(id)}
              >
                Apply {proposal.ops.length} change{proposal.ops.length === 1 ? '' : 's'}
              </Button>
            </div>
          )}
        </div>
        {apply.error && <p className="m-0 px-4 pt-3 text-[13px] text-accent">{apply.error.message}</p>}
        <DegreeGraph
          state={shown}
          readOnly
          moved={applied ? undefined : showAfter ? moved : new Set()}
          ghosts={!applied && showAfter ? ghosts : []}
        />
      </section>

      <aside className="grid grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-4">
        <section className="flex flex-col gap-3 rounded-xl border border-line bg-white p-4">
          <SectionLabel>What changes</SectionLabel>
          {proposal.changes.map((c) => (
            <div key={c.course} className="flex flex-col gap-1">
              <span className="font-mono font-semibold">{c.course}</span>
              <span className="text-[13px]">
                {c.from_term ? termLabel(c.from_term) : 'Added'} → {c.to_term ? termLabel(c.to_term) : 'Removed'}
              </span>
              <span className="text-[13px] text-muted">{c.reason}</span>
            </div>
          ))}
        </section>
        <section className="flex flex-col gap-2 rounded-xl border border-line bg-white p-4">
          <SectionLabel>Checked by the planner</SectionLabel>
          {proposal.checks.map((c) => (
            <span key={c} className="flex gap-2 text-[13px]">
              <span aria-hidden="true">✓</span>
              {c}
            </span>
          ))}
          {proposal.violations.map((v) => (
            <span key={v.message} className={`flex gap-2 text-[13px] ${v.blocking ? 'text-accent' : 'text-muted'}`}>
              <span aria-hidden="true">{v.blocking ? '✕' : '!'}</span>
              {v.message}
            </span>
          ))}
          <span className="text-[12.5px] text-muted">
            Offerings in terms without a published roster are assumed from past years.
          </span>
        </section>
      </aside>
    </div>
  )
}
