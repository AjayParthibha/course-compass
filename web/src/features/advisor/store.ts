import { create } from 'zustand'
import type { AdvisorEvent } from '../../api/types'

export type Turn = { id: string; role: 'user' | 'assistant'; events: AdvisorEvent[] }

const PREF_KEY = 'cc-advisor-open'

function readPref(): boolean | null {
  try {
    const v = localStorage.getItem(PREF_KEY)
    return v === '1' ? true : v === '0' ? false : null
  } catch {
    return null
  }
}

function writePref(open: boolean) {
  try {
    localStorage.setItem(PREF_KEY, open ? '1' : '0')
  } catch {
    // private mode or blocked storage: the choice just lasts for this visit
  }
}

type AdvisorState = {
  conversationId: number | null
  turns: Turn[]
  streaming: boolean
  draft: string
  /** side panel on wide screens; null follows the screen-size default until the student picks */
  open: boolean | null
  /** drawer from the right on narrow screens */
  sheetOpen: boolean
  /** whether the conversation is on screen right now (set by the dock) */
  visible: boolean
  unread: boolean
  setDraft: (draft: string) => void
  /** the student's own choice, remembered across visits */
  setOpen: (open: boolean) => void
  setSheetOpen: (open: boolean) => void
  setVisible: (visible: boolean) => void
  /** bring the side panel back for something that needs attention, without changing the saved choice */
  reveal: () => void
  /** start a question from elsewhere in the app and show the advisor */
  ask: (text: string) => void
}

export const useAdvisor = create<AdvisorState>((set) => ({
  conversationId: null,
  turns: [],
  streaming: false,
  draft: '',
  open: readPref(),
  sheetOpen: false,
  visible: false,
  unread: false,
  setDraft: (draft) => set({ draft }),
  setOpen: (open) => {
    writePref(open)
    set({ open })
  },
  setSheetOpen: (sheetOpen) => set({ sheetOpen }),
  setVisible: (visible) => set((s) => ({ visible, unread: visible ? false : s.unread })),
  reveal: () => set({ open: true }),
  ask: (draft) => set({ draft, open: true, sheetOpen: true }),
}))
