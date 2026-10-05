import { create } from 'zustand'
import type { AdvisorEvent } from '../../api/types'

export type Turn = { id: string; role: 'user' | 'assistant'; events: AdvisorEvent[] }

type AdvisorState = {
  conversationId: number | null
  turns: Turn[]
  streaming: boolean
  draft: string
  setDraft: (draft: string) => void
}

export const useAdvisor = create<AdvisorState>((set) => ({
  conversationId: null,
  turns: [],
  streaming: false,
  draft: '',
  setDraft: (draft) => set({ draft }),
}))
