import { describe, expect, it } from 'vitest'
import { anchorYs, chainSteps, edgePath, flipDeltas, gutters, pickGutter, type Box } from './graphGeometry'

const box = (col: number, row: number): Box => ({ x: 16 + col * 148, y: 40 + row * 76, w: 128, h: 66 })
const cy = (b: Box) => b.y + b.h / 2
const numbers = (d: string) => d.match(/-?\d+(\.\d+)?/g)!.map(Number)

describe('gutters', () => {
  it('finds the channels above, between and below rows', () => {
    expect(gutters([box(0, 0), box(0, 1), box(1, 0), box(2, 2)])).toEqual([35, 111, 187, 263])
    expect(gutters([])).toEqual([])
  })
})

describe('pickGutter', () => {
  it('prefers a channel between the two ends, nearest their midpoint', () => {
    expect(pickGutter(73, 225, [35, 111, 187, 263])).toBe(187)
    expect(pickGutter(225, 73, [35, 111, 187, 263])).toBe(187)
  })

  it('runs just below the row when both ends are level', () => {
    expect(pickGutter(73, 73, [35, 111, 187])).toBe(111)
  })
})

describe('edgePath', () => {
  const lines = gutters([box(0, 0), box(0, 1), box(0, 2)])

  it('joins neighbouring terms with one curve from right edge to left edge', () => {
    const s = box(0, 0)
    const t = box(1, 2)
    const g = edgePath(s, t, cy(s), cy(t), lines)
    expect(g.kind).toBe('forward')
    expect(g.d.startsWith(`M${s.x + s.w} ${cy(s)}C`)).toBe(true)
    expect(g.d.endsWith(`${t.x - 1} ${cy(t)}`)).toBe(true)
    expect(g.d).not.toContain('L')
    expect(g.tip).toEqual({ x: t.x - 1, y: cy(t), dir: 1 })
  })

  it('routes long jumps along a channel between rows instead of through cards', () => {
    const s = box(0, 0)
    const t = box(3, 0)
    const g = edgePath(s, t, cy(s), cy(t), lines)
    const [, , , , , , gx, gy, lx, ly] = numbers(g.d)
    expect(gy).toBe(111)
    expect(ly).toBe(111)
    expect(gx).toBe(s.x + s.w + 20)
    expect(lx).toBe(t.x - 1 - 20)
  })

  it('loops corequisites in the same term out to the right', () => {
    const s = box(1, 0)
    const t = box(1, 1)
    const g = edgePath(s, t, cy(s), cy(t), lines)
    expect(g.kind).toBe('same')
    expect(Math.max(...numbers(g.d).filter((_, i) => i % 2 === 0))).toBeGreaterThan(s.x + s.w)
    expect(g.tip.dir).toBe(-1)
  })

  it('flags edges that point back in time', () => {
    expect(edgePath(box(2, 0), box(0, 0), 73, 73, lines).kind).toBe('backward')
  })
})

describe('anchorYs', () => {
  it('fans out several edges on the same side of a card, ordered by the other end', () => {
    const boxes = new Map([
      ['a', box(0, 1)],
      ['b', box(1, 0)],
      ['c', box(1, 2)],
    ])
    const ends = anchorYs([{ source: 'a', target: 'c' }, { source: 'a', target: 'b' }], boxes)
    const toB = ends.get('a>b')!
    const toC = ends.get('a>c')!
    expect(toB.sy).toBeLessThan(toC.sy)
    expect((toB.sy + toC.sy) / 2).toBe(cy(box(0, 1)))
    expect(toB.ty).toBe(cy(box(1, 0)))
  })

  it('skips edges whose cards are not on screen', () => {
    expect(anchorYs([{ source: 'a', target: 'z' }], new Map([['a', box(0, 0)]])).size).toBe(0)
  })
})

describe('chainSteps', () => {
  it('draws prerequisites towards the course, then what it unlocks outward', () => {
    const edges = [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
      { source: 'c', target: 'd' },
      { source: 'd', target: 'e' },
      { source: 'x', target: 'y' },
    ]
    const steps = chainSteps('c', edges)
    expect(Object.fromEntries(steps)).toEqual({ 'a>b': 0, 'b>c': 1, 'c>d': 2, 'd>e': 3 })
  })

  it('starts unlocks at zero when nothing is upstream', () => {
    expect(Object.fromEntries(chainSteps('a', [{ source: 'a', target: 'b' }]))).toEqual({ 'a>b': 0 })
  })
})

describe('flipDeltas', () => {
  it('reports how far moved cards travelled', () => {
    const prev = new Map([['a', box(0, 0)], ['b', box(1, 0)]])
    const next = new Map([['a', box(0, 0)], ['b', box(2, 1)], ['c', box(0, 1)]])
    expect(flipDeltas(prev, next)).toEqual([{ id: 'b', dx: -148, dy: -76 }])
  })
})
