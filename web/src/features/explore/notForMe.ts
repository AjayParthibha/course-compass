import { useMutation, useMutationState, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { keys } from '../../api/hooks'

const hideKey = ['not-for-me', 'hide'] as const
const unhideKey = ['not-for-me', 'unhide'] as const

/**
 * "Not for me" is saved as a not_interested profile fact; the candidates endpoint skips those
 * courses. Showing a course again deletes that fact by id, so cross-listed codes work too.
 * Each mutation stays pending until the candidate list has refetched, so `hiding` and `undoing`
 * cover every call in flight, not just the latest.
 */
export function useNotForMe() {
  const qc = useQueryClient()
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ['candidates'] }),
      qc.invalidateQueries({ queryKey: keys.profile }),
    ])
  const hide = useMutation({
    mutationKey: hideKey,
    mutationFn: (code: string) =>
      unwrap(api.PUT('/api/courses/{code}/not-interested', { params: { path: { code } } })),
    onSettled: refresh,
  })
  const unhide = useMutation({
    mutationKey: unhideKey,
    mutationFn: (factId: number) =>
      unwrap(api.DELETE('/api/profile/facts/{fact_id}', { params: { path: { fact_id: factId } } })),
    onSettled: refresh,
  })
  const hiding = useMutationState({
    filters: { mutationKey: hideKey, status: 'pending' },
    select: (m) => m.state.variables as string,
  })
  const undoing = useMutationState({
    filters: { mutationKey: unhideKey, status: 'pending' },
    select: (m) => m.state.variables as number,
  })
  return { hide, unhide, hiding, undoing }
}
