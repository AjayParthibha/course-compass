import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { LONG_PRESS_MS, autoScrollStep, canDrop, dropColumn, pressIntent } from './graphInput'

export type DragState = {
  id: string
  from: string
  /** Column index under the pointer, or null when the pointer is away from the graph. */
  target: number | null
  phase: 'drag' | 'dropped' | 'returning'
}

type Session = {
  id: string
  el: HTMLElement
  pointerId: number
  pointerType: string
  x0: number
  y0: number
  t0: number
  x: number
  y: number
  offX: number
  offY: number
  phase: 'pending' | 'drag'
  timer: number
  raf: number
  target: number | null
  cols: { left: number; right: number }[]
}

type Options = {
  enabled: boolean
  scroller: RefObject<HTMLDivElement | null>
  content: RefObject<HTMLDivElement | null>
  terms: string[]
  currentTerm: string
  termOf: (id: string) => string | undefined
  onDrop: (id: string, term: string) => void
}

/** How long a dropped card waits for the plan to change before it returns to where it came from. */
const SETTLE_MS = 1200
const RETURN_MS = 220
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Pointer drag for planned cards. The dragged card is a visual copy only: positions always come from
 * plan data, so a move that fails or is cancelled sends the copy back to the card's real place.
 */
export function useCardDrag(options: Options) {
  const opts = useRef(options)
  useLayoutEffect(() => {
    opts.current = options
  })
  const [drag, setDrag] = useState<DragState | null>(null)
  const dragRef = useRef<DragState | null>(null)
  const clone = useRef<HTMLDivElement>(null)
  const session = useRef<Session | null>(null)
  const pending = useRef<{ id: string; term: string; rect: DOMRect; timer: number } | null>(null)
  const suppressClick = useRef(false)
  const startAt = useRef({ x: 0, y: 0 })

  const update = useCallback((next: DragState | null) => {
    dragRef.current = next
    setDrag(next)
  }, [])

  const api = useMemo(() => {
    const cardEl = (id: string) =>
      opts.current.content.current?.querySelector<HTMLElement>(`[data-card="${CSS.escape(id)}"]`) ?? null

    const finish = () => {
      if (pending.current) clearTimeout(pending.current.timer)
      pending.current = null
      update(null)
    }

    const flyBack = () => {
      const d = dragRef.current
      if (pending.current) clearTimeout(pending.current.timer)
      pending.current = null
      const el = clone.current
      const card = d && cardEl(d.id)
      if (!d || !el || !card || reduced()) return finish()
      update({ ...d, phase: 'returning' })
      const from = el.getBoundingClientRect()
      const to = card.getBoundingClientRect()
      el.animate(
        [
          { transform: `translate3d(${from.left}px, ${from.top}px, 0)` },
          { transform: `translate3d(${to.left}px, ${to.top}px, 0)` },
        ],
        { duration: RETURN_MS, easing: 'cubic-bezier(.2,.75,.25,1)', fill: 'forwards' },
      ).onfinish = finish
    }

    const targetAt = (s: Session) => {
      const sc = opts.current.scroller.current
      const ct = opts.current.content.current
      if (!sc || !ct) return null
      const sr = sc.getBoundingClientRect()
      const near = s.y > sr.top - 80 && s.y < sr.bottom + 80
      const col = near ? dropColumn(s.x - ct.getBoundingClientRect().left, s.cols) : -1
      return col < 0 ? null : col
    }

    const frame = () => {
      const s = session.current
      if (!s) return
      s.raf = 0
      const sc = opts.current.scroller.current
      if (!sc) return
      const sr = sc.getBoundingClientRect()
      const target = targetAt(s)
      if (clone.current) clone.current.style.transform = `translate3d(${s.x - s.offX}px, ${s.y - s.offY}px, 0)`
      const dx = autoScrollStep(s.x, sr.left, sr.right)
      const dy = autoScrollStep(s.y, 0, window.innerHeight, 40, 14)
      if (dx) sc.scrollLeft += dx
      if (dy) window.scrollBy(0, dy)
      if (target !== s.target) {
        s.target = target
        const d = dragRef.current
        if (d) update({ ...d, target })
      }
      if (dx || dy) s.raf = requestAnimationFrame(frame)
    }
    const schedule = (s: Session) => {
      if (!s.raf) s.raf = requestAnimationFrame(frame)
    }

    const end = (s: Session) => {
      clearTimeout(s.timer)
      cancelAnimationFrame(s.raf)
      delete s.el.dataset.pressing
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onCancel)
      window.removeEventListener('keydown', onKey, true)
      document.body.style.removeProperty('user-select')
      document.body.style.removeProperty('-webkit-user-select')
      session.current = null
      // the click that follows pointerup is swallowed by onClickCapture; don't let it eat a later one
      setTimeout(() => (suppressClick.current = false), 0)
    }

    const start = (s: Session) => {
      const { content, termOf } = opts.current
      const from = termOf(s.id)
      if (!content.current || !from) return end(s)
      const r = s.el.getBoundingClientRect()
      s.offX = s.x0 - r.left
      s.offY = s.y0 - r.top
      s.phase = 'drag'
      s.cols = Array.from(content.current.querySelectorAll<HTMLElement>('[data-term-col]')).map((el) => ({
        left: el.offsetLeft,
        right: el.offsetLeft + el.offsetWidth,
      }))
      delete s.el.dataset.pressing
      suppressClick.current = true
      document.body.style.setProperty('user-select', 'none')
      document.body.style.setProperty('-webkit-user-select', 'none')
      if (s.pointerType === 'touch') navigator.vibrate?.(8)
      startAt.current = { x: r.left, y: r.top }
      update({ id: s.id, from, target: null, phase: 'drag' })
      schedule(s)
    }

    const onMove = (e: PointerEvent) => {
      const s = session.current
      if (!s || e.pointerId !== s.pointerId) return
      s.x = e.clientX
      s.y = e.clientY
      if (s.phase === 'drag') return schedule(s)
      const intent = pressIntent(s.pointerType, e.timeStamp - s.t0, Math.hypot(s.x - s.x0, s.y - s.y0))
      if (intent === 'drag') start(s)
      else if (intent === 'cancel') end(s)
    }

    const onUp = (e: PointerEvent) => {
      const s = session.current
      if (!s || e.pointerId !== s.pointerId) return
      if (s.phase !== 'drag') return end(s)
      // a quick flick can end before the next frame runs, so read the drop target now
      const target = targetAt(s)
      const rect =
        clone.current?.getBoundingClientRect() ??
        new DOMRect(s.x - s.offX, s.y - s.offY, s.el.offsetWidth, s.el.offsetHeight)
      end(s)
      const d = dragRef.current
      const { terms, currentTerm, onDrop } = opts.current
      const term = target == null ? null : terms[target]
      if (!d || !term || !canDrop(d.from, term, terms, currentTerm).ok) return flyBack()
      update({ ...d, target, phase: 'dropped' })
      pending.current = { id: d.id, term, rect, timer: window.setTimeout(flyBack, SETTLE_MS) }
      onDrop(d.id, term)
    }

    const onCancel = (e: PointerEvent) => {
      const s = session.current
      if (!s || e.pointerId !== s.pointerId) return
      const dragging = s.phase === 'drag'
      end(s)
      if (dragging) flyBack()
    }

    const onKey = (e: KeyboardEvent) => {
      const s = session.current
      if (e.key !== 'Escape' || !s) return
      e.preventDefault()
      e.stopPropagation()
      const dragging = s.phase === 'drag'
      end(s)
      if (dragging) flyBack()
    }

    const onPointerDown = (e: React.PointerEvent) => {
      if (!opts.current.enabled || e.button !== 0 || session.current || dragRef.current) return
      const el = (e.target as HTMLElement).closest<HTMLElement>('[data-drag]')
      if (!el?.dataset.card) return
      suppressClick.current = false
      const s: Session = {
        id: el.dataset.card,
        el,
        pointerId: e.pointerId,
        pointerType: e.pointerType,
        x0: e.clientX,
        y0: e.clientY,
        t0: e.timeStamp,
        x: e.clientX,
        y: e.clientY,
        offX: 0,
        offY: 0,
        phase: 'pending',
        timer: 0,
        raf: 0,
        target: null,
        cols: [],
      }
      session.current = s
      if (e.pointerType === 'touch') {
        el.dataset.pressing = ''
        s.timer = window.setTimeout(() => {
          if (session.current !== s) return
          if (pressIntent('touch', LONG_PRESS_MS, Math.hypot(s.x - s.x0, s.y - s.y0)) === 'drag') start(s)
          else end(s)
        }, LONG_PRESS_MS)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
      window.addEventListener('pointercancel', onCancel)
      window.addEventListener('keydown', onKey, true)
    }

    /** Called after the plan re-renders: hands back where a dropped card was let go, if it landed. */
    const takeDrop = (): { id: string; rect: DOMRect } | null => {
      const p = pending.current
      if (!p) return null
      if (opts.current.termOf(p.id) !== p.term) {
        flyBack()
        return null
      }
      finish()
      return { id: p.id, rect: p.rect }
    }

    return {
      onPointerDown,
      takeDrop,
      onClickCapture: (e: React.MouseEvent) => {
        if (!suppressClick.current) return
        suppressClick.current = false
        e.preventDefault()
        e.stopPropagation()
      },
      onContextMenu: (e: React.MouseEvent) => {
        if (session.current || dragRef.current) e.preventDefault()
      },
      dispose: () => {
        if (session.current) end(session.current)
        if (pending.current) clearTimeout(pending.current.timer)
      },
    }
  }, [update])

  // Place the copy before it paints; after that the pointer handler moves it directly.
  const dragId = drag?.id
  useLayoutEffect(() => {
    if (dragId && clone.current) {
      clone.current.style.transform = `translate3d(${startAt.current.x}px, ${startAt.current.y}px, 0)`
    }
  }, [dragId])

  // Once a touch drag has started, stop the finger from also scrolling the page.
  useEffect(() => {
    const el = options.content.current
    if (!el) return
    const block = (e: TouchEvent) => {
      if (session.current?.phase === 'drag') e.preventDefault()
    }
    el.addEventListener('touchmove', block, { passive: false })
    return () => el.removeEventListener('touchmove', block)
  }, [options.content])

  useEffect(() => api.dispose, [api])

  return { drag, clone, ...api }
}
