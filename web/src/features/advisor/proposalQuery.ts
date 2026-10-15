import { api, unwrap } from '../../api/client'
import { keys } from '../../api/hooks'
import type { Proposal } from '../../api/types'

/** Reads a proposal from the shared cache, so applying or discarding it elsewhere shows up here. */
export const proposalQuery = (initial: Proposal) => ({
  queryKey: keys.proposal(initial.id),
  queryFn: () => unwrap(api.GET('/api/proposals/{proposal_id}', { params: { path: { proposal_id: initial.id } } })),
  initialData: initial,
  staleTime: Infinity,
  gcTime: Infinity,
})
