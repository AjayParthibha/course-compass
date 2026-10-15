import { create } from 'zustand'

type View = 'graph' | 'semesters'

/**
 * Feedback after a manual edit; `undoable` is false once the edit has been undone. `version` is
 * the plan version the edit produced, so the notice can go away once the plan moves on.
 */
export type EditNotice = { id: number; text: string; undoable: boolean; version: number }

type PlanUI = {
  selected: string | null
  highlightReq: string | null
  view: View
  notice: EditNotice | null
  editError: string | null
  /** Plan version right after the latest undo, while nothing else has changed the plan. */
  undoneAt: number | null
  select: (id: string | null) => void
  setHighlightReq: (id: string | null) => void
  setView: (view: View) => void
  notify: (text: string, version: number, undoable?: boolean) => void
  dismissNotice: () => void
  setEditError: (message: string | null) => void
  setUndoneAt: (version: number | null) => void
}

let nextNotice = 1

export const usePlanUI = create<PlanUI>((set) => ({
  selected: null,
  highlightReq: null,
  view: 'graph',
  notice: null,
  editError: null,
  undoneAt: null,
  select: (selected) => set({ selected, highlightReq: null }),
  setHighlightReq: (highlightReq) => set({ highlightReq, selected: null }),
  setView: (view) => set({ view }),
  notify: (text, version, undoable = true) =>
    set({ notice: { id: nextNotice++, text, undoable, version }, editError: null }),
  dismissNotice: () => set({ notice: null }),
  setEditError: (editError) => set({ editError }),
  setUndoneAt: (undoneAt) => set({ undoneAt }),
}))
