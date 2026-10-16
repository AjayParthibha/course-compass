import { useEffect, useRef, useState } from 'react'
import { useMediaQuery } from '../../ui/useMediaQuery'
import AdvisorPanel from './AdvisorPanel'
import { useAdvisor, WIDE_QUERY } from './store'

// The side panel starts open where there's room for the graph beside it.
const ROOMY = '(min-width: 1440px)'

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5v6a1.5 1.5 0 0 1-1.5 1.5H8l-3.5 3v-3h0A1.5 1.5 0 0 1 3 10.5z" />
    </svg>
  )
}

// the plan keeps at least this much room beside the panel (matches max-w on the aside)
const PLAN_ROOM = 480
const MIN_WIDTH = 320
const WIDTH_KEY = 'advisor-width'

// the aside's own default, w-[min(380px,32vw)] min-w-[320px]
const defaultWidth = () => Math.round(Math.max(MIN_WIDTH, Math.min(380, window.innerWidth * 0.32)))

/** A col-resize cursor everywhere and no text selection while dragging; returns the undo. */
function holdResizeCursor() {
  const { cursor, userSelect } = document.body.style
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  return () => {
    document.body.style.cursor = cursor
    document.body.style.userSelect = userSelect
  }
}

const clampWidth = (w: number) => Math.round(Math.max(MIN_WIDTH, Math.min(w, window.innerWidth - PLAN_ROOM)))

/** The docked panel's width in px once the student has dragged it; null keeps the default. */
function useSavedWidth() {
  const [width, setWidth] = useState<number | null>(() => {
    try {
      const saved = Number(localStorage.getItem(WIDTH_KEY))
      return saved > 0 ? saved : null
    } catch {
      return null
    }
  })
  const save = (w: number | null) => {
    setWidth(w)
    try {
      if (w === null) localStorage.removeItem(WIDTH_KEY)
      else localStorage.setItem(WIDTH_KEY, String(w))
    } catch {
      // private windows can refuse storage; the width just won't be remembered
    }
  }
  return [width, save] as const
}

/** Drag the panel's left edge to resize it; arrow keys work too, and a double-click resets it. */
function ResizeHandle({ width, onResize }: { width: number | null; onResize: (w: number | null) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const current = () => ref.current?.parentElement?.getBoundingClientRect().width ?? MIN_WIDTH

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    const handle = e.currentTarget
    handle.setPointerCapture(e.pointerId)
    const startX = e.clientX
    const startWidth = current()
    const release = holdResizeCursor()
    // the panel sits on the right, so dragging left makes it wider
    const move = (ev: PointerEvent) => onResize(clampWidth(startWidth + startX - ev.clientX))
    const end = () => {
      release()
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', end)
      handle.removeEventListener('pointercancel', end)
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', end)
    handle.addEventListener('pointercancel', end)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 64 : 16
    if (e.key === 'ArrowLeft') onResize(clampWidth(current() + step))
    else if (e.key === 'ArrowRight') onResize(clampWidth(current() - step))
    else if (e.key === 'Home') onResize(null)
    else return
    e.preventDefault()
  }

  return (
    <div
      ref={ref}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the advisor"
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={Math.max(MIN_WIDTH, window.innerWidth - PLAN_ROOM)}
      aria-valuenow={width ?? defaultWidth()}
      title="Drag to resize · double-click to reset"
      tabIndex={0}
      onPointerDown={onPointerDown}
      onDoubleClick={() => onResize(null)}
      onKeyDown={onKeyDown}
      className="group absolute inset-y-0 -left-1.5 z-10 w-3 cursor-col-resize touch-none focus-visible:outline-none"
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-transparent transition-colors group-hover:bg-line-strong group-focus-visible:bg-ink group-active:bg-ink"
      />
    </div>
  )
}

type OpenerProps = { unread: boolean; onOpen: () => void; ref: React.Ref<HTMLButtonElement> }

/** What's left of the docked advisor when it's collapsed: a slim full-height tab on the right edge that opens it. */
function AdvisorRail({ unread, onOpen, ref }: OpenerProps) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={onOpen}
      aria-expanded={false}
      aria-label={unread ? 'Open the advisor, new reply' : 'Open the advisor'}
      title="Open the advisor"
      className={`flex w-11 shrink-0 flex-col items-center gap-3 border-l border-line bg-paper py-4 transition-colors hover:bg-chip hover:text-ink focus-visible:-outline-offset-2! motion-safe:animate-sheet-fade ${unread ? 'text-ink' : 'text-muted'}`}
    >
      <ChatIcon />
      <span className="text-[13px] font-semibold tracking-wide [writing-mode:vertical-rl]">Advisor</span>
      {unread && <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full bg-accent" />}
    </button>
  )
}

/** What's left of the drawer on narrow screens: a small message box that opens it. */
function AdvisorPill({ unread, onOpen, ref }: OpenerProps) {
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

/**
 * The advisor beside the plan: a full-height panel docked on the right on wide screens (a slim tab on the
 * right edge when collapsed), and a drawer from the right on narrow ones (a small pill when closed).
 */
export default function AdvisorDock() {
  const wide = useMediaQuery(WIDE_QUERY)
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
  const [width, setWidth] = useSavedWidth()

  useEffect(() => setVisible(visible), [visible, setVisible])
  // the drawer belongs to narrow screens and to this page; don't let it reappear after a resize or a return visit
  useEffect(() => {
    if (wide) setSheetOpen(false)
  }, [wide, setSheetOpen])
  useEffect(() => () => setSheetOpen(false), [setSheetOpen])

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
      <aside
        aria-label="Advisor"
        style={width ? { width } : undefined}
        className="relative flex w-[min(380px,32vw)] max-w-[calc(100vw-480px)] min-w-[320px] shrink-0 flex-col border-l border-line"
      >
        <ResizeHandle width={width} onResize={setWidth} />
        <AdvisorPanel variant="side" focusInput={focusOnOpen} onClose={() => close(() => setOpen(false))} />
      </aside>
    ) : (
      <AdvisorRail ref={opener} unread={unread} onOpen={() => openByHand(() => setOpen(true))} />
    )
  }

  return sheetOpen ? (
    <AdvisorSheet focusInput={focusOnOpen} onClose={() => close(() => setSheetOpen(false))} />
  ) : (
    <AdvisorPill ref={opener} unread={unread} onOpen={() => openByHand(() => setSheetOpen(true))} />
  )
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'

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
      const active = document.activeElement as HTMLElement | null
      // focus can sit on the drawer itself (or plain text in it), which isn't one of the items
      const loose = !active || !items.includes(active)
      if (e.shiftKey && (active === first || loose)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (active === last || loose)) {
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
