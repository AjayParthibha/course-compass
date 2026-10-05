import { auth } from './client'
import type { AdvisorEvent } from './types'

/** Split a buffer of SSE text into complete `data:` payloads plus the leftover tail. */
export function parseSSE(buffer: string): { events: string[]; rest: string } {
  const chunks = buffer.split('\n\n')
  const rest = chunks.pop() ?? ''
  const events = chunks
    .map((chunk) =>
      chunk
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n'),
    )
    .filter(Boolean)
  return { events, rest }
}

export async function* streamChat(
  message: string,
  conversationId: number | null,
  signal?: AbortSignal,
): AsyncGenerator<AdvisorEvent> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.get() ?? ''}` },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  })
  if (!res.ok || !res.body) {
    yield { type: 'error', message: `Request failed (${res.status})` }
    return
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const { events, rest } = parseSSE(buffer)
    buffer = rest
    for (const data of events) yield JSON.parse(data) as AdvisorEvent
  }
}
