import { useEffect, useId, useRef, useState } from 'react'
import { useChats } from '../../api/hooks'
import { useAdvisor } from './store'

const iconButton =
  'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border-0 bg-transparent text-muted hover:bg-chip hover:text-ink disabled:opacity-40'

function when(iso: string) {
  const d = new Date(iso)
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000)
  if (days < 1) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (days < 7) return d.toLocaleDateString([], { weekday: 'short' })
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

/** "New chat" and the list of earlier chats, in the advisor's header. */
export default function ChatMenu({ onOpen }: { onOpen: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const box = useRef<HTMLDivElement>(null)
  const streaming = useAdvisor((s) => s.streaming)
  const current = useAdvisor((s) => s.conversationId)
  const empty = useAdvisor((s) => s.turns.length === 0)
  const { data: chats, isLoading } = useChats(open)

  // close on a click outside or Escape
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    // the list spans the advisor's header (positioned there), not just these two buttons
    <div ref={box} className="flex items-center">
      <button
        type="button"
        onClick={() => useAdvisor.getState().newChat()}
        disabled={streaming || empty}
        aria-label="New chat"
        title="New chat"
        className={iconButton}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M8 3v10M3 8h10" />
        </svg>
      </button>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        disabled={streaming}
        aria-label="Earlier chats"
        aria-expanded={open}
        aria-controls={listId}
        title="Earlier chats"
        className={iconButton}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <circle cx="8" cy="8" r="5.5" />
          <path d="M8 5v3l2 1.5" />
        </svg>
      </button>
      {open && (
        <div
          id={listId}
          className="absolute top-full right-3 left-3 z-30 -mt-1 flex max-h-80 flex-col overflow-y-auto rounded-lg border border-line bg-white py-1 shadow-[0_8px_24px_rgba(23,27,23,0.12)]"
        >
          <span className="px-3 pt-1.5 pb-1 text-[11.5px] font-semibold tracking-wide text-muted uppercase">Earlier chats</span>
          {isLoading && <span className="px-3 py-2 text-[13px] text-muted">Loading…</span>}
          {chats?.length === 0 && <span className="px-3 py-2 text-[13px] text-muted">No earlier chats yet.</span>}
          <ul className="m-0 list-none p-0">
            {chats?.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  aria-current={c.id === current ? 'true' : undefined}
                  onClick={() => {
                    setOpen(false)
                    if (c.id !== current) onOpen(c.id)
                  }}
                  className={`flex w-full flex-col gap-0.5 border-0 px-3 py-2 text-left hover:bg-chip ${c.id === current ? 'bg-chip/60' : 'bg-transparent'}`}
                >
                  <span className="line-clamp-2 text-[13.5px] leading-snug">{c.title}</span>
                  <span className="text-[11.5px] text-muted">
                    {when(c.last_at)} · {c.questions} {c.questions === 1 ? 'question' : 'questions'}
                    {c.id === current && ' · open now'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
