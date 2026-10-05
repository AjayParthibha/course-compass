import type { AdvisorEvent } from '../../api/types'

export type Block =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; summary: string | null; ok: boolean }
  | { kind: 'event'; event: AdvisorEvent }

/** Merge streamed text deltas and pair tool start/end events into display blocks. */
export function toBlocks(events: AdvisorEvent[]): Block[] {
  const blocks: Block[] = []
  for (const e of events) {
    const last = blocks[blocks.length - 1]
    if (e.type === 'text') {
      if (last?.kind === 'text') last.text += e.delta
      else blocks.push({ kind: 'text', text: e.delta })
    } else if (e.type === 'tool_start') {
      blocks.push({ kind: 'tool', id: e.id, name: e.name, summary: null, ok: true })
    } else if (e.type === 'tool_end') {
      const tool = blocks.find((b) => b.kind === 'tool' && b.id === e.id)
      if (tool && tool.kind === 'tool') Object.assign(tool, { summary: e.summary, ok: e.ok })
      else blocks.push({ kind: 'tool', id: e.id, name: e.name, summary: e.summary, ok: e.ok })
    } else {
      blocks.push({ kind: 'event', event: e })
    }
  }
  return blocks
}
