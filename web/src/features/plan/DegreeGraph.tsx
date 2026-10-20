import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMe } from '../../api/hooks'
import type { Placement, PlanState } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { cardState } from './cards'
import { CardClone, GraphCard } from './GraphCard'
import GraphEdges from './GraphEdges'
import { CARD_W, chainSteps, edgeKey, type Box } from './graphGeometry'
import { canDrop, navTarget, type DropCheck } from './graphInput'
import { chain, layoutPlan } from './layout'
import { useCardDrag } from './useCardDrag'

const NO_GHOSTS: Placement[] = []
const MOVE_MS = 380
const EASE = 'cubic-bezier(.2,.75,.25,1)'
const PEEK = 24
const PREVIEW_DELAY = 90
const NAV_KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'])

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const scrollBehavior = (): ScrollBehavior => (reducedMotion() ? 'auto' : 'smooth')

const HELP =
  'Use the arrow keys to move between courses. Press Enter or Space to see details. Planned courses can be moved to another term from the details panel.'

const blockedLabel: Record<NonNullable<DropCheck['reason']>, string> = {
  same: '',
  current: 'Under way',
  past: 'Past term',
}

type Geometry = { boxes: Map<string, Box>; w: number; h: number }
const EMPTY: Geometry = { boxes: new Map(), w: 0, h: 0 }

function sameGeometry(a: Geometry, b: Geometry) {
  if (a.w !== b.w || a.h !== b.h || a.boxes.size !== b.boxes.size) return false
  for (const [id, x] of a.boxes) {
    const y = b.boxes.get(id)
    if (!y || x.x !== y.x || x.y !== y.y || x.w !== y.w || x.h !== y.h) return false
  }
  return true
}

const round = (n: number) => Math.round(n * 10) / 10

type Props = {
  state: PlanState
  selected?: string | null
  highlight?: Set<string> | null
  moved?: Set<string>
  ghosts?: Placement[]
  readOnly?: boolean
  onSelect?: (id: string | null) => void
  onMove?: (placement: Placement, term: string) => void
}

export default function DegreeGraph({
  state,
  selected = null,
  highlight = null,
  moved,
  ghosts = NO_GHOSTS,
  readOnly,
  onSelect,
  onMove,
}: Props) {
  const { plan, audit, edges } = state
  const { data: me } = useMe()
  const uid = useId()
  const helpId = `${uid}-help`
  const scroller = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const interactive = !!onSelect

  const byId = useMemo(() => new Map(plan.placements.map((p) => [p.id, p])), [plan.placements])
  const ordered = useMemo(() => layoutPlan(plan.placements, plan.terms, audit), [plan.placements, plan.terms, audit])
  const problems = useMemo(
    () => new Set(state.violations.filter((v) => v.blocking).flatMap((v) => v.placement_ids)),
    [state.violations],
  )

  // Callers may pass a fresh Set with the same contents on every render; key them by contents.
  const highlightKey = highlight ? [...highlight].sort().join('\n') : null
  const movedKey = moved?.size ? [...moved].sort().join('\n') : ''
  const highlightSet = useMemo(
    () => (highlightKey == null ? null : new Set(highlightKey ? highlightKey.split('\n') : [])),
    [highlightKey],
  )
  const movedSet = useMemo(() => new Set(movedKey ? movedKey.split('\n') : []), [movedKey])

  // A selection that no longer exists (undone, or replaced by a proposal) counts as none.
  const active = selected && byId.has(selected) ? selected : null
  const [hovered, setHovered] = useState<string | null>(null)
  const preview = !active && !highlightSet && !movedSet.size && hovered && byId.has(hovered) ? hovered : null
  const chainId = active ?? preview

  const focus = useMemo(() => {
    if (highlightSet) return highlightSet
    if (!chainId) return null
    const { up, down } = chain(chainId, edges)
    return new Set([...up, ...down])
  }, [highlightSet, chainId, edges])

  const lit = useMemo(() => {
    if (focus) return new Set(edges.filter((e) => focus.has(e.source) && focus.has(e.target)).map(edgeKey))
    if (movedSet.size) return new Set(edges.filter((e) => movedSet.has(e.source) || movedSet.has(e.target)).map(edgeKey))
    return null
  }, [focus, movedSet, edges])
  const steps = useMemo(() => (chainId && !highlightSet ? chainSteps(chainId, edges) : null), [chainId, highlightSet, edges])
  const litKey = highlightKey != null ? `h:${highlightKey}` : chainId ? `c:${chainId}` : movedKey ? `m:${movedKey}` : null

  const currentIndex = plan.terms.indexOf(plan.current_term)
  const columns = useMemo(
    () =>
      plan.terms.map((term, i) => {
        const cards = ordered[i]
        return {
          term,
          cards,
          ghosts: ghosts.filter((g) => g.term === term),
          credits: cards.reduce((n, p) => n + p.credits, 0),
          cap: me && i >= currentIndex ? (me.term_caps[term] ?? me.max_credits) : null,
        }
      }),
    [plan.terms, ordered, ghosts, me, currentIndex],
  )
  const layoutKey = columns
    .map((c) => `${c.term}:${c.cards.map((p) => p.id).join(',')}|${c.ghosts.map((g) => g.id).join(',')}`)
    .join(';')

  // ---- drag ----
  const termOf = useCallback((id: string) => byId.get(id)?.term, [byId])
  const dnd = useCardDrag({
    enabled: !readOnly && !!onMove,
    scroller,
    content,
    terms: plan.terms,
    currentTerm: plan.current_term,
    termOf,
    onDrop: (id, term) => {
      const p = byId.get(id)
      if (p) onMove?.(p, term)
    },
  })
  const { drag, clone, takeDrop } = dnd
  const dragged = drag ? byId.get(drag.id) : undefined

  // How far each card's ring reaches outside it (GraphCard: the selection outline sits 4px
  // out, a problem ring 2px), so arrows end on the outline instead of under it
  const liftedId = drag?.id ?? null
  const outlines = useMemo(() => {
    const out = new Map<string, number>()
    for (const id of problems) if (id !== liftedId) out.set(id, 2)
    if (active && active !== liftedId) out.set(active, 4)
    return out
  }, [problems, active, liftedId])

  // ---- measuring ----
  const [geo, setGeo] = useState<Geometry>(EMPTY)
  const last = useRef<Map<string, Box> | null>(null)
  const followUntil = useRef(0)
  const followRaf = useRef(0)

  const measure = useCallback(() => {
    const root = content.current
    if (!root) return
    const origin = root.getBoundingClientRect()
    const boxes = new Map<string, Box>()
    for (const el of Array.from(root.querySelectorAll<HTMLElement>('[data-card]'))) {
      const r = el.getBoundingClientRect()
      boxes.set(el.dataset.card!, {
        x: round(r.left - origin.left),
        y: round(r.top - origin.top),
        w: round(r.width),
        h: round(r.height),
      })
    }
    last.current = boxes
    const next = { boxes, w: Math.ceil(origin.width), h: Math.ceil(origin.height) }
    setGeo((prev) => (sameGeometry(prev, next) ? prev : next))
  }, [])

  // Re-measure every frame while cards are animating so the lines travel with them.
  const follow = useCallback(
    (ms: number) => {
      followUntil.current = Math.max(followUntil.current, performance.now() + ms)
      if (followRaf.current) return
      const tick = () => {
        measure()
        followRaf.current = performance.now() < followUntil.current ? requestAnimationFrame(tick) : 0
      }
      followRaf.current = requestAnimationFrame(tick)
    },
    [measure],
  )

  useEffect(() => {
    const root = content.current
    if (!root) return
    let raf = 0
    const soon = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(measure)
    }
    const ro = new ResizeObserver(soon)
    ro.observe(root)
    document.fonts?.ready.then(soon)
    document.fonts?.addEventListener('loadingdone', soon)
    return () => {
      ro.disconnect()
      cancelAnimationFrame(raf)
      cancelAnimationFrame(followRaf.current)
      followRaf.current = 0
      document.fonts?.removeEventListener('loadingdone', soon)
    }
  }, [measure])

  // FLIP: when cards change place, start each from where it was and glide to where it is now.
  useLayoutEffect(() => {
    const root = content.current
    if (!root) return
    const dropped = takeDrop()
    const prev = last.current
    const els = Array.from(root.querySelectorAll<HTMLElement>('[data-card]'))
    if (prev && !reducedMotion()) {
      for (const el of els) el.getAnimations().forEach((a) => a.id === 'flip' && a.cancel())
      const origin = root.getBoundingClientRect()
      const rects = els.map((el) => el.getBoundingClientRect())
      els.forEach((el, i) => {
        const id = el.dataset.card!
        const r = rects[i]
        const from =
          dropped?.id === id
            ? { x: dropped.rect.left - origin.left, y: dropped.rect.top - origin.top }
            : prev.get(id)
        let anim: Animation
        if (!from) {
          anim = el.animate([{ opacity: 0, transform: 'scale(.96)' }, { opacity: 1, transform: 'none' }], {
            duration: 220,
            easing: 'ease-out',
          })
        } else {
          const dx = from.x - (r.left - origin.left)
          const dy = from.y - (r.top - origin.top)
          if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return
          anim = el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], {
            duration: MOVE_MS,
            easing: EASE,
          })
        }
        anim.id = 'flip'
      })
      follow(MOVE_MS + 40)
    }
    measure()
  }, [layoutKey, takeDrop, follow, measure])

  // ---- scrolling ----
  const placedAtStart = useRef(false)
  useLayoutEffect(() => {
    const sc = scroller.current
    if (placedAtStart.current || !sc || !plan.terms.length) return
    placedAtStart.current = true
    const col = content.current?.querySelector<HTMLElement>(`[data-term-col="${currentIndex}"]`)
    if (currentIndex > 0 && col) sc.scrollLeft = col.offsetLeft - PEEK
  }, [plan.terms.length, currentIndex])

  const [fade, setFade] = useState({ start: false, end: false })
  const updateFade = useCallback(() => {
    const sc = scroller.current
    if (!sc) return
    const start = sc.scrollLeft > 2
    const end = sc.scrollLeft + sc.clientWidth < sc.scrollWidth - 2
    setFade((f) => (f.start === start && f.end === end ? f : { start, end }))
  }, [])
  useEffect(updateFade, [updateFade, geo.w])
  useEffect(() => {
    const sc = scroller.current
    if (!sc) return
    let raf = 0
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(() => ((raf = 0), updateFade()))
    }
    sc.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      sc.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [updateFade])

  // Bring a newly selected course into view sideways (e.g. picked from the details panel).
  useEffect(() => {
    const sc = scroller.current
    const el = active ? content.current?.querySelector<HTMLElement>(`[data-card="${CSS.escape(active)}"]`) : null
    if (!sc || !el) return
    const s = sc.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    if (r.left < s.left + 8) sc.scrollBy({ left: r.left - s.left - PEEK, behavior: scrollBehavior() })
    else if (r.right > s.right - 8) sc.scrollBy({ left: r.right - s.right + PEEK, behavior: scrollBehavior() })
  }, [active])

  // ---- focus ----
  const [current, setCurrent] = useState<string | null>(null)
  const focused = useRef<string | null>(null)
  const firstCard = columns[Math.max(currentIndex, 0)]?.cards[0]?.id ?? columns.find((c) => c.cards.length)?.cards[0]?.id
  const tabStop = [current, active].find((id) => id && byId.has(id)) ?? firstCard ?? null

  // A card that changes term is a new element; keep keyboard focus on it.
  useLayoutEffect(() => {
    const id = focused.current
    if (!id || (document.activeElement && document.activeElement !== document.body)) return
    content.current?.querySelector<HTMLElement>(`[data-card="${CSS.escape(id)}"]`)?.focus({ preventScroll: true })
  }, [layoutKey])

  const cardFrom = (target: EventTarget) => {
    const el = (target as HTMLElement).closest<HTMLElement>('[data-card]')
    const id = el?.dataset.card
    return el && id && byId.has(id) ? { el, id } : null
  }

  const onClick = (e: React.MouseEvent) => {
    if (!onSelect) return
    const card = cardFrom(e.target)
    if (!card) {
      if (!(e.target as HTMLElement).closest('[data-card]') && active) onSelect(null)
      return
    }
    setCurrent(card.id)
    if (card.id === active) {
      onSelect(null)
      // a mouse click on the selected card lets go of it entirely; Enter or Space keeps focus
      if (e.detail > 0) card.el.blur()
    } else {
      onSelect(card.id)
    }
  }

  const navColumns = useMemo(
    () =>
      columns.map((c) =>
        c.cards.map((p, row) => ({ id: p.id, y: geo.boxes.get(p.id)?.y ?? row * 76 })),
      ),
    [columns, geo.boxes],
  )

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!interactive) return
    const card = cardFrom(e.target)
    if (!card) return
    if (e.key === 'Escape') {
      if (active) {
        e.preventDefault()
        onSelect?.(null)
      }
      return
    }
    if (!NAV_KEYS.has(e.key) || e.altKey || e.ctrlKey || e.metaKey) return
    const next = navTarget(navColumns, card.id, e.key)
    e.preventDefault()
    if (!next) return
    setCurrent(next)
    content.current?.querySelector<HTMLElement>(`[data-card="${CSS.escape(next)}"]`)?.focus()
  }

  // ---- hover preview ----
  const hoverTimer = useRef(0)
  useEffect(() => () => clearTimeout(hoverTimer.current), [])
  const onPointerOver = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse' || drag) return
    const id = cardFrom(e.target)?.id ?? null
    clearTimeout(hoverTimer.current)
    hoverTimer.current = window.setTimeout(() => setHovered(id), PREVIEW_DELAY)
  }
  const onPointerLeave = () => {
    clearTimeout(hoverTimer.current)
    setHovered(null)
  }

  // ---- render ----
  const dropInfo = (term: string): DropCheck | null =>
    drag && drag.phase === 'drag' ? canDrop(drag.from, term, plan.terms, plan.current_term) : null
  const target = drag?.target != null ? plan.terms[drag.target] : null
  const targetCheck = target ? dropInfo(target) : null

  return (
    <div className="relative">
      <p id={helpId} hidden>
        {HELP}
      </p>
      <div
        ref={scroller}
        data-dragging={drag ? '' : undefined}
        className="overflow-x-auto overscroll-x-contain [scrollbar-width:thin] max-sm:snap-x max-sm:snap-proximity max-sm:scroll-pl-4 data-dragging:snap-none"
      >
        <div
          ref={content}
          data-dragging={drag?.phase === 'drag' ? '' : undefined}
          data-blocked={targetCheck && targetCheck.reason !== 'same' && !targetCheck.ok ? '' : undefined}
          className="relative isolate inline-flex min-h-[320px] min-w-full gap-5 px-4 pt-4 pb-6 data-blocked:**:cursor-not-allowed! data-dragging:**:cursor-grabbing"
          onClick={onClick}
          onClickCapture={dnd.onClickCapture}
          onKeyDown={onKeyDown}
          onPointerDown={dnd.onPointerDown}
          onPointerOver={onPointerOver}
          onPointerLeave={onPointerLeave}
          onContextMenu={dnd.onContextMenu}
          onFocus={(e) => {
            const card = cardFrom(e.target)
            if (card) {
              focused.current = card.id
              setCurrent(card.id)
            }
          }}
          onBlur={(e) => {
            const el = e.target
            queueMicrotask(() => {
              if (el.isConnected && focused.current === (el as HTMLElement).dataset.card) focused.current = null
            })
          }}
        >
          <GraphEdges edges={edges} boxes={geo.boxes} width={geo.w} height={geo.h} lit={lit} litKey={litKey} steps={steps} outlines={outlines} />
          {columns.map((col, i) => {
            const isCurrent = i === currentIndex
            const check = dropInfo(col.term)
            const hoveredCol = drag?.phase === 'drag' && drag.target === i
            const blocked = check && !check.ok && check.reason !== 'same'
            const over = col.cap != null && col.credits > col.cap
            const projected = hoveredCol && check?.ok && dragged ? col.credits + dragged.credits : null
            const projectedOver = projected != null && col.cap != null && projected > col.cap
            let backdrop = isCurrent ? 'bg-ground' : ''
            if (hoveredCol && check?.ok) backdrop = 'bg-[#EEF1E9] border-[1.5px] border-dashed border-ink/45'
            else if (hoveredCol && blocked) backdrop = 'bg-accent/[.04] border-[1.5px] border-dashed border-accent/45'
            else if (blocked)
              backdrop = `${isCurrent ? 'bg-ground' : ''} bg-[repeating-linear-gradient(135deg,transparent_0_6px,rgb(23_27_23/.05)_6px_7px)]`
            const headingId = `${uid}-term-${i}`
            return (
              <div
                key={col.term}
                data-term-col={i}
                role="group"
                aria-labelledby={headingId}
                className="relative flex shrink-0 snap-start flex-col"
                style={{ width: CARD_W }}
              >
                <div
                  className={`pointer-events-none absolute -inset-x-2 -top-2 -bottom-3 -z-10 rounded-xl transition-colors duration-150 motion-reduce:transition-none ${backdrop}`}
                />
                <h3
                  id={headingId}
                  className={`m-0 mb-3 flex h-6 items-baseline justify-between gap-2 border-b pb-1 text-[12.5px] ${
                    isCurrent ? 'border-ink font-bold' : 'border-line-soft font-semibold'
                  } ${i < currentIndex ? 'text-muted' : ''}`}
                >
                  <span className="sr-only">
                    {termLabel(col.term, true)}
                    {isCurrent ? ', current term' : ''}, {col.credits} credits
                    {over ? `, over your ${col.cap}-credit limit` : ''}
                  </span>
                  <span aria-hidden="true" className="whitespace-nowrap">
                    {termLabel(col.term)}
                  </span>
                  <span
                    aria-hidden="true"
                    title={over ? `Over your ${col.cap}-credit limit for ${termLabel(col.term)}` : undefined}
                    className={`font-mono text-[11px] font-normal whitespace-nowrap ${
                      hoveredCol && blocked ? 'text-accent' : over || projectedOver ? 'text-accent' : 'text-muted'
                    }`}
                  >
                    {hoveredCol && blocked
                      ? blockedLabel[check.reason!]
                      : projected != null
                        ? `→ ${projected} cr`
                        : over
                          ? `${col.credits}/${col.cap} cr`
                          : `${col.credits} cr`}
                  </span>
                </h3>
                <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
                  {col.cards.map((p) => {
                    const state = cardState(p)
                    return (
                      <li key={p.id}>
                        <GraphCard
                          placement={p}
                          state={state}
                          interactive={interactive}
                          tabStop={p.id === tabStop}
                          selected={p.id === active}
                          dim={(focus != null && !focus.has(p.id)) || (movedSet.size > 0 && !movedSet.has(p.id))}
                          moved={movedSet.has(p.id)}
                          problem={problems.has(p.id)}
                          draggable={!readOnly && !!onMove && p.status === 'planned' && !p.locked}
                          lifted={drag?.id === p.id}
                          helpId={interactive ? helpId : undefined}
                        />
                      </li>
                    )
                  })}
                  {col.ghosts.map((g) => (
                    <li key={`ghost-${g.id}`}>
                      <GraphCard
                        placement={g}
                        state="ghost"
                        interactive={false}
                        tabStop={false}
                        selected={false}
                        dim={false}
                        moved={false}
                        problem={false}
                        draggable={false}
                        lifted={false}
                      />
                    </li>
                  ))}
                </ol>
              </div>
            )
          })}
        </div>
      </div>
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute inset-y-0 left-0 w-6 bg-linear-to-r from-white to-transparent transition-opacity duration-200 ${fade.start ? 'opacity-100' : 'opacity-0'}`}
      />
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute inset-y-0 right-0 w-6 bg-linear-to-l from-white to-transparent transition-opacity duration-200 ${fade.end ? 'opacity-100' : 'opacity-0'}`}
      />
      {drag &&
        dragged &&
        createPortal(
          <div
            ref={clone}
            aria-hidden="true"
            className="pointer-events-none fixed top-0 left-0 z-50 will-change-transform"
            style={{ width: CARD_W }}
          >
            <CardClone placement={dragged} settling={drag.phase !== 'drag'} />
          </div>,
          document.body,
        )}
    </div>
  )
}
