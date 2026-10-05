import { describe, expect, it } from 'vitest'
import { parseSSE } from './sse'

describe('parseSSE', () => {
  it('splits complete events and keeps the partial tail', () => {
    const { events, rest } = parseSSE('data: {"a":1}\n\ndata: {"b":2}\n\ndata: {"c"')
    expect(events).toEqual(['{"a":1}', '{"b":2}'])
    expect(rest).toBe('data: {"c"')
  })

  it('ignores comment lines', () => {
    expect(parseSSE(': ping\n\ndata: x\n\n').events).toEqual(['x'])
  })
})
