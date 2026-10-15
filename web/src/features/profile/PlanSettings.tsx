import { type FormEvent, useId, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { usePlan, useUpdatePlanSettings } from '../../api/hooks'
import type { Student } from '../../api/types'
import { Button, SectionLabel } from '../../ui'
import { termLabel } from '../../ui/terms'
import { capsIn, capsToSave, CREDIT_MAX, CREDIT_MIN, creditError, termsAfter } from './settings'

const inputClass =
  'h-10 rounded-md border bg-white px-2 aria-invalid:border-accent'

const sameCaps = (a: Record<string, number>, b: Record<string, number>) =>
  JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort())

export default function PlanSettings({ student }: { student: Student }) {
  const id = useId()
  const form = useRef<HTMLFormElement>(null)
  const { data: state } = usePlan()
  const save = useUpdatePlanSettings()
  const [grad, setGrad] = useState(student.graduation_term ?? '')
  const [limit, setLimit] = useState(String(student.max_credits))
  const [caps, setCaps] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(student.term_caps).map(([t, c]) => [t, String(c)])),
  )
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState(false)

  // the remaining terms come from the plan; until it loads, saving would drop every cap
  const loaded = !!state
  const current = state?.plan.current_term
  const options = current ? termsAfter(current) : []
  if (grad && !options.includes(grad)) options.unshift(grad)
  const remaining = current && grad ? termsAfter(current, grad, 20) : []
  const planned: Record<string, number> = {}
  for (const p of state?.plan.placements ?? []) planned[p.term] = (planned[p.term] ?? 0) + p.credits

  const limitError = creditError(limit, true)
  const capErrors = Object.fromEntries(remaining.map((t) => [t, creditError(caps[t] ?? '')]))
  const invalid = !!limitError || Object.values(capErrors).some(Boolean)
  const body = { graduation_term: grad, max_credits: Number(limit), term_caps: capsToSave(caps, remaining) }
  const dirty =
    loaded &&
    (grad !== student.graduation_term ||
      body.max_credits !== student.max_credits ||
      !sameCaps(body.term_caps, capsIn(student.term_caps, remaining)))

  const conflict = save.error instanceof ApiError && save.error.status === 409 ? save.error.message : null
  const otherError = save.error && !conflict ? save.error.message : null
  const show = (field: string) => touched[field] || touched.submit

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTouched((t) => ({ ...t, submit: true }))
    if (invalid) {
      requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus())
      return
    }
    if (!loaded || !dirty) return
    save.mutate(body, { onSuccess: () => setSaved(true) })
  }
  const edit = () => {
    setSaved(false)
    if (save.error) save.reset()
  }

  return (
    <section
      id="plan-settings"
      aria-label="Plan settings"
      tabIndex={-1}
      className="scroll-mt-6 rounded-xl border border-line bg-white focus:outline-none"
    >
      <div className="flex flex-col gap-1 px-4 pt-4 pb-3">
        <SectionLabel>Plan settings</SectionLabel>
        <p className="m-0 text-muted">
          The planner and the advisor keep every term within these limits.
        </p>
      </div>
      <form ref={form} noValidate onSubmit={submit} onChange={edit} className="flex flex-col gap-5 border-t border-line-soft px-4 py-4">
        <div className="flex flex-wrap gap-x-10 gap-y-5">
          <div className="flex min-w-[240px] flex-1 flex-col gap-5">
            <div className="flex flex-col gap-1">
              <label htmlFor={`${id}-grad`} className="font-semibold">Graduation term</label>
              <select
                id={`${id}-grad`}
                value={grad}
                onChange={(e) => setGrad(e.target.value)}
                disabled={!loaded}
                aria-describedby={`${id}-grad-hint${conflict ? ` ${id}-grad-error` : ''}`}
                aria-invalid={!!conflict || undefined}
                className={`${inputClass} max-w-[220px] border-[#C3C9BC]`}
              >
                {options.map((t) => (
                  <option key={t} value={t}>{termLabel(t, true)}</option>
                ))}
              </select>
              <span id={`${id}-grad-hint`} className="text-[13px] text-muted">
                Later adds empty terms. Earlier only works once the terms you’d drop are empty.
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor={`${id}-limit`} className="font-semibold">Default credit limit per term</label>
              <input
                id={`${id}-limit`}
                type="number"
                inputMode="numeric"
                min={CREDIT_MIN}
                max={CREDIT_MAX}
                step={1}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                disabled={!loaded}
                onBlur={() => setTouched((t) => ({ ...t, limit: true }))}
                aria-describedby={`${id}-limit-hint${show('limit') && limitError ? ` ${id}-limit-error` : ''}`}
                aria-invalid={(show('limit') && !!limitError) || undefined}
                className={`${inputClass} w-24 border-[#C3C9BC]`}
              />
              <span id={`${id}-limit-hint`} className="text-[13px] text-muted">
                {CREDIT_MIN}–{CREDIT_MAX} credits. Used for every term without its own cap.
              </span>
              {show('limit') && limitError && (
                <span id={`${id}-limit-error`} className="text-[13px] font-semibold text-accent">{limitError}</span>
              )}
            </div>
          </div>

          <fieldset className="m-0 flex min-w-[260px] flex-[2_1_320px] flex-col gap-1 border-0 p-0">
            <legend className="mb-1 p-0 font-semibold">Credit cap for each remaining term</legend>
            <span id={`${id}-caps-hint`} className="mb-2 text-[13px] text-muted">
              Optional. Leave a term blank to use your default{limitError ? '' : ` of ${limit}`}.
            </span>
            {!loaded && <span className="text-muted">Loading your plan…</span>}
            {loaded && remaining.length === 0 && <span className="text-muted">No terms left after this one.</span>}
            <ul className="m-0 list-none p-0">
              {remaining.map((t) => {
                const err = show(t) ? capErrors[t] : null
                const cap = Number(caps[t]?.trim() || limit)
                const over = !capErrors[t] && !limitError && (planned[t] ?? 0) > cap
                return (
                  <li key={t} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-soft py-2 first:border-t-0">
                    <label htmlFor={`${id}-${t}`} className="w-24 font-semibold">{termLabel(t)}</label>
                    <input
                      id={`${id}-${t}`}
                      type="number"
                      inputMode="numeric"
                      min={CREDIT_MIN}
                      max={CREDIT_MAX}
                      step={1}
                      value={caps[t] ?? ''}
                      placeholder={limitError ? '' : limit}
                      onChange={(e) => setCaps((c) => ({ ...c, [t]: e.target.value }))}
                      onBlur={() => setTouched((x) => ({ ...x, [t]: true }))}
                      aria-label={`${termLabel(t)} credit cap`}
                      aria-describedby={`${id}-caps-hint ${id}-${t}-planned${err ? ` ${id}-${t}-error` : ''}`}
                      aria-invalid={!!err || undefined}
                      className={`${inputClass} w-20 border-[#C3C9BC]`}
                    />
                    <span id={`${id}-${t}-planned`} className={`text-[13px] ${over ? 'font-semibold text-accent' : 'text-muted'}`}>
                      {planned[t] ?? 0} credits planned{over ? ', over this cap' : ''}
                    </span>
                    {err && (
                      <span id={`${id}-${t}-error`} className="basis-full text-[13px] font-semibold text-accent">{err}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </fieldset>
        </div>

        {conflict && (
          <p id={`${id}-grad-error`} role="alert" className="m-0 rounded-lg bg-ground p-3 font-semibold text-accent">
            {conflict}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-line-soft pt-4">
          {otherError && <span role="alert" className="mr-auto font-semibold text-accent">{otherError}</span>}
          <span role="status" className="text-muted">{saved && !dirty ? 'Saved. Your plan is updated.' : ''}</span>
          <Button type="submit" variant="primary" disabled={save.isPending || !dirty}>
            {save.isPending ? 'Saving…' : 'Save plan settings'}
          </Button>
        </div>
      </form>
    </section>
  )
}
