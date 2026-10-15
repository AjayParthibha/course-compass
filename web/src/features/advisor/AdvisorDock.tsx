import { useEffect, useRef, useState } from 'react'
import { useMediaQuery } from '../../ui/useMediaQuery'
import AdvisorPanel from './AdvisorPanel'
import { useAdvisor } from './store'

// Side panel from `lg`; it starts open where there's room for the graph beside it.
const WIDE = '(min-width: 1024px)'
const ROOMY = '(min-width: 1440px)'

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5v6a1.5 1.5 0 0 1-1.5 1.5H8l-3.5 3v-3h0A1.5 1.5 0 0 1 3 10.5z" />
    </svg>
  )
}

type PillProps = { unread: boolean; onOpen: () => void; ref: React.Ref<HTMLButtonElement> }

/** What's left of the advisor when it's collapsed: a small message box that opens it. */
function AdvisorPill({ unread, onOpen, ref }: PillProps) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={onOpen}
      aria-expanded={false}
      aria-label={unread ? 'Open the advisor, new reply' : 'Ask the advisor'}
      className="group fixed right-4 bottom-4 z-30 flex h-12 w-[min(300px,calc(100vw-2rem))] items-center gap-2.5 rounded-full border border-line bg-white pr-1.5 pl-4 text-left shadow-[0_10px_28px_-10px_rgba(23,27,23,0.4),0_2px_6px_rgba(23,27,23,0.08)] transition-[box-shadow,border-color] hover:border-line-strong hover:shadow-[0_14px_32px_-10px_rgba(23,27,23,0.45),0_2px_6px_rgba(23,27,23,0.1)] motion-safe:animate-sheet-fade sm:right-5 sm:bottom-5"
    >
      <span className="text-ink">
        <ChatIcon />
      </span>
      <span className={`flex-1 truncate text-[14px] ${unread ? 'font-semibold text-ink' : 'text-muted'}`}>
        {unread ? 'New reply from your advisor' : 'Ask the advisor…'}
      </span>
      {unread && <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full bg-accent" />}
      <span
        aria-hidden="true"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-paper transition-transform group-hover:-translate-y-px"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M7 11.5v-9M3 6.5 7 2.5l4 4" />
        </svg>
      </span>
    </button>
  )
}

/** The advisor beside the plan: a docked panel on wide screens, a drawer from the right on narrow ones, and a small pill when collapsed. */
export default function AdvisorDock() {
  const wide = useMediaQuery(WIDE)
  const roomy = useMediaQuery(ROOMY)
  // narrow selectors: the dock shouldn't re-render for every streamed word
  const open = useAdvisor((s) => s.open)
  const sheetOpen = useAdvisor((s) => s.sheetOpen)
  const unread = useAdvisor((s) => s.unread)
  const { setOpen, setSheetOpen, setVisible } = useAdvisor.getState()
  const sideOpen = open ?? roomy
  const visible = wide ? sideOpen : sheetOpen
  // where focus goes back to after collapsing or closing, and whether opening was the student's click
  const opener = useRef<HTMLButtonElement>(null)
  const [focusOnOpen, setFocusOnOpen] = useState(false)

  useEffect(() => setVisible(visible), [visible, setVisible])

  const openByHand = (show: () => void) => {
    setFocusOnOpen(true)
    show()
  }
  const close = (hide: () => void) => {
    setFocusOnOpen(false)
    hide()
    requestAnimationFrame(() => opener.current?.focus())
  }

  if (wide) {
    return sideOpen ? (
      <aside aria-label="Advisor" className="sticky top-4 h-[calc(100vh-96px)] min-h-[520px] w-[min(380px,32vw)] min-w-[320px] shrink-0">
        <AdvisorPanel variant="side" focusInput={focusOnOpen} onClose={() => close(() => setOpen(false))} />
      </aside>
    ) : (
      <AdvisorPill ref={opener} unread={unread} onOpen={() => openByHand(() => setOpen(true))} />
    )
  }

  return sheetOpen ? (
    <AdvisorSheet focusInput={focusOnOpen} onClose={() => close(() => setSheetOpen(false))} />
  ) : (
    <AdvisorPill ref={opener} unread={unread} onOpen={() => openByHand(() => setSheetOpen(true))} />
  )
}

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'

function AdvisorSheet({ onClose: closeSheet, focusInput }: { onClose: () => void; focusInput: boolean }) {
  const dialog = useRef<HTMLElement>(null)
  const latestClose = useRef(closeSheet)
  useEffect(() => {
    latestClose.current = closeSheet
  }, [closeSheet])

  useEffect(() => {
    const onClose = () => latestClose.current()
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') return onClose()
      if (e.key !== 'Tab' || !dialog.current) return
      // keep Tab inside the drawer while it's open
      const items = Array.from(dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    if (!dialog.current?.contains(document.activeElement)) dialog.current?.focus()
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        tabIndex={-1}
        aria-hidden="true"
        onClick={closeSheet}
        className="absolute inset-0 border-0 bg-ink/30 motion-safe:animate-sheet-fade"
      />
      <section
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Advisor"
        className="absolute inset-y-0 right-0 flex w-[min(420px,92vw)] flex-col overflow-hidden rounded-l-2xl border-l border-line bg-paper shadow-[-8px_0_30px_rgba(23,27,23,0.18)] motion-safe:animate-drawer-in"
      >
        <AdvisorPanel variant="sheet" focusInput={focusInput} onClose={closeSheet} />
      </section>
    </div>
  )
}
