import { create } from 'zustand'

type View = 'graph' | 'semesters'

type PlanUI = {
  selected: string | null
  highlightReq: string | null
  view: View
  select: (id: string | null) => void
  setHighlightReq: (id: string | null) => void
  setView: (view: View) => void
}

export const usePlanUI = create<PlanUI>((set) => ({
  selected: null,
  highlightReq: null,
  view: 'graph',
  select: (selected) => set({ selected, highlightReq: null }),
  setHighlightReq: (highlightReq) => set({ highlightReq, selected: null }),
  setView: (view) => set({ view }),
}))
