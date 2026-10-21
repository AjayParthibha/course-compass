import { useQueries } from '@tanstack/react-query'
import { useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router'
import { useMe, usePlan } from '../../api/hooks'
import { usePlanUI } from '../plan/store'
import ChatMenu from './ChatMenu'
import Message from './Message'
import { proposalQuery } from './proposalQuery'
import { latestProposalId } from './proposalState'
import { useAdvisor } from './store'
import { suggestPrompts } from './suggestions'
import { useChat } from './useChat'
import { Button } from '../../ui'

type Props = {
  variant: 'side' | 'sheet'
  onClose: () => void
  /** focus the message box when the panel appears (the student just opened it) */
  focusInput?: boolean
}

export default function AdvisorPanel({ variant, onClose, focusInput = false }: Props) {
  const { turns, streaming, draft, setDraft } = useAdvisor()
  const { send, open } = useChat()
  const scroller = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const events = useMemo(() => turns.flatMap((t) => t.events), [turns])
  // follow each proposal's current status, so discarding the newest one re-offers the one before it
  const current = useQueries({
    queries: events.flatMap((e) => (e.type === 'proposal' ? [proposalQuery(e.proposal)] : [])),
    combine: (results) => new Map(results.flatMap((r) => (r.data ? [[r.data.id, r.data] as const] : []))),
  })
  const latestId = latestProposalId(events, (p) => current.get(p.id) ?? p)
  const { data: plan } = usePlan()
  const { data: me } = useMe()
  const selected = usePlanUI((s) => s.selected)
  const suggestions = useMemo(() => {
    const asked = turns.filter((t) => t.role === 'user').map((t) => t.events.map((e) => (e.type === 'text' ? e.delta : '')).join(''))
    return suggestPrompts({ state: plan, selected, asked, maxCredits: me?.max_credits, termCaps: me?.term_caps })
  }, [plan, selected, turns, me])

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight })
  }, [turns])

  useEffect(() => {
    if (draft) input.current?.focus()
  }, [draft])

  useEffect(() => {
    if (focusInput) input.current?.focus()
  }, [focusInput])

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault()
    send(draft)
  }

  return (
    <div
      id="advisor-panel"
      className="flex h-full min-h-0 flex-col overflow-hidden bg-paper"
    >
      <div className="relative flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="m-0 text-[16px] font-extrabold">Advisor</h2>
          <p className="m-0 text-[12.5px] text-muted">Checks every change with the planner before suggesting it</p>
          <Link to="/profile" className="text-[12.5px] font-semibold whitespace-nowrap">
            What it knows
          </Link>
        </div>
        <div className="-mr-1.5 flex shrink-0 items-center">
        <ChatMenu onOpen={open} />
        <button
          type="button"
          onClick={onClose}
          aria-label={variant === 'side' ? 'Collapse advisor' : 'Close advisor'}
          aria-expanded={true}
          aria-controls="advisor-panel"
          title={variant === 'side' ? 'Collapse' : 'Close'}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border-0 bg-transparent text-muted hover:bg-chip hover:text-ink"
        >
          {variant === 'side' ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M6 3.5 10.5 8 6 12.5" />
              <path d="M11.5 3v10" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          )}
        </button>
        </div>
      </div>

      <div ref={scroller} className="flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <p className="m-0 text-[13px] text-muted">
            Ask about your plan, a requirement, or a course. The advisor proposes changes; nothing moves until you apply it.
          </p>
        )}
        {turns.map((t, i) => (
          <Message
            key={t.id}
            role={t.role}
            events={t.events}
            live={streaming && i === turns.length - 1}
            canAnswer={!streaming && i === turns.length - 1}
            onAnswer={send}
            latestProposalId={latestId}
          />
        ))}
      </div>

      <div className="flex flex-col gap-2 border-t border-line p-3">
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={streaming}
              onClick={() => send(s)}
              className="min-h-8 max-w-full rounded-2xl border border-line bg-white px-3 py-1 text-left text-[12.5px] leading-snug"
            >
              {s}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="flex items-end gap-2">
          <label htmlFor="advisor-input" className="sr-only">
            Message the advisor
          </label>
          <textarea
            id="advisor-input"
            ref={input}
            rows={2}
            value={draft}
            placeholder="Message the advisor"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            className="min-h-11 flex-1 resize-none rounded-md border border-[#C3C9BC] bg-white px-3 py-2"
          />
          <Button variant="primary" type="submit" disabled={streaming || !draft.trim()} className="h-11">
            Send
          </Button>
        </form>
      </div>
    </div>
  )
}
