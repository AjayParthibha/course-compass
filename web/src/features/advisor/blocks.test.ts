import { describe, expect, it } from 'vitest'
import { toBlocks } from './blocks'

describe('toBlocks', () => {
  it('merges text deltas and pairs tool events', () => {
    const blocks = toBlocks([
      { type: 'tool_start', id: '1', name: 'get_plan_state', args: {} },
      { type: 'tool_end', id: '1', name: 'get_plan_state', summary: '3 open slots', ok: true },
      { type: 'text', delta: 'Hello ' },
      { type: 'text', delta: 'there' },
    ])
    expect(blocks).toEqual([
      { kind: 'tool', id: '1', name: 'get_plan_state', summary: '3 open slots', ok: true },
      { kind: 'text', text: 'Hello there' },
    ])
  })
})
