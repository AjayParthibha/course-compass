import { usePlanOps, useUndo } from '../../api/hooks'
import type { Placement } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { usePlanUI } from './store'

export function placementName(p: Placement) {
  return p.course ?? `${p.slot_label ?? 'Open'} slot`
}

export function describeMove(p: Placement, term: string) {
  return `Moved ${placementName(p)} to ${termLabel(term)}`
}

export function describeRemove(p: Placement) {
  return `Removed ${placementName(p)} from ${termLabel(p.term)}`
}

/** Manual plan edits that report back through the undo notice. */
export function usePlanEdits() {
  const ops = usePlanOps()
  const undo = useUndo()
  const { notify, setEditError } = usePlanUI.getState()
  const onError = (e: Error) => setEditError(e.message)

  return {
    pending: ops.isPending || undo.isPending,
    move: (p: Placement, term: string) =>
      ops.mutate([{ op: 'move', placement_id: p.id, term }], {
        onSuccess: () => notify(describeMove(p, term)),
        onError,
      }),
    remove: (p: Placement) =>
      ops.mutate([{ op: 'remove', placement_id: p.id }], {
        onSuccess: () => notify(describeRemove(p)),
        onError,
      }),
    lock: (p: Placement, locked: boolean) =>
      ops.mutate([{ op: 'lock', placement_id: p.id, locked }], {
        onSuccess: () =>
          notify(
            locked
              ? `Keeping ${placementName(p)} in ${termLabel(p.term)}`
              : `${placementName(p)} can move again`,
          ),
        onError,
      }),
    undo: () =>
      undo.mutate(undefined, {
        onSuccess: () => notify('Change undone', false),
        onError,
      }),
  }
}
