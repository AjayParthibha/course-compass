import type { AdvisorEvent, Proposal } from '../../api/types'

export type ProposalCardState = 'ready' | 'blocked' | 'replaced' | 'outdated' | 'applied' | 'discarded'

export const hasBlocking = (p: Proposal) => p.violations.some((v) => v.blocking)

/** Made against an older version of the plan, so it can't be applied as-is. */
export const isOutdated = (p: Proposal, planVersion: number | undefined) =>
  p.status === 'outdated' || (p.status === 'pending' && planVersion !== undefined && planVersion !== p.base_version)

/**
 * The newest proposal in the conversation that passed the planner check. A suggestion that
 * failed the check doesn't replace an earlier one that passed.
 */
export function latestProposalId(events: AdvisorEvent[]): number | null {
  let latest: number | null = null
  for (const e of events) {
    if (e.type === 'proposal' && !hasBlocking(e.proposal) && (latest === null || e.proposal.id > latest))
      latest = e.proposal.id
  }
  return latest
}

/** What a proposal card should offer, given the current plan and the rest of the conversation. */
export function proposalCardState(
  p: Proposal,
  planVersion: number | undefined,
  latestId: number | null,
): ProposalCardState {
  if (p.status === 'applied' || p.status === 'discarded') return p.status
  if (hasBlocking(p)) return 'blocked'
  if (latestId !== null && p.id !== latestId) return 'replaced'
  if (isOutdated(p, planVersion)) return 'outdated'
  return 'ready'
}
