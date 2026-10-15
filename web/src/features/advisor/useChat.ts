import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { keys, useLatestConversation } from '../../api/hooks'
import { streamChat } from '../../api/sse'
import type { AdvisorEvent } from '../../api/types'
import { useAdvisor, type Turn } from './store'

let nextId = 0
const turnId = () => `t${++nextId}`

export function useChat() {
  const qc = useQueryClient()
  const history = useLatestConversation()

  useEffect(() => {
    const convo = history.data
    if (!convo || useAdvisor.getState().turns.length) return
    // history carries each proposal's current status; seed the cache the cards read from
    for (const m of convo.messages)
      for (const e of m.events) if (e.type === 'proposal') qc.setQueryData(keys.proposal(e.proposal.id), e.proposal)
    useAdvisor.setState({
      conversationId: convo.id,
      turns: convo.messages.map((m) => ({ id: turnId(), role: m.role, events: m.events as AdvisorEvent[] })),
    })
  }, [history.data, qc])

  const send = async (text: string) => {
    const { streaming, conversationId, turns } = useAdvisor.getState()
    if (streaming || !text.trim()) return
    const user: Turn = { id: turnId(), role: 'user', events: [{ type: 'text', delta: text.trim() }] }
    const reply: Turn = { id: turnId(), role: 'assistant', events: [] }
    useAdvisor.setState({ turns: [...turns, user, reply], streaming: true, draft: '' })

    const push = (event: AdvisorEvent) =>
      useAdvisor.setState((s) => ({
        turns: s.turns.map((t) => (t.id === reply.id ? { ...t, events: [...t.events, event] } : t)),
        unread: s.visible ? s.unread : true,
      }))

    try {
      for await (const event of streamChat(text.trim(), conversationId)) {
        if (event.type === 'done') {
          useAdvisor.setState({ conversationId: event.conversation_id })
          continue
        }
        push(event)
        if (event.type === 'proposal') {
          qc.setQueryData(keys.proposal(event.proposal.id), event.proposal)
          // a proposal needs the student's eyes; on wide screens bring the panel back
          useAdvisor.getState().reveal()
        }
        if (event.type === 'profile_update') qc.invalidateQueries({ queryKey: keys.profile })
      }
    } catch (err) {
      push({ type: 'error', message: (err as Error).message })
    } finally {
      useAdvisor.setState({ streaming: false })
      qc.invalidateQueries({ queryKey: keys.plan })
    }
  }

  return { send }
}
