import { create } from 'zustand'

type View = 'graph' | 'semesters'

/** Feedback after a manual edit; `undoable` is false once the edit has been undone. */
export type EditNotice = { id: number; text: string; undoable: boolean }

type PlanUI = {
  selected: string | null
  highlightReq: string | null
  view: View
  notice: EditNotice | null
  editError: string | null
  select: (id: string | null) => void
  setHighlightReq: (id: string | null) => void
  setView: (view: View) => void
  notify: (text: string, undoable?: boolean) => void
  dismissNotice: () => void
  setEditError: (message: string | null) => void
}

let nextNotice = 1

export const usePlanUI = create<PlanUI>((set) => ({
  selected: null,
  highlightReq: null,
  view: 'graph',
  notice: null,
  editError: null,
  select: (selected) => set({ selected, highlightReq: null }),
  setHighlightReq: (highlightReq) => set({ highlightReq, selected: null }),
  setView: (view) => set({ view }),
  notify: (text, undoable = true) => set({ notice: { id: nextNotice++, text, undoable }, editError: null }),
  dismissNotice: () => set({ notice: null }),
  setEditError: (editError) => set({ editError }),
}))
