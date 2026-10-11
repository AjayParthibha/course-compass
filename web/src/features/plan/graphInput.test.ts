import { describe, expect, it } from 'vitest'
import { LONG_PRESS_MS, autoScrollStep, canDrop, dropColumn, navTarget, pressIntent } from './graphInput'

describe('pressIntent', () => {
  it('starts a mouse drag after a few pixels', () => {
    expect(pressIntent('mouse', 0, 2)).toBe('pending')
    expect(pressIntent('mouse', 0, 4)).toBe('drag')
  })

  it('needs a still long-press on touch so swipes keep scrolling', () => {
    expect(pressIntent('touch', 100, 3)).toBe('pending')
    expect(pressIntent('touch', 100, 12)).toBe('cancel')
    expect(pressIntent('touch', LONG_PRESS_MS, 3)).toBe('drag')
    expect(pressIntent('touch', LONG_PRESS_MS + 50, 40)).toBe('drag')
  })
})

describe('dropColumn', () => {
  const cols = [
    { left: 16, right: 144 },
    { left: 164, right: 292 },
    { left: 312, right: 440 },
  ]

  it('splits the gap between columns down the middle', () => {
    expect(dropColumn(153, cols)).toBe(0)
    expect(dropColumn(155, cols)).toBe(1)
    expect(dropColumn(300, cols)).toBe(1)
    expect(dropColumn(303, cols)).toBe(2)
  })

  it('clamps to the first and last columns', () => {
    expect(dropColumn(-40, cols)).toBe(0)
    expect(dropColumn(900, cols)).toBe(2)
    expect(dropColumn(10, [])).toBe(-1)
  })
})

describe('canDrop', () => {
  const terms = ['FA25', 'SP26', 'FA26', 'SP27']

  it('only accepts a different term after the current one', () => {
    expect(canDrop('FA26', 'SP27', terms, 'SP26')).toEqual({ ok: true, reason: null })
    expect(canDrop('FA26', 'FA26', terms, 'SP26')).toEqual({ ok: false, reason: 'same' })
    expect(canDrop('FA26', 'SP26', terms, 'SP26')).toEqual({ ok: false, reason: 'current' })
    expect(canDrop('FA26', 'FA25', terms, 'SP26')).toEqual({ ok: false, reason: 'past' })
  })
})

describe('autoScrollStep', () => {
  it('scrolls faster the closer the pointer gets to an edge', () => {
    expect(autoScrollStep(200, 0, 400)).toBe(0)
    expect(autoScrollStep(40, 0, 400)).toBeLessThan(0)
    expect(autoScrollStep(5, 0, 400)).toBeLessThan(autoScrollStep(40, 0, 400))
    expect(autoScrollStep(395, 0, 400)).toBeGreaterThan(autoScrollStep(360, 0, 400))
    expect(autoScrollStep(-30, 0, 400)).toBe(-18)
  })
})

describe('navTarget', () => {
  const cols = [
    [{ id: 'a', y: 30 }, { id: 'b', y: 106 }, { id: 'c', y: 182 }],
    [],
    [{ id: 'd', y: 30 }, { id: 'e', y: 106 }],
  ]

  it('moves up and down within a term without wrapping', () => {
    expect(navTarget(cols, 'b', 'ArrowUp')).toBe('a')
    expect(navTarget(cols, 'b', 'ArrowDown')).toBe('c')
    expect(navTarget(cols, 'c', 'ArrowDown')).toBeNull()
    expect(navTarget(cols, 'a', 'ArrowUp')).toBeNull()
  })

  it('jumps across empty terms to the card at the nearest height', () => {
    expect(navTarget(cols, 'c', 'ArrowRight')).toBe('e')
    expect(navTarget(cols, 'a', 'ArrowRight')).toBe('d')
    expect(navTarget(cols, 'e', 'ArrowLeft')).toBe('b')
    expect(navTarget(cols, 'a', 'ArrowLeft')).toBeNull()
  })

  it('goes to the ends of a term with Home and End', () => {
    expect(navTarget(cols, 'b', 'Home')).toBe('a')
    expect(navTarget(cols, 'b', 'End')).toBe('c')
    expect(navTarget(cols, 'x', 'ArrowUp')).toBeNull()
  })
})
