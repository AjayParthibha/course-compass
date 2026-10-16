import { usePlanOps, useUndo } from '../../api/hooks'
import type { Placement, PlanOp, PlanState } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { usePlanUI } from './store'

export function placementName(p: Placement) {
  return p.course ?? `${p.slot_label ?? 'Open'} slot`
}

export function describeMove(p: Placement, term: string) {
  return `Moved ${placementName(p)} to ${termLabel(term)}`
}

export function describeRemove(p: Placement) {
  // a course chosen for a requirement slot comes out and leaves the slot open
  if (p.slot && p.course) return `Removed ${p.course}. The ${termLabel(p.term)} ${p.slot_label ?? 'requirement'} slot is open again`
  return `Removed ${placementName(p)} from ${termLabel(p.term)}`
}

/** Manual plan edits that report back through the undo notice. */
export function usePlanEdits() {
  const ops = usePlanOps()
  const undo = useUndo()
  const { notify, setEditError, setUndoneAt } = usePlanUI.getState()
  const onError = (e: Error) => setEditError(e.message)

  const edit = (op: PlanOp, text: string) => {
    setEditError(null)
    ops.mutate([op], {
      onSuccess: (state: PlanState) => {
        setUndoneAt(null)
        notify(text, state.plan.version)
      },
      onError,
    })
  }

  return {
    pending: ops.isPending || undo.isPending,
    move: (p: Placement, term: string) => edit({ op: 'move', placement_id: p.id, term }, describeMove(p, term)),
    remove: (p: Placement) => edit({ op: 'remove', placement_id: p.id }, describeRemove(p)),
    lock: (p: Placement, locked: boolean) =>
      edit(
        { op: 'lock', placement_id: p.id, locked },
        locked ? `Keeping ${placementName(p)} in ${termLabel(p.term)}` : `${placementName(p)} can move again`,
      ),
    undo: () => {
      setEditError(null)
      undo.mutate(undefined, {
        onSuccess: (state: PlanState) => {
          setUndoneAt(state.plan.version)
          notify('Change undone', state.plan.version, false)
        },
        onError,
      })
    },
  }
}
