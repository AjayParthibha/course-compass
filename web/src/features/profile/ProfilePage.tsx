import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { api, unwrap } from '../../api/client'
import { keys, useProfile } from '../../api/hooks'
import type { ProfileFact } from '../../api/types'
import { Button, SectionLabel, Tag } from '../../ui'
import { termLabel } from '../../ui/terms'
import { useAdvisor } from '../advisor/store'
import PlanSettings from './PlanSettings'

const PROGRAMS: Record<string, [string, string]> = {
  'cs-eng': ['Engineering', 'Computer Science B.S.'],
  'cs-as': ['Arts & Sciences', 'Computer Science B.A.'],
}

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

function useProfileActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: keys.profile })
  return {
    update: async (id: number, body: Partial<Pick<ProfileFact, 'status' | 'text' | 'value'>>) => {
      await unwrap(api.PATCH('/api/profile/facts/{fact_id}', { params: { path: { fact_id: id } }, body }))
      refresh()
    },
    remove: async (id: number) => {
      await api.DELETE('/api/profile/facts/{fact_id}', { params: { path: { fact_id: id } } })
      refresh()
    },
    add: async (text: string) => {
      await unwrap(api.POST('/api/profile/facts', { body: { dimension: 'note', value: text, text } }))
      refresh()
    },
    setMemory: async (on: boolean) => {
      const student = await unwrap(api.PATCH('/api/profile/student', { body: { memory_enabled: on } }))
      qc.setQueryData(keys.me, student)
      refresh()
    },
    clear: async () => {
      await api.DELETE('/api/profile')
      refresh()
    },
  }
}

function ConflictCard({ a, b }: { a: ProfileFact; b: ProfileFact }) {
  const { update } = useProfileActions()
  const resolve = async (winner: ProfileFact | null) => {
    if (!winner) {
      await Promise.all([update(a.id, { status: 'open' }), update(b.id, { status: 'open' })])
      return
    }
    const loser = winner.id === a.id ? b : a
    await Promise.all([update(winner.id, { status: 'stated' }), update(loser.id, { status: 'superseded' })])
  }
  return (
    <section aria-label="Conflicting information" className="overflow-hidden rounded-xl border-[1.5px] border-ink bg-white">
      <div className="border-b-[1.5px] border-ink bg-highlight px-4 py-3 text-[12px] font-extrabold tracking-[0.08em] uppercase">
        These don’t agree anymore
      </div>
      <div className="flex flex-col gap-4 p-4">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(280px,100%),1fr))] gap-3">
          {[a, b].map((f) => (
            <div key={f.id} className="flex flex-col gap-1.5 rounded-lg bg-ground p-3.5">
              <span className="text-[12px] font-semibold text-muted">{shortDate(f.created_at)}</span>
              <span className="text-base leading-snug">{f.evidence ?? f.text}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="font-bold">Which is true now?</span>
          <Button variant="primary" onClick={() => resolve(b)}>{b.text}</Button>
          <Button onClick={() => resolve(a)}>{a.text}</Button>
          <Button onClick={() => resolve(null)}>Undecided, keep both in mind</Button>
        </div>
        <span className="text-[13px] text-muted">
          Until you pick, the advisor won’t recommend anything that only makes sense one way.
        </span>
      </div>
    </section>
  )
}

function FactRow({ fact }: { fact: ProfileFact }) {
  const { update, remove } = useProfileActions()
  const navigate = useNavigate()
  const ask = useAdvisor((s) => s.ask)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(fact.text)
  const tag =
    fact.status === 'stated' ? <Tag kind="said">You said</Tag> : fact.status === 'inferred' ? <Tag kind="guess">My guess</Tag> : <Tag kind="open">Open question</Tag>

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-t border-line-soft px-4 py-3.5">
      <div className="flex min-w-[260px] flex-1 flex-col gap-1.5">
        {editing ? (
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault()
              await update(fact.id, { text, status: 'stated' })
              setEditing(false)
            }}
          >
            <input value={text} onChange={(e) => setText(e.target.value)} aria-label="Edit" className="h-9 flex-1 rounded-md border border-[#C3C9BC] px-2" autoFocus />
            <Button type="submit" variant="primary">Save</Button>
          </form>
        ) : (
          <span className={`text-[15.5px] leading-snug font-semibold ${fact.status === 'open' ? 'text-muted' : ''}`}>{fact.text}</span>
        )}
        <span className="flex flex-wrap items-center gap-2">
          {tag}
          <span className="text-[12.5px] text-muted">
            {fact.status === 'stated' ? shortDate(fact.last_confirmed_at ?? fact.updated_at) : fact.evidence ?? shortDate(fact.created_at)}
          </span>
        </span>
      </div>
      <div className="flex gap-1.5">
        {fact.status === 'inferred' && (
          <>
            <Button className="border-ink! font-semibold" onClick={() => update(fact.id, { status: 'stated' })}>That’s right</Button>
            <Button onClick={() => update(fact.id, { status: 'rejected' })}>Not really</Button>
          </>
        )}
        {fact.status === 'open' && (
          <Button
            className="border-ink! font-semibold"
            onClick={() => {
              ask(`Let's talk about this: ${fact.text.toLowerCase()}.`)
              navigate('/plan')
            }}
          >
            Talk it through
          </Button>
        )}
        {fact.status === 'stated' && !editing && (
          <>
            <Button variant="quiet" aria-label="Edit" onClick={() => setEditing(true)}>Edit</Button>
            <Button variant="quiet" aria-label="Remove" onClick={() => remove(fact.id)}>Remove</Button>
          </>
        )}
      </div>
    </div>
  )
}

export default function ProfilePage() {
  const { data, isLoading } = useProfile()
  const actions = useProfileActions()
  const [adding, setAdding] = useState('')
  const { hash } = useLocation()
  const loaded = !!data

  useEffect(() => {
    if (!loaded || hash !== '#plan-settings') return
    const el = document.getElementById('plan-settings')
    el?.scrollIntoView({ block: 'start' })
    el?.focus({ preventScroll: true })
  }, [loaded, hash])

  if (isLoading || !data) return <div className="p-10 text-muted">Loading…</div>
  const { student, facts } = data
  const [college, degree] = PROGRAMS[student.program ?? ''] ?? ['', student.program]

  const conflicts = facts.filter((f) => f.status === 'conflict')
  const pairs: [ProfileFact, ProfileFact][] = []
  for (const dim of new Set(conflicts.map((f) => f.dimension))) {
    const group = conflicts.filter((f) => f.dimension === dim)
    if (group.length >= 2) pairs.push([group[0], group[group.length - 1]])
  }
  const shown = facts.filter((f) => ['stated', 'inferred', 'open'].includes(f.status))

  const download = async () => {
    const profile = await unwrap(api.GET('/api/profile/export'))
    const url = URL.createObjectURL(new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: 'coursecompass-profile.json' })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 px-6 pt-8 pb-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-2xl flex-col gap-2">
          <h1 className="m-0 text-[34px] leading-tight font-extrabold tracking-tight">What the advisor knows about you</h1>
          <p className="m-0 text-base text-muted">
            All of this shapes your recommendations. Change or remove anything, and the advisor stops using the old version right away.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={student.memory_enabled}
          aria-labelledby="memory-switch-label"
          aria-describedby="memory-switch-hint"
          onClick={() => actions.setMemory(!student.memory_enabled)}
          className="flex min-h-11 items-center gap-3 border-0 bg-transparent"
        >
          <span id="memory-switch-label" className="font-semibold">Remember between sessions</span>
          <span id="memory-switch-hint" className="sr-only">
            When off, the advisor only uses what you tell it in the current conversation.
          </span>
          <span aria-hidden="true" className={`relative inline-block h-[26px] w-11 rounded-full transition-colors ${student.memory_enabled ? 'bg-ink' : 'bg-[#B9C0B2]'}`}>
            <span className={`absolute top-[3px] h-5 w-5 rounded-full bg-white transition-all ${student.memory_enabled ? 'left-[21px]' : 'left-[3px]'}`} />
          </span>
        </button>
      </div>

      {pairs.map(([a, b]) => (
        <ConflictCard key={a.dimension} a={a} b={b} />
      ))}

      <div className="flex flex-wrap items-start gap-6">
        <section aria-label="The basics" className="min-w-0 flex-[1_1_280px] rounded-xl border border-line bg-white">
          <SectionLabel className="px-4 pt-4 pb-2.5">The basics</SectionLabel>
          <dl className="m-0">
            {[
              ['College', college],
              ['Degree', degree],
              ['Rules used', `${student.catalog_year} catalog`],
              ['Started', student.entering_term ? termLabel(student.entering_term, true) : '—'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-t border-line-soft px-4 py-2.5">
                <dt className="text-muted">{k}</dt>
                <dd className="m-0 text-right font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          <Link to="/onboarding" className="mx-4 mt-1.5 mb-4 block border-t border-line-soft pt-3 font-semibold">
            Review your course history
          </Link>
        </section>

        <section aria-label="Goals and preferences" className="min-w-0 flex-[999_1_560px] rounded-xl border border-line bg-white">
          <div className="flex items-baseline justify-between gap-3 px-4 pt-4 pb-2.5">
            <SectionLabel>Goals and preferences</SectionLabel>
          </div>
          {shown.length === 0 && (
            <p className="m-0 border-t border-line-soft px-4 py-4 text-muted">
              Nothing yet. Tell the advisor what you’re aiming for, or add something here.
            </p>
          )}
          {shown.map((f) => (
            <FactRow key={f.id} fact={f} />
          ))}
          <form
            className="flex gap-2 border-t border-line-soft px-4 py-3"
            onSubmit={async (e) => {
              e.preventDefault()
              if (!adding.trim()) return
              await actions.add(adding.trim())
              setAdding('')
            }}
          >
            <input
              value={adding}
              onChange={(e) => setAdding(e.target.value)}
              placeholder="Add something the advisor should know"
              aria-label="Add something"
              className="h-9 flex-1 rounded-md border border-[#C3C9BC] px-2"
            />
            <Button type="submit" disabled={!adding.trim()}>Add</Button>
          </form>
          <div className="flex flex-wrap gap-4 border-t border-line-soft px-4 py-3.5 text-[12.5px] text-muted">
            <span className="flex items-center gap-1.5"><Tag kind="said">You said</Tag>used with full weight</span>
            <span className="flex items-center gap-1.5"><Tag kind="guess">My guess</Tag>used lightly until you confirm</span>
          </div>
        </section>
      </div>

      <PlanSettings student={student} />

      <div className="flex flex-wrap justify-between gap-3 border-t border-line pt-4 text-muted">
        <span>Your profile never includes transcripts or grades you didn’t enter yourself.</span>
        <div className="flex gap-4">
          <Button variant="link" onClick={download}>Download my profile</Button>
          <Button
            variant="link"
            className="text-accent!"
            onClick={() => window.confirm('Clear everything the advisor knows about you?') && actions.clear()}
          >
            Clear everything
          </Button>
        </div>
      </div>
    </div>
  )
}
