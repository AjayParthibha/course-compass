import { useQueryClient } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, unwrap } from '../../api/client'
import { keys, useUpdatePlanSettings } from '../../api/hooks'
import { Button } from '../../ui'
import { AFTER, emptyGoals, factsToSupersede, goalFacts, type Goals, INTERESTS, LOADS } from './goals'

const chip =
  'inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-full border border-[#C3C9BC] bg-white px-3.5 ' +
  'has-[:checked]:border-ink has-[:checked]:bg-ink has-[:checked]:text-paper ' +
  'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink'

const textInput = 'h-10 rounded-md border border-[#C3C9BC] bg-white px-2'

export default function GoalsStep() {
  const id = useId()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const settings = useUpdatePlanSettings()
  const [goals, setGoals] = useState<Goals>(emptyGoals)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<Goals>) => setGoals((g) => ({ ...g, ...patch }))

  const facts = goalFacts(goals)
  const load = LOADS.find((l) => l.id === goals.load)

  const finish = async () => {
    setBusy(true)
    setError(null)
    try {
      if (facts.length) {
        const { facts: existing } = await unwrap(api.GET('/api/profile'))
        const have = new Set(
          existing.filter((f) => f.status === 'stated').map((f) => `${f.dimension}:${f.value}`),
        )
        // a new answer to a single-choice question replaces the old one instead of stacking
        for (const factId of factsToSupersede(existing, facts))
          await unwrap(
            api.PATCH('/api/profile/facts/{fact_id}', {
              params: { path: { fact_id: factId } },
              body: { status: 'superseded' },
            }),
          )
        for (const body of facts)
          if (!have.has(`${body.dimension}:${body.value}`)) await unwrap(api.POST('/api/profile/facts', { body }))
        qc.invalidateQueries({ queryKey: keys.profile })
      }
      if (load) await settings.mutateAsync({ max_credits: load.credits })
      navigate('/plan')
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-6 rounded-xl border border-line bg-white p-5">
      <div className="flex flex-col gap-1.5">
        <h1 id={`${id}-title`} className="m-0 text-2xl font-extrabold tracking-tight">What are you aiming for?</h1>
        <p className="m-0 max-w-2xl text-muted">
          Your history is saved. These three questions help the advisor rank courses for you. Every one is
          optional, and you can refine your answers any time by talking to the advisor.
        </p>
      </div>

      <fieldset className="m-0 flex flex-col gap-2.5 border-0 p-0">
        <legend className="mb-2.5 p-0 font-semibold">After graduating, you’re thinking of…</legend>
        <div className="flex flex-wrap gap-2">
          {AFTER.map((o) => (
            <label key={o.id} className={chip}>
              <input
                type="radio"
                name={`${id}-after`}
                value={o.id}
                aria-label={o.label}
                checked={goals.after === o.id}
                onChange={() => set({ after: o.id })}
                className="sr-only"
              />
              {o.label}
            </label>
          ))}
        </div>
        {goals.after === 'other' && (
          <div className="flex flex-col gap-1">
            <label htmlFor={`${id}-after-other`} className="text-[13.5px] font-semibold">What do you have in mind?</label>
            <input
              id={`${id}-after-other`}
              aria-label="What do you have in mind?"
              value={goals.afterOther}
              onChange={(e) => set({ afterOther: e.target.value })}
              placeholder="e.g. start a company, teach, a gap year"
              className={`${textInput} max-w-md`}
            />
          </div>
        )}
      </fieldset>

      <fieldset className="m-0 flex flex-col gap-2.5 border-0 p-0" aria-describedby={`${id}-interests-hint`}>
        <legend className="mb-1 p-0 font-semibold">Which areas interest you?</legend>
        <span id={`${id}-interests-hint`} className="text-[13px] text-muted">Pick as many as you like.</span>
        <div className="flex flex-wrap gap-2">
          {INTERESTS.map((o) => (
            <label key={o.id} className={chip}>
              <input
                type="checkbox"
                value={o.id}
                aria-label={o.label}
                checked={goals.interests.includes(o.id)}
                onChange={(e) =>
                  set({
                    interests: e.target.checked
                      ? [...goals.interests, o.id]
                      : goals.interests.filter((i) => i !== o.id),
                  })
                }
                className="sr-only"
              />
              {o.label}
            </label>
          ))}
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`${id}-interest-other`} className="text-[13.5px] font-semibold">Anything else?</label>
          <input
            id={`${id}-interest-other`}
            aria-label="Anything else?"
            value={goals.interestOther}
            onChange={(e) => set({ interestOther: e.target.value })}
            placeholder="e.g. robotics, computational biology"
            className={`${textInput} max-w-md`}
          />
        </div>
      </fieldset>

      <fieldset className="m-0 flex flex-col gap-2.5 border-0 p-0" aria-describedby={`${id}-load-hint`}>
        <legend className="mb-1 p-0 font-semibold">How heavy a semester do you want?</legend>
        <span id={`${id}-load-hint`} className="text-[13px] text-muted">
          Sets your default credit limit. You can change it, or cap single terms, on your profile.
        </span>
        <div className="flex flex-wrap gap-2">
          {LOADS.map((o) => (
            <label key={o.id} className={chip}>
              <input
                type="radio"
                name={`${id}-load`}
                value={o.id}
                aria-label={`${o.label}, up to ${o.credits} credits`}
                checked={goals.load === o.id}
                onChange={() => set({ load: o.id })}
                className="sr-only"
              />
              <span className="font-semibold">{o.label}</span>
              <span className="text-[12.5px] opacity-80">up to {o.credits} credits</span>
            </label>
          ))}
        </div>
      </fieldset>

      {error && <p role="alert" className="m-0 font-semibold text-accent">{error}</p>}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-4">
        <Button className="h-11" disabled={busy} onClick={() => navigate('/plan')}>Skip for now</Button>
        <Button variant="primary" className="h-11" disabled={busy || (!facts.length && !load)} onClick={finish}>
          {busy ? 'Saving…' : 'Save and see my plan'}
        </Button>
      </div>
    </section>
  )
}
