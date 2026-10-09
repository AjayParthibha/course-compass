import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { keys } from '../../api/hooks'
import type { ParsedCourse, ParseResult } from '../../api/types'
import { Button, Logo, SectionLabel } from '../../ui'
import { termLabel } from '../../ui/terms'
import GoalsStep from './GoalsStep'

const ENTERING = ['FA22', 'SP23', 'FA23', 'SP24', 'FA24', 'SP25', 'FA25', 'SP26']
const GRADUATING = ['FA26', 'SP27', 'FA27', 'SP28', 'FA28', 'SP29', 'FA29', 'SP30']
const PROGRAMS = [
  { id: 'cs-eng', label: 'Engineering (B.S.)' },
  { id: 'cs-as', label: 'Arts & Sciences (B.A.)' },
]
const PLACEHOLDER = `AP Computer Science A  5
FA24  CS 1110 / MATH 1910 / CHEM 2090 / FWS
SP25  CS 211x, MATH 1920, PHYS 1112
FA25  CS 2800 MATH 2940 PHYS 2213 ECON 1110
SP26  CS 3110, CS 3410, ENGRD 2700 (4cr)`

const issueLabel: Record<string, string> = {
  ambiguous_code: 'Which one?',
  credit_mismatch: 'Credits differ',
  ap_credit: 'Check this',
  unknown_course: 'Not found',
  duplicate: 'Listed twice',
}

function Steps({ step }: { step: number }) {
  const items = [
    ['Your coursework', 'Pasted from Student Center'],
    ['Check what we read', 'Nothing is planned until you confirm'],
    ['What you’re aiming for', 'Three optional questions'],
  ]
  return (
    <ol className="m-0 flex list-none flex-wrap gap-6 p-0">
      {items.map(([title, sub], i) => (
        <li key={title} aria-current={i === step ? 'step' : undefined} className={`flex items-center gap-3 ${i === step ? '' : 'opacity-60'}`}>
          <span className={`grid h-7 w-7 place-items-center rounded-full font-mono text-[13px] font-semibold ${i <= step ? 'bg-ink text-paper' : 'border border-ink'}`}>
            {i + 1}
          </span>
          <span className="flex flex-col">
            <span className="font-semibold">{title}</span>
            <span className="text-[12.5px] text-muted">{sub}</span>
          </span>
        </li>
      ))}
    </ol>
  )
}

function Row({
  course,
  choice,
  onChoose,
}: {
  course: ParsedCourse
  choice: string | undefined
  onChoose: (value: string) => void
}) {
  const [typed, setTyped] = useState('')
  const issue = course.issue
  const resolved = !issue || choice !== undefined
  const picked = issue?.kind === 'ambiguous_code' && choice !== undefined
  return (
    <li className="flex flex-col gap-2 border-t border-line-soft px-4 py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-3">
        <span className="w-28 font-mono font-semibold">
          {picked ? choice : (course.code ?? (issue?.kind === 'ap_credit' ? 'AP' : course.raw))}
        </span>
        <span className="flex-1 text-ink-soft">
          {picked ? (issue.options.find((o) => o.value === choice)?.label.split(' · ')[1] ?? '') : (course.title ?? '')}
        </span>
        {course.credits != null && <span className="font-mono text-[12px] text-muted">{choice && issue?.kind === 'credit_mismatch' ? choice : course.credits} cr</span>}
        <span
          className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${!issue ? 'bg-chip' : resolved ? 'bg-highlight' : 'bg-accent text-white'}`}
        >
          {!issue ? 'Matched' : resolved ? (choice === 'drop' ? 'Left out' : 'Confirmed') : issueLabel[issue.kind]}
        </span>
      </div>
      {issue && !resolved && (
        <div className="flex flex-col gap-2 rounded-lg bg-ground p-3">
          <span className="text-[13.5px]">{issue.message}</span>
          <div className="flex flex-wrap gap-2">
            {issue.options.map((o) => (
              <Button key={o.value} onClick={() => onChoose(o.value)}>
                {o.label}
              </Button>
            ))}
            {issue.kind === 'unknown_course' && (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (typed.trim()) onChoose(typed.trim().toUpperCase())
                }}
              >
                <input
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  placeholder="e.g. ENGL 1170"
                  aria-label="Course code"
                  className="h-9 w-36 rounded-md border border-[#C3C9BC] bg-white px-2 font-mono"
                />
                <Button type="submit">Use this</Button>
              </form>
            )}
          </div>
        </div>
      )}
    </li>
  )
}

export default function OnboardingPage() {
  const qc = useQueryClient()
  const [step, setStep] = useState(0)
  const [program, setProgram] = useState('cs-eng')
  const [entering, setEntering] = useState('FA24')
  const [graduating, setGraduating] = useState('SP28')
  const [text, setText] = useState('')
  const [parsed, setParsed] = useState<ParseResult | null>(null)
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const read = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await unwrap(
        api.POST('/api/onboarding/parse', { body: { text, program, entering_term: entering } }),
      )
      setParsed(result)
      setChoices({})
      setStep(1)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    if (!parsed) return
    const courses = parsed.courses.flatMap((c) => {
      const choice = choices[c.id]
      if (choice === 'drop' || c.issue?.kind === 'ap_credit') return []
      if (c.issue?.kind === 'ambiguous_code' || c.issue?.kind === 'unknown_course')
        return [{ term: c.term, code: choice }]
      if (c.issue?.kind === 'credit_mismatch') return [{ term: c.term, code: c.code!, credits: Number(choice) }]
      return c.code ? [{ term: c.term, code: c.code }] : []
    })
    setBusy(true)
    setError(null)
    try {
      await unwrap(
        api.POST('/api/onboarding/confirm', {
          body: { program, entering_term: entering, graduation_term: graduating, courses },
        }),
      )
      await qc.invalidateQueries({ queryKey: keys.me })
      await qc.invalidateQueries({ queryKey: keys.plan })
      setStep(2)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const left = parsed ? parsed.courses.filter((c) => c.issue && choices[c.id] === undefined).length : 0
  const groups = parsed
    ? [...new Set(parsed.courses.map((c) => c.term ?? ''))].map((term) => ({
        term,
        courses: parsed.courses.filter((c) => (c.term ?? '') === term),
      }))
    : []

  return (
    <div className="min-h-screen">
      <header className="flex items-center gap-3 border-b border-line bg-paper px-5 py-3">
        <Logo />
        <span className="text-[17px] font-extrabold tracking-tight">CourseCompass</span>
        <span className="text-muted">Setting up your plan · takes about 5 minutes</span>
      </header>
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-5 py-8">
        <Steps step={step} />

        {step === 0 && (
          <section className="flex flex-col gap-5 rounded-xl border border-line bg-white p-5">
            <fieldset className="m-0 flex flex-wrap gap-3 border-0 p-0">
              <legend className="mb-2 font-semibold">Your program</legend>
              {PROGRAMS.map((p) => (
                <label
                  key={p.id}
                  htmlFor={`program-${p.id}`}
                  className={`flex h-10 items-center gap-2 rounded-md border px-3 ${program === p.id ? 'border-ink' : 'border-line'}`}
                >
                  <input
                    id={`program-${p.id}`}
                    type="radio"
                    name="program"
                    value={p.id}
                    aria-label={p.label}
                    checked={program === p.id}
                    onChange={() => setProgram(p.id)}
                  />
                  {p.label}
                </label>
              ))}
            </fieldset>
            <div className="flex flex-wrap gap-6">
              <label htmlFor="onboarding-entering" className="flex flex-col gap-1">
                <span className="font-semibold">First semester at Cornell</span>
                <select id="onboarding-entering" value={entering} onChange={(e) => setEntering(e.target.value)} className="h-10 rounded-md border border-[#C3C9BC] bg-white px-2">
                  {ENTERING.map((t) => <option key={t} value={t}>{termLabel(t, true)}</option>)}
                </select>
              </label>
              <label htmlFor="onboarding-graduating" className="flex flex-col gap-1">
                <span className="font-semibold">Expected graduation</span>
                <select id="onboarding-graduating" value={graduating} onChange={(e) => setGraduating(e.target.value)} className="h-10 rounded-md border border-[#C3C9BC] bg-white px-2">
                  {GRADUATING.map((t) => <option key={t} value={t}>{termLabel(t, true)}</option>)}
                </select>
              </label>
            </div>
            <p className="m-0 text-[13px] text-muted">
              We check you against the CS requirements for your entering year, not this year’s.
            </p>
            <label className="flex flex-col gap-2">
              <span className="font-semibold">Paste your courses</span>
              <span className="text-[13px] text-muted">
                Copy from Student Center or type them out. Messy is fine: one term per line works best.
              </span>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={8}
                placeholder={PLACEHOLDER}
                className="rounded-md border border-[#C3C9BC] p-3 font-mono text-[13px]"
              />
            </label>
            {error && <p className="m-0 text-accent">{error}</p>}
            <Button variant="primary" className="h-11 self-end" disabled={busy || !text.trim()} onClick={read}>
              Read my courses
            </Button>
          </section>
        )}

        {step === 1 && parsed && (
          <section className="flex flex-col gap-4">
            <div>
              <h1 className="m-0 text-2xl font-extrabold tracking-tight">Is this what you’ve taken?</h1>
              <p className="m-0 text-muted">
                We matched {parsed.courses.filter((c) => c.code).length} courses against the Class Roster.{' '}
                {left === 0 ? 'Everything is confirmed.' : left === 1 ? '1 thing needs you.' : `${left} things need you.`}
              </p>
            </div>
            {groups.map((g) => (
              <div key={g.term} className="rounded-xl border border-line bg-white">
                <SectionLabel className="px-4 pt-3 pb-1">{g.term ? termLabel(g.term, true) : 'Before Cornell'}</SectionLabel>
                <ul className="m-0 list-none p-0">
                  {g.courses.map((c) => (
                    <Row key={c.id} course={c} choice={choices[c.id]} onChoose={(v) => setChoices((s) => ({ ...s, [c.id]: v }))} />
                  ))}
                </ul>
              </div>
            ))}
            {error && <p className="m-0 text-accent">{error}</p>}
            <div className="flex items-center justify-between gap-3">
              <Button onClick={() => setStep(0)}>Back</Button>
              <span className="text-[13px] text-muted">We’ll never count a course you haven’t confirmed.</span>
              <Button variant="primary" className="h-11" disabled={left > 0 || busy} onClick={confirm}>
                {left > 0 ? `${left} left to check` : 'Looks right. Continue'}
              </Button>
            </div>
          </section>
        )}

        {step === 2 && <GoalsStep />}
      </main>
    </div>
  )
}
