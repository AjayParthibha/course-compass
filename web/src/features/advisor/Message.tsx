import { useSearchParams } from 'react-router'
import type { AdvisorEvent } from '../../api/types'
import { toBlocks } from './blocks'
import { Button } from '../../ui'

type Props = {
  role: 'user' | 'assistant'
  events: AdvisorEvent[]
  live: boolean
  canAnswer: boolean
  onAnswer: (text: string) => void
}

export default function Message({ role, events, live, canAnswer, onAnswer }: Props) {
  const [, setParams] = useSearchParams()

  if (role === 'user') {
    const text = events.map((e) => (e.type === 'text' ? e.delta : '')).join('')
    return (
      <div className="flex flex-col gap-1">
        <span className="text-[12px] font-semibold text-muted">You</span>
        <p className="m-0 rounded-lg bg-chip px-3 py-2 whitespace-pre-wrap">{text}</p>
      </div>
    )
  }

  const blocks = toBlocks(events)
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[12px] font-semibold text-muted">Advisor</span>
      {blocks.length === 0 && live && <span className="text-[13px] text-muted">Thinking…</span>}
      {blocks.map((b, i) => {
        if (b.kind === 'text') return <p key={i} className="m-0 leading-relaxed whitespace-pre-wrap">{b.text}</p>
        if (b.kind === 'tool')
          return (
            <div key={i} className="font-mono text-[11.5px] leading-snug text-muted">
              <span className="font-semibold text-ink-soft">{b.name}</span>
              {' → '}
              <span className={b.ok ? '' : 'text-accent'}>{b.summary ?? '…'}</span>
            </div>
          )
        const e = b.event
        if (e.type === 'question')
          return (
            <div key={i} className="flex flex-col gap-2 rounded-lg bg-ink p-3 text-paper">
              <span className="font-semibold">{e.question}</span>
              {e.options.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  disabled={!canAnswer}
                  onClick={() => onAnswer(opt)}
                  className="min-h-10 rounded-md border border-[#5A6158] bg-transparent px-3 text-left text-paper disabled:opacity-50"
                >
                  {opt}
                </button>
              ))}
              <span className="text-[12px] text-[#C3C9BC]">Your answer is saved to your profile as something you said.</span>
              {canAnswer && (
                <button type="button" onClick={() => onAnswer('Ask me later.')} className="self-start border-0 bg-transparent p-0 text-[12.5px] text-paper underline">
                  Ask me later
                </button>
              )}
            </div>
          )
        if (e.type === 'proposal')
          return (
            <div key={i} className="flex flex-col gap-2 rounded-lg border-[1.5px] border-ink bg-white p-3">
              <span className="text-[11px] font-bold tracking-[0.08em] uppercase">Proposed change</span>
              <span className="text-[13.5px]">{e.proposal.summary}</span>
              {e.proposal.rejected.length > 0 && (
                <details className="text-[13px]">
                  <summary className="cursor-pointer font-semibold">What I didn’t do, and why</summary>
                  <ul className="mt-1 mb-0 flex flex-col gap-1 pl-4">
                    {e.proposal.rejected.map((r) => (
                      <li key={r.title}>
                        <strong>{r.title}</strong> {r.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <Button variant="primary" className="self-start" onClick={() => setParams({ proposal: String(e.proposal.id) })}>
                Preview in the graph
              </Button>
            </div>
          )
        if (e.type === 'profile_update')
          return (
            <span key={i} className="text-[12.5px] text-muted">
              Saved to your profile: “{e.fact.text}”
              {e.fact.status === 'stated' ? ' (something you said)' : ' (a guess, until you confirm)'}
            </span>
          )
        if (e.type === 'error')
          return <span key={i} className="text-[13px] text-accent">{e.message}</span>
        return null
      })}
    </div>
  )
}
