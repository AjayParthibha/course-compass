import { memo } from 'react'
import type { Placement } from '../../api/types'
import { termLabel } from '../../ui/terms'
import { cardState, nodeLabel, type CardState } from './cards'

const tone: Record<CardState, string> = {
  completed: 'bg-done border border-[#BFC6B8]',
  in_progress: 'bg-white border-[1.5px] border-ink',
  planned: 'bg-white border border-line-strong',
  open: 'bg-paper/70 border-[1.5px] border-dashed border-[#8C9488]',
  ghost: 'bg-transparent border-[1.5px] border-dashed border-accent',
}

const dimTone: Record<CardState, string> = {
  completed: 'bg-paper border border-line-soft',
  in_progress: 'bg-white border-[1.5px] border-line',
  planned: 'bg-white border border-line-soft',
  open: 'bg-paper/70 border-[1.5px] border-dashed border-line',
  ghost: tone.ghost,
}

const hoverTone: Record<CardState, string> = {
  completed: 'hover:border-[#9DA697]',
  in_progress: '',
  planned: 'hover:border-[#5F675B]',
  open: 'hover:border-[#5F675B]',
  ghost: '',
}

const MOVED = 'bg-highlight border-[1.5px] border-ink shadow-[0_2px_0_#171B17]'
const SHAPE = 'relative box-border flex h-[66px] w-[128px] flex-col gap-0.5 rounded-lg px-2 py-1.5 text-left'

function Lock() {
  return (
    <svg width="9" height="10" viewBox="0 0 9 10" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
      <rect x="1" y="4.5" width="7" height="5" rx="1" />
      <path d="M2.75 4.5V3a1.75 1.75 0 0 1 3.5 0v1.5" />
    </svg>
  )
}

/** The visible inside of a card: code and credits on one line, the title below it. */
export function CardFace({ placement: p, state, dim = false }: { placement: Placement; state: CardState; dim?: boolean }) {
  const code = p.course ?? 'Open slot'
  const title = p.course ? p.title : p.slot_label
  const codeTone = dim ? 'text-faint' : state === 'ghost' ? 'text-accent line-through' : state === 'open' ? 'text-[#5B6358]' : ''
  return (
    <>
      <span className="flex flex-nowrap items-baseline justify-between gap-1 leading-[17px]">
        <span className={`shrink-0 font-mono text-[11.5px] font-semibold whitespace-nowrap transition-colors duration-200 motion-reduce:transition-none ${codeTone}`}>
          {code}
        </span>
        <span className={`flex shrink-0 items-center gap-0.5 font-mono text-[10px] ${dim ? 'text-faint' : 'text-muted'}`}>
          {p.locked && state !== 'ghost' && <Lock />}
          {state === 'ghost' ? 'was' : `${p.credits} cr`}
        </span>
      </span>
      <span className={`line-clamp-2 text-[11px] leading-[14px] transition-colors duration-200 motion-reduce:transition-none ${dim ? 'text-faint' : 'text-ink-soft'}`}>
        {title}
      </span>
    </>
  )
}

/** A detached copy of a card, drawn under the pointer while it is dragged. */
export function CardClone({ placement, settling }: { placement: Placement; settling: boolean }) {
  const state = cardState(placement)
  return (
    <div
      className={`${SHAPE} ${tone[state]} ${settling ? 'animate-card-settle' : 'animate-card-lift'} motion-reduce:animate-none`}
    >
      <CardFace placement={placement} state={state} />
    </div>
  )
}

type Props = {
  placement: Placement
  state: CardState
  interactive: boolean
  tabStop: boolean
  selected: boolean
  dim: boolean
  moved: boolean
  problem: boolean
  draggable: boolean
  lifted: boolean
  helpId?: string
}

export const GraphCard = memo(function GraphCard({
  placement: p,
  state,
  interactive,
  tabStop,
  selected,
  dim,
  moved,
  problem,
  draggable,
  lifted,
  helpId,
}: Props) {
  const id = state === 'ghost' ? `ghost-${p.id}` : p.id
  const label = nodeLabel(p, state, problem, moved)
  const look = lifted
    ? 'border-[1.5px] border-dashed border-line-strong bg-paper [&>*]:invisible'
    : moved
      ? MOVED
      : dim
        ? dimTone[state]
        : `${tone[state]} ${interactive ? hoverTone[state] : ''}`
  const cls = [
    SHAPE,
    look,
    'transition-[background-color,border-color,box-shadow,scale] duration-200 ease-out motion-reduce:transition-none',
    problem && !lifted ? 'ring-2 ring-accent' : '',
    "after:pointer-events-none after:absolute after:-inset-[4px] after:rounded-[11px] after:border-2 after:border-accent after:transition-[opacity,scale] after:duration-150 after:content-[''] motion-reduce:after:transition-none",
    selected && !lifted ? 'after:scale-100 after:opacity-100' : 'after:scale-[.97] after:opacity-0',
  ].join(' ')

  if (!interactive) {
    return (
      <>
        <span className="sr-only">{label}</span>
        <div data-card={id} aria-hidden="true" className={cls}>
          <CardFace placement={p} state={state} dim={dim && !moved} />
        </div>
      </>
    )
  }

  const title = p.course ? p.title : p.slot_label
  return (
    <button
      type="button"
      data-card={id}
      data-drag={draggable || undefined}
      tabIndex={tabStop ? 0 : -1}
      aria-label={label}
      aria-pressed={selected}
      aria-describedby={helpId}
      title={`${p.course ?? 'Open slot'}${title ? ` · ${title}` : ''}${p.locked ? ` · kept in ${termLabel(p.term)}` : ''}`}
      className={`${cls} touch-manipulation select-none [-webkit-touch-callout:none] focus-visible:outline-offset-[6px]! active:scale-[.98] data-pressing:scale-[.95] data-pressing:duration-[250ms] ${
        draggable ? 'pointer-fine:cursor-grab' : ''
      } hover:shadow-[0_1px_2px_rgb(23_27_23/.06),0_6px_14px_-8px_rgb(23_27_23/.4)]`}
    >
      <CardFace placement={p} state={state} dim={dim && !moved} />
    </button>
  )
})
