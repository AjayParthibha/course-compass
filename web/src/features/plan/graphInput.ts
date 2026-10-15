export const LONG_PRESS_MS = 250
export const TOUCH_SLOP = 8
export const MOUSE_SLOP = 4

/**
 * Whether a press on a card should become a drag. Mouse and pen drag as soon as they move a few pixels;
 * touch waits for a still long-press so ordinary swipes keep scrolling the graph.
 */
export function pressIntent(pointerType: string, elapsed: number, distance: number): 'pending' | 'drag' | 'cancel' {
  if (pointerType === 'touch') {
    if (distance > TOUCH_SLOP) return elapsed >= LONG_PRESS_MS ? 'drag' : 'cancel'
    return elapsed >= LONG_PRESS_MS ? 'drag' : 'pending'
  }
  return distance >= MOUSE_SLOP ? 'drag' : 'pending'
}

/** Column under content-space `x`; the gap between two columns is split down the middle. */
export function dropColumn(x: number, cols: { left: number; right: number }[]) {
  if (!cols.length) return -1
  for (let i = 0; i < cols.length - 1; i++) {
    if (x < (cols[i].right + cols[i + 1].left) / 2) return i
  }
  return cols.length - 1
}

export type DropCheck = { ok: boolean; reason: 'same' | 'current' | 'past' | null }

/** Planned courses can only move to a different term after the current one. */
export function canDrop(from: string, to: string, terms: string[], current: string): DropCheck {
  if (from === to) return { ok: false, reason: 'same' }
  const i = terms.indexOf(to)
  const now = terms.indexOf(current)
  if (i === now) return { ok: false, reason: 'current' }
  if (i < now) return { ok: false, reason: 'past' }
  return { ok: true, reason: null }
}

/** Pixels to scroll this frame when the pointer is near (or past) either end of `[start, end]`. */
export function autoScrollStep(pos: number, start: number, end: number, zone = 56, max = 18) {
  const ease = (d: number) => Math.round(max * Math.min(1, Math.max(0, (zone - d) / zone)) ** 2)
  if (pos < start + zone) return -ease(pos - start)
  if (pos > end - zone) return ease(end - pos)
  return 0
}

export type NavCard = { id: string; y: number }

/**
 * Card to focus for an arrow key: up/down within a term, left/right to the nearest card by height
 * in the closest term that has any, Home/End to the ends of the term.
 */
export function navTarget(cols: NavCard[][], id: string, key: string): string | null {
  const c = cols.findIndex((col) => col.some((card) => card.id === id))
  if (c < 0) return null
  const col = cols[c]
  const i = col.findIndex((card) => card.id === id)
  if (key === 'ArrowUp') return col[i - 1]?.id ?? null
  if (key === 'ArrowDown') return col[i + 1]?.id ?? null
  if (key === 'Home') return col[0].id === id ? null : col[0].id
  if (key === 'End') return col[col.length - 1].id === id ? null : col[col.length - 1].id
  const step = key === 'ArrowLeft' ? -1 : key === 'ArrowRight' ? 1 : 0
  if (!step) return null
  const y = col[i].y
  for (let k = c + step; k >= 0 && k < cols.length; k += step) {
    if (!cols[k].length) continue
    return cols[k].reduce((best, card) => (Math.abs(card.y - y) < Math.abs(best.y - y) ? card : best)).id
  }
  return null
}
