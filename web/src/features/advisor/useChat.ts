import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect } from 'react'
import { api, unwrap } from '../../api/client'
import { keys, useLatestConversation } from '../../api/hooks'
import { streamChat } from '../../api/sse'
import type { AdvisorEvent, Conversation } from '../../api/types'
import { useAdvisor, type Turn } from './store'

let nextId = 0
const turnId = () => `t${++nextId}`

export function useChat() {
  const qc = useQueryClient()
  const history = useLatestConversation()

  // history carries each proposal's current status; seed the cache the cards read from
  const show = useCallback(
    (convo: Conversation) => {
      for (const m of convo.messages)
        for (const e of m.events) if (e.type === 'proposal') qc.setQueryData(keys.proposal(e.proposal.id), e.proposal)
      useAdvisor
        .getState()
        .showChat(convo.id, convo.messages.map((m) => ({ id: turnId(), role: m.role, events: m.events as AdvisorEvent[] })))
    },
    [qc],
  )

  // the latest chat comes back on a new visit, unless one is already on screen (including a new one)
  useEffect(() => {
    const convo = history.data
    if (!convo || useAdvisor.getState().loaded) return
    show(convo)
  }, [history.data, show])

  /** open an earlier chat; asking there continues it */
  const open = async (id: number) => {
    if (useAdvisor.getState().streaming) return
    show(await unwrap(api.GET('/api/chat/{conversation_id}', { params: { path: { conversation_id: id } } })))
  }

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
          useAdvisor.setState({ conversationId: event.conversation_id, loaded: true })
          // a new chat now has a title; an old one moves to the top of the list
          qc.invalidateQueries({ queryKey: keys.chats })
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

  return { send, open }
}
