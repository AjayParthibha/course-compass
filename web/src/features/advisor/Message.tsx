import type { AdvisorEvent } from '../../api/types'
import { toBlocks } from './blocks'
import MarkdownText from './MarkdownText'
import ProposalCard from './ProposalCard'

type Props = {
  role: 'user' | 'assistant'
  events: AdvisorEvent[]
  live: boolean
  canAnswer: boolean
  onAnswer: (text: string) => void
  latestProposalId: number | null
}

export default function Message({ role, events, live, canAnswer, onAnswer, latestProposalId }: Props) {
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
        if (b.kind === 'text') return <MarkdownText key={i} text={b.text} streaming={live && i === blocks.length - 1} />
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
            <div key={i} className="flex flex-col gap-2 rounded-xl border border-line bg-white p-3.5">
              <span className="text-[14px] leading-snug font-semibold">{e.question}</span>
              <div className="flex flex-col gap-1.5">
                {e.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    disabled={!canAnswer}
                    onClick={() => onAnswer(opt)}
                    className="min-h-9 rounded-md border border-line-soft bg-ground px-3 py-1.5 text-left text-[13.5px] leading-snug transition-colors enabled:hover:border-line-strong enabled:hover:bg-chip disabled:text-muted"
                  >
                    {opt}
                  </button>
                ))}
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[12px] text-muted">Your answer is saved to your profile as something you said.</span>
                {canAnswer && (
                  <button type="button" onClick={() => onAnswer('Ask me later.')} className="shrink-0 border-0 bg-transparent p-0 text-[12.5px] font-semibold text-ink underline underline-offset-2">
                    Ask me later
                  </button>
                )}
              </div>
            </div>
          )
        if (e.type === 'proposal') return <ProposalCard key={i} initial={e.proposal} latestId={latestProposalId} />
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
