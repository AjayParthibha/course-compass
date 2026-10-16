import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from './client'
import type { PlanOp, PlanSettingsUpdate, PlanState } from './types'

export const keys = {
  me: ['me'] as const,
  plan: ['plan'] as const,
  profile: ['profile'] as const,
  course: (code: string) => ['course', code] as const,
  proposal: (id: number) => ['proposal', id] as const,
  proposalPreview: (id: number) => ['proposal', id, 'preview'] as const,
  candidates: (slot: string, term: string, limit: number, subject?: string | null) =>
    ['candidates', slot, term, limit, subject ?? null] as const,
  // under 'candidates' so whatever refreshes the lists refreshes the areas too
  areas: (slot: string, term: string, placement: string | null) => ['candidates', 'areas', slot, term, placement] as const,
  conversation: ['conversation', 'latest'] as const,
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET('/api/auth/me')),
    enabled,
    retry: false,
  })
}

export function usePlan() {
  return useQuery({ queryKey: keys.plan, queryFn: () => unwrap(api.GET('/api/plan')) })
}

export function useCourse(code: string | null | undefined) {
  return useQuery({
    queryKey: keys.course(code ?? ''),
    queryFn: () => unwrap(api.GET('/api/courses/{code}', { params: { path: { code: code! } } })),
    enabled: !!code,
    staleTime: Infinity,
  })
}

export function usePlanOps() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ops: PlanOp[]) => unwrap(api.POST('/api/plan/ops', { body: { ops } })),
    onSuccess: (state) => qc.setQueryData(keys.plan, state),
  })
}

/** "Keep in this term": a locked placement can't be moved until it's unlocked. */
/** Graduation term and credit caps. Rejects (409) if an earlier graduation would drop courses. */
export function useUpdatePlanSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: PlanSettingsUpdate) => unwrap(api.PATCH('/api/plan/settings', { body })),
    onSuccess: (student) => {
      qc.setQueryData(keys.me, student)
      qc.invalidateQueries({ queryKey: keys.me })
      qc.invalidateQueries({ queryKey: keys.plan })
      qc.invalidateQueries({ queryKey: keys.profile })
    },
  })
}

export function useUndo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/plan/undo')),
    onSuccess: (state) => qc.setQueryData(keys.plan, state),
  })
}

export function useProposal(id: number | null) {
  return useQuery({
    queryKey: keys.proposal(id ?? 0),
    queryFn: () =>
      unwrap(api.GET('/api/proposals/{proposal_id}', { params: { path: { proposal_id: id! } } })),
    enabled: id != null,
  })
}

export function useProposalPreview(id: number | null) {
  return useQuery({
    queryKey: keys.proposalPreview(id ?? 0),
    queryFn: () =>
      unwrap(
        api.POST('/api/proposals/{proposal_id}/preview', {
          params: { path: { proposal_id: id! } },
        }),
      ),
    enabled: id != null,
  })
}

export function useApplyProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(api.POST('/api/proposals/{proposal_id}/apply', { params: { path: { proposal_id: id } } })),
    onSuccess: (state: PlanState, id) => {
      qc.setQueryData(keys.plan, state)
      qc.invalidateQueries({ queryKey: keys.proposal(id) })
    },
  })
}

export function useDiscardProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/proposals/{proposal_id}/discard', { params: { path: { proposal_id: id } } }),
      ),
    onSuccess: (proposal) => qc.setQueryData(keys.proposal(proposal.id), proposal),
  })
}

export function useProfile() {
  return useQuery({ queryKey: keys.profile, queryFn: () => unwrap(api.GET('/api/profile')) })
}

export function useCandidates(
  slot: string,
  term: string,
  limit = 3,
  { subject, placement }: { subject?: string | null; placement?: string | null } = {},
) {
  return useQuery({
    queryKey: keys.candidates(slot, term, limit, subject),
    queryFn: () =>
      unwrap(
        api.GET('/api/slots/{slot_id}/candidates', {
          params: { path: { slot_id: slot }, query: { term, limit, subject, placement } },
        }),
      ),
    enabled: !!slot && !!term,
    placeholderData: keepPreviousData,
  })
}

/** Subjects a same-subject slot (the external specialization) could be filled from. */
export function useAreas(slot: string, term: string, placement: string | null, enabled = true) {
  return useQuery({
    queryKey: keys.areas(slot, term, placement),
    queryFn: () =>
      unwrap(
        api.GET('/api/slots/{slot_id}/areas', {
          params: { path: { slot_id: slot }, query: { term, placement } },
        }),
      ),
    enabled: enabled && !!slot && !!term,
  })
}

export function useLatestConversation() {
  return useQuery({
    queryKey: keys.conversation,
    queryFn: () => unwrap(api.GET('/api/chat/latest')),
    staleTime: Infinity,
  })
}
