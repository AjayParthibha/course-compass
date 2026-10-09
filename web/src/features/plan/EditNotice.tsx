import { useEffect, useRef, useState } from 'react'
import { usePlanEdits } from './edits'
import { usePlanUI, type EditNotice as Notice } from './store'

const UNDO_MS = 8000
const DONE_MS = 4000

function NoticeCard({ notice }: { notice: Notice }) {
  const dismiss = usePlanUI((s) => s.dismissNotice)
  const edits = usePlanEdits()
  const card = useRef<HTMLDivElement>(null)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const paused = notice.undoable && (hovered || focused)

  useEffect(() => {
    if (paused) return
    const t = setTimeout(dismiss, notice.undoable ? UNDO_MS : DONE_MS)
    return () => clearTimeout(t)
  }, [notice, paused, dismiss])

  return (
    <div
      ref={card}
      tabIndex={-1}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setFocused(false)}
      onKeyDown={(e) => e.key === 'Escape' && dismiss()}
      className="pointer-events-auto flex max-w-full items-center gap-3 rounded-lg bg-ink py-1.5 pr-1.5 pl-4 text-[13px] text-paper shadow-[0_6px_20px_rgba(23,27,23,0.25)]"
    >
      <span className="min-w-0 py-1">{notice.text}</span>
      <span className="flex shrink-0 items-center">
        {notice.undoable && (
          <button
            type="button"
            disabled={edits.pending}
            onClick={() => {
              // keep focus inside the notice once the Undo button goes away
              card.current?.focus()
              edits.undo()
            }}
            className="h-8 rounded-md border-0 bg-transparent px-2.5 font-semibold text-paper underline underline-offset-3 hover:bg-white/10 focus-visible:outline-paper"
          >
            Undo
          </button>
        )}
        <button
          type="button"
          aria-label="Dismiss"
          onClick={dismiss}
          className="flex h-8 w-8 items-center justify-center rounded-md border-0 bg-transparent text-paper hover:bg-white/10 focus-visible:outline-paper"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </span>
    </div>
  )
}

/** Confirms manual edits with an Undo, announced politely to screen readers. */
export default function EditNotice() {
  const notice = usePlanUI((s) => s.notice)
  const dismiss = usePlanUI((s) => s.dismissNotice)
  useEffect(() => dismiss, [dismiss])
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 left-4 z-30 flex sm:right-auto sm:left-5"
    >
      {notice && <NoticeCard notice={notice} />}
    </div>
  )
}
