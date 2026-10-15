import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { keys } from '../../api/hooks'

/** "Not for me" is saved as a not_interested profile fact; the candidates endpoint skips those courses. */
export function useNotForMe() {
  const qc = useQueryClient()
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ['candidates'] }),
      qc.invalidateQueries({ queryKey: keys.profile }),
    ])
  const hide = useMutation({
    mutationFn: (code: string) =>
      unwrap(api.PUT('/api/courses/{code}/not-interested', { params: { path: { code } } })),
    onSettled: refresh,
  })
  const unhide = useMutation({
    mutationFn: (code: string) =>
      unwrap(api.DELETE('/api/courses/{code}/not-interested', { params: { path: { code } } })),
    onSettled: refresh,
  })
  return { hide, unhide }
}
