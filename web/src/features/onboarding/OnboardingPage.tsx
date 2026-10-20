import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { keys, useMe, useOnboardingOptions, useSignOut } from '../../api/hooks'
import type { ParsedCourse } from '../../api/types'
import { Button, Logo, SectionLabel } from '../../ui'
import { termLabel } from '../../ui/terms'
import { termIndex, termsAfter } from '../profile/settings'
import CourseSearch, { type PickedCourse } from './CourseSearch'
import GoalsStep from './GoalsStep'
import { catalogYear, graduationTerms, olderRules, type Stage, stageOf, startingChoices } from './goals'

type Review = { courses: ParsedCourse[]; unread: string[]; skipped: string[] }

const toBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(new Error('That file couldn’t be read.'))
    reader.readAsDataURL(file)
  })

const PROGRAMS = [
  { id: 'cs-eng', label: 'Engineering (B.S.)', name: 'Engineering', detail: 'Computer Science B.S. · College of Engineering' },
  { id: 'cs-as', label: 'Arts & Sciences (B.A.)', name: 'Arts & Sciences', detail: 'Computer Science B.A. · College of Arts & Sciences' },
]

const select =
  'h-11 w-full appearance-none rounded-lg border border-[#C3C9BC] bg-white pr-9 pl-3 text-[15px] hover:border-line-strong'

/** A native select with the app's chevron (the browser's own differs on every platform). */
function TermSelect({ id, label, value, terms, onChange }: { id: string; label: string; value: string; terms: string[]; onChange: (t: string) => void }) {
  return (
    <label htmlFor={id} className="flex min-w-0 flex-col gap-1.5">
      <span className="text-[13.5px] font-semibold">{label}</span>
      <span className="relative">
        <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={select}>
          {terms.map((t) => <option key={t} value={t}>{termLabel(t, true)}</option>)}
        </select>
        <svg aria-hidden="true" viewBox="0 0 16 16" className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-muted">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </label>
  )
}
const PLACEHOLDER = `AP Computer Science A  5
FA24  CS 1110 / MATH 1910 / CHEM 2090 / FWS
SP25  CS 211x, MATH 1920, PHYS 1112
FA25  CS 2800 MATH 2940 PHYS 2213 ECON 1110
SP26  CS 3110, CS 3410, ENGRD 2700 (4cr)`

type Confirmed = { term: string | null; code: string; credits?: number }

const withTerm = (terms: string[], term: string) =>
  terms.includes(term) ? terms : [...terms, term].sort((a, b) => termIndex(a) - termIndex(b))

const issueLabel: Record<string, string> = {
  ambiguous_code: 'Which one?',
  credit_mismatch: 'Credits differ',
  ap_credit: 'Check this',
  unknown_course: 'Not found',
  duplicate: 'Listed twice',
}

const STEPS: Record<Stage, [string, string][]> = {
  continuing: [
    ['Your coursework', 'Pasted from Student Center'],
    ['Check what we read', 'Nothing is planned until you confirm'],
    ['What you’re aiming for', 'Three optional questions'],
  ],
  first: [
    ['This semester', 'What you’re taking now'],
    ['Check what we read', 'Nothing is planned until you confirm'],
    ['What you’re aiming for', 'Three optional questions'],
  ],
  // nothing taken yet, so no coursework to check
  incoming: [
    ['Your program', 'Where you’re starting'],
    ['What you’re aiming for', 'Three optional questions'],
  ],
}

function Steps({ step, stage }: { step: number; stage: Stage }) {
  const items = STEPS[stage]
  if (stage === 'incoming') step = step === 2 ? 1 : 0
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

/** One term on the review step, with a way to add a course the reading missed. */
function TermGroup({ label, onAdd, children }: { label: string; onAdd: (c: PickedCourse) => void; children: React.ReactNode }) {
  const [adding, setAdding] = useState(false)
  return (
    <div className="rounded-xl border border-line bg-white">
      <SectionLabel className="px-4 pt-3 pb-1">{label}</SectionLabel>
      <ul className="m-0 list-none p-0">{children}</ul>
      <div className="border-t border-line-soft px-4 py-2.5">
        {adding ? (
          <CourseSearch
            autoFocus
            label={`Add a course to ${label}`}
            onPick={(c) => {
              onAdd(c)
              setAdding(false)
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            aria-label={`Add a course to ${label}`}
            className="border-0 bg-transparent p-0 text-[13.5px] font-semibold underline underline-offset-2"
          >
            + Add a course
          </button>
        )}
      </div>
    </div>
  )
}

function Row({
  course,
  choice,
  onChoose,
  onReplace,
  onRemove,
}: {
  course: ParsedCourse
  choice: string | undefined
  onChoose: (value: string) => void
  onReplace: (c: PickedCourse) => void
  onRemove: () => void
}) {
  const name = course.code ?? course.raw
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
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${name}`}
          className="border-0 bg-transparent p-0 text-[13px] text-muted underline underline-offset-2"
        >
          Remove
        </button>
      </div>
      {course.note && <span className="text-[12.5px] text-muted">{course.note}</span>}
      {issue && !resolved && (
        <div className="flex flex-col gap-2 rounded-lg bg-ground p-3">
          <span className="text-[13.5px]">{issue.message}</span>
          <div className="flex flex-wrap gap-2">
            {issue.options.map((o) => (
              <Button key={o.value} aria-label={`${o.label} (${name})`} onClick={() => onChoose(o.value)}>
                {o.label}
              </Button>
            ))}
          </div>
          {/* a course we couldn't match, or a "211x" with no listed options: find it in the roster */}
          {(issue.kind === 'unknown_course' || (issue.kind === 'ambiguous_code' && issue.options.length === 0)) && (
            <CourseSearch label={`Find the course for ${name}`} onPick={onReplace} />
          )}
        </div>
      )}
    </li>
  )
}

export default function OnboardingPage() {
  const qc = useQueryClient()
  const { data: me } = useMe()
  const signOut = useSignOut()
  const { data: options } = useOnboardingOptions()
  const [start] = useState(() => startingChoices(me, PROGRAMS.map((p) => p.id)))
  const [step, setStep] = useState(0)
  const [program, setProgram] = useState(start.program)
  const [entering, setEntering] = useState(start.entering)
  const [graduating, setGraduating] = useState(start.graduating)
  const [text, setText] = useState('')
  // what was read, from pasted text or a transcript; the student edits it on the review step
  const [parsed, setParsed] = useState<Review | null>(null)
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // confirmed courses wait here until the goals step, where the plan is built with the
  // semester load the student picks
  const [pending, setPending] = useState<Confirmed[]>([])
  const [dragging, setDragging] = useState(false)
  // the student chose to add courses one by one rather than upload or paste
  const [manual, setManual] = useState(false)

  const read = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await unwrap(
        api.POST('/api/onboarding/parse', { body: { text, program, entering_term: entering } }),
      )
      setParsed({ courses: result.courses, unread: result.unread, skipped: [] })
      setChoices({})
      setManual(false)
      setStep(1)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const upload = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Upload the transcript as a PDF, or paste your courses instead.')
      return
    }
    if (file.size > 5_000_000) {
      setError('That file is larger than a transcript should be (5 MB).')
      return
    }
    setBusy(true)
    try {
      const result = await unwrap(
        api.POST('/api/onboarding/transcript', { body: { pdf_base64: await toBase64(file) } }),
      )
      const detected = result.program && PROGRAMS.some((p) => p.id === result.program) ? result.program : program
      setProgram(detected)
      const first = result.entering_term
      const since = options?.rule_years[detected]?.[0]
      if (first && since && catalogYear(first) < since) {
        setError(
          `Your transcript starts in ${termLabel(first, true)}. CourseCompass only has degree rules for students ` +
            `who started in Fall ${since.slice(0, 4)} or later, so it can’t plan for you yet.`,
        )
        return
      }
      if (first) pickEntering(first)
      setParsed({ courses: result.courses, unread: result.unread, skipped: result.skipped })
      setChoices({})
      setManual(false)
      setStep(1)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  // a first-semester student picks courses before anything has been read, so start empty
  const edit = (update: (courses: ParsedCourse[]) => ParsedCourse[]) =>
    setParsed((p) => ({ ...(p ?? { unread: [], skipped: [] }), courses: update(p?.courses ?? []) }))
  const remove = (id: string) => edit((cs) => cs.filter((c) => c.id !== id))
  // a course picked from the roster replaces a row we couldn't match, or adds one to a term
  const replace = (id: string, c: PickedCourse) =>
    edit((cs) => cs.map((r) => (r.id === id ? { ...r, code: c.code, title: c.title, credits: c.credits, issue: null } : r)))
  const add = (term: string | null, c: PickedCourse) =>
    edit((cs) => [
      ...cs,
      { id: crypto.randomUUID().slice(0, 8), raw: c.code, term, code: c.code, title: c.title, credits: c.credits, issue: null, note: null },
    ])

  const current = options?.current_term
  const stage: Stage = current ? stageOf(entering, current) : 'continuing'
  const rules = olderRules(entering, options?.rule_years[program] ?? [])
  // each program's rules start at its oldest catalog year; earlier starts can't be planned
  const firstYear = options?.rule_years[program]?.[0]
  const enteringTerms = (options?.entering_terms ?? []).filter((t) => !firstYear || catalogYear(t) >= firstYear)
  const unsupported = !!options && !enteringTerms.includes(entering)

  // a new start term moves graduation out to a standard eight semesters if it was sooner
  const pickEntering = (term: string) => {
    setEntering(term)
    const eighth = termsAfter(term, undefined, 7).at(-1)!
    if (termIndex(graduating) < termIndex(eighth)) setGraduating(eighth)
  }

  // builds the plan; errors surface on the goals step
  const build = async (maxCredits?: number) => {
    await unwrap(
      api.POST('/api/onboarding/confirm', {
        body: {
          program,
          entering_term: entering,
          graduation_term: graduating,
          courses: pending,
          max_credits: maxCredits ?? null,
        },
      }),
    )
    await qc.invalidateQueries({ queryKey: keys.me })
    await qc.invalidateQueries({ queryKey: keys.plan })
  }

  const confirm = () => {
    if (!parsed) return
    const courses = parsed.courses.flatMap((c) => {
      const choice = choices[c.id]
      if (choice === 'drop' || c.issue?.kind === 'ap_credit') return []
      if (c.issue?.kind === 'ambiguous_code' || c.issue?.kind === 'unknown_course')
        return [{ term: c.term, code: choice }]
      if (c.issue?.kind === 'credit_mismatch') return [{ term: c.term, code: c.code!, credits: Number(choice) }]
      // transcript credits are what was earned (variable-credit courses differ from the roster)
      return c.code ? [{ term: c.term, code: c.code, credits: c.credits ?? undefined }] : []
    })
    setPending(courses)
    setStep(2)
  }

  const left = parsed ? parsed.courses.filter((c) => c.issue && choices[c.id] === undefined).length : 0
  const none = !parsed || parsed.courses.length === 0
  const thisTerm = parsed?.courses.filter((c) => c.term === entering) ?? []
  const matched = parsed?.courses.filter((c) => c.code).length ?? 0
  const semesters = termIndex(graduating) - termIndex(entering) + 1
  // every term from the first one to now, so a missing course can be added to an empty term
  const history = current && stage !== 'incoming' ? [entering, ...termsAfter(entering, current, 20)] : []
  const terms = [
    ...new Set([
      ...(parsed?.courses.some((c) => !c.term) ? [''] : []),
      ...[...history, ...(parsed?.courses.flatMap((c) => (c.term ? [c.term] : [])) ?? [])].sort(
        (a, b) => termIndex(a) - termIndex(b),
      ),
    ]),
  ]
  const groups = parsed
    ? terms.map((term) => ({ term, courses: parsed.courses.filter((c) => (c.term ?? '') === term) }))
    : []

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-paper px-5 py-3">
        <Logo />
        <span className="text-[17px] font-extrabold tracking-tight">CourseCompass</span>
        <span className="text-muted max-sm:hidden">Setting up your plan · takes about 5 minutes</span>
        <span className="flex-1" />
        {me?.code && <span className="font-mono text-[13px] text-muted max-sm:hidden">{me.code}</span>}
        <Button variant="quiet" onClick={signOut}>
          Sign out
        </Button>
      </header>
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-5 py-8">
        <Steps step={step} stage={stage} />

        {step === 0 && (
          <section className="flex flex-col gap-5 rounded-xl border border-line bg-white p-5">
            <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
              <legend className="mb-2 p-0 text-[13.5px] font-semibold">Your program</legend>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {PROGRAMS.map((p) => {
                  const on = program === p.id
                  return (
                    <label
                      key={p.id}
                      htmlFor={`program-${p.id}`}
                      className={`flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink ${
                        on ? 'border-ink bg-chip/60 shadow-[inset_0_0_0_1px_var(--color-ink)]' : 'border-line bg-white hover:border-line-strong'
                      }`}
                    >
                      <input
                        id={`program-${p.id}`}
                        type="radio"
                        name="program"
                        value={p.id}
                        aria-label={p.label}
                        checked={on}
                        onChange={() => setProgram(p.id)}
                        className="sr-only"
                      />
                      <span
                        aria-hidden="true"
                        className={`mt-0.5 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border-[1.5px] ${on ? 'border-ink' : 'border-line-strong'}`}
                      >
                        {on && <span className="h-2 w-2 rounded-full bg-ink" />}
                      </span>
                      <span className="flex min-w-0 flex-col">
                        <span className="font-semibold">{p.name}</span>
                        <span className="text-[13px] text-muted">{p.detail}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>
            <div className="flex flex-col gap-2">
              <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
                <TermSelect id="onboarding-entering" label="First semester at Cornell" value={entering} terms={withTerm(enteringTerms, entering)} onChange={pickEntering} />
                <TermSelect
                  id="onboarding-graduating"
                  label="Expected graduation"
                  value={graduating}
                  terms={withTerm(current ? graduationTerms(entering, current) : [], graduating)}
                  onChange={setGraduating}
                />
              </div>
              <p className="m-0 text-[13px] text-muted">
                <span className="font-semibold text-ink-soft">
                  {semesters} {semesters === 1 ? 'semester' : 'semesters'}
                </span>
                , {termLabel(entering, true)} to {termLabel(graduating, true)}. {rules
                  ? `There are no separate rules for a ${termLabel(entering, true)} start yet, so you’re checked against the current CS requirements (for students who started in Fall ${rules.slice(0, 4)} or later).`
                  : 'Your first semester decides which year’s degree requirements apply.'}
              </p>
            </div>
            {unsupported && firstYear && (
              <p role="alert" className="m-0 text-accent">
                {PROGRAMS.find((p) => p.id === program)?.label} rules start with students who began in Fall{' '}
                {firstYear.slice(0, 4)}, so CourseCompass can’t plan for a {termLabel(entering, true)} start yet.
              </p>
            )}
            {stage === 'incoming' ? (
              <>
                <p className="m-0 max-w-2xl">
                  You start in {termLabel(entering, true)}, so there’s nothing to import. We’ll lay out every
                  requirement as open slots across your semesters, and you fill them in as you go.
                </p>
                {error && <p role="alert" className="m-0 text-accent">{error}</p>}
                <Button
                  variant="primary"
                  className="h-11 self-end"
                  disabled={!current || unsupported}
                  onClick={() => {
                    setPending([])
                    setStep(2)
                  }}
                >
                  Continue
                </Button>
              </>
            ) : (
              <>
                <div
                    onDragOver={(e) => {
                      e.preventDefault()
                      setDragging(true)
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => {
                      e.preventDefault()
                      setDragging(false)
                      upload(e.dataTransfer.files[0])
                    }}
                    className={`flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border-2 border-dashed px-5 py-4 ${
                      dragging ? 'border-ink bg-chip' : 'border-[#C3C9BC] bg-ground'
                    }`}
                  >
                    <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1">
                      <span className="font-semibold">Upload your unofficial transcript</span>
                      <span className="text-[13px] text-muted">
                        The PDF from Student Center. Drop it here or choose it. We read your courses, terms and
                        credits, including AP credit, and don’t keep the file or your grades.
                      </span>
                    </div>
                    <label className={`inline-flex h-11 cursor-pointer items-center rounded-md bg-ink px-4 font-semibold text-paper ${busy ? 'opacity-60' : ''}`}>
                      {busy ? 'Reading…' : 'Choose PDF'}
                      <input
                        type="file"
                        accept="application/pdf,.pdf"
                        className="sr-only"
                        disabled={busy}
                        onChange={(e) => {
                          upload(e.target.files?.[0])
                          e.target.value = ''
                        }}
                      />
                    </label>
                  </div>
                {stage === 'first' ? (
                  // a first semester is a handful of courses in one term: picking each from the
                  // roster avoids typos and unknown codes, and is about as quick as typing them
                  <div className="flex flex-col gap-2">
                    <span className="font-semibold">Or find what you’re taking in {termLabel(entering, true)}</span>
                    {thisTerm.length > 0 && (
                      <ul className="m-0 flex list-none flex-col rounded-xl border border-line bg-white p-0" aria-label="Courses you’re taking">
                        {thisTerm.map((c) => (
                          <li key={c.id} className="flex items-center gap-3 border-t border-line-soft px-4 py-2 first:border-t-0">
                            <span className="w-24 font-mono font-semibold">{c.code}</span>
                            <span className="min-w-0 flex-1 truncate text-ink-soft">{c.title}</span>
                            <span className="font-mono text-[12px] text-muted">{c.credits} cr</span>
                            <button
                              type="button"
                              onClick={() => remove(c.id)}
                              aria-label={`Remove ${c.code}`}
                              className="border-0 bg-transparent p-0 text-[13px] text-muted underline underline-offset-2"
                            >
                              Remove
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    <CourseSearch label={`Add a course you’re taking in ${termLabel(entering, true)}`} onPick={(c) => add(entering, c)} />
                    {error && <p role="alert" className="m-0 text-accent">{error}</p>}
                    <Button
                      variant="primary"
                      className="h-11 self-end"
                      disabled={busy || !thisTerm.length || unsupported}
                      onClick={() => {
                        // courses from another start term chosen earlier don't belong here
                        edit((cs) => cs.filter((c) => c.term === entering))
                        setChoices({})
                        setManual(false)
                        setStep(1)
                      }}
                    >
                      Continue
                    </Button>
                  </div>
                ) : (
                  <>
                    <label className="flex flex-col gap-2">
                      <span className="font-semibold">Or paste your courses</span>
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
                    {error && <p role="alert" className="m-0 text-accent">{error}</p>}
                    <div className="flex flex-wrap items-center justify-end gap-x-5 gap-y-2">
                      <button
                        type="button"
                        disabled={busy || unsupported}
                        onClick={() => {
                          setParsed({ courses: [], unread: [], skipped: [] })
                          setChoices({})
                          setManual(true)
                          setStep(1)
                        }}
                        className="border-0 bg-transparent p-0 text-[14px] font-semibold underline underline-offset-2 disabled:opacity-50"
                      >
                        Or add them one by one
                      </button>
                      <Button variant="primary" className="h-11" disabled={busy || !text.trim() || unsupported} onClick={read}>
                        Read my courses
                      </Button>
                    </div>
                  </>
                )}
              </>
            )}
          </section>
        )}

        {step === 1 && parsed && (
          <section className="flex flex-col gap-4">
            <div>
              <h1 className="m-0 text-2xl font-extrabold tracking-tight">
                {manual ? 'Add your courses' : stage === 'first' ? 'Is this what you’re taking?' : 'Is this what you’ve taken?'}
              </h1>
              <p className="m-0 text-muted">
                {manual
                  ? 'Use “Add a course” under each semester and search by code or title. Include this semester’s courses.'
                  : `We matched ${matched} ${matched === 1 ? 'course' : 'courses'} against the Class Roster. ` +
                    (left === 0 ? 'Everything is confirmed.' : left === 1 ? '1 thing needs you.' : `${left} things need you.`)}
              </p>
            </div>
            {groups.map((g) => (
              <TermGroup
                key={g.term}
                label={g.term ? termLabel(g.term, true) : stage === 'first' ? termLabel(entering, true) : 'Before Cornell'}
                onAdd={(c) => add(g.term || null, c)}
              >
                {g.courses.map((c) => (
                  <Row
                    key={c.id}
                    course={c}
                    choice={choices[c.id]}
                    onChoose={(v) => setChoices((s) => ({ ...s, [c.id]: v }))}
                    onReplace={(picked) => replace(c.id, picked)}
                    onRemove={() => remove(c.id)}
                  />
                ))}
              </TermGroup>
            ))}
            {parsed.skipped.length > 0 && (
              <div className="flex flex-col gap-1 rounded-xl border border-line-soft px-4 py-3">
                <span className="font-semibold">Not counted from your transcript</span>
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-[13px] text-muted">
                  {parsed.skipped.map((line, i) => <li key={i}>{line}</li>)}
                </ul>
              </div>
            )}
            {parsed.unread.length > 0 && (
              <div role="status" className="flex flex-col gap-1.5 rounded-xl border border-line bg-highlight/30 px-4 py-3">
                <span className="font-semibold">
                  We couldn’t read {parsed.unread.length === 1 ? 'this line' : `these ${parsed.unread.length} lines`}
                </span>
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0 font-mono text-[13px]">
                  {parsed.unread.map((line, i) => <li key={i}>{line}</li>)}
                </ul>
                <span className="text-[13px] text-muted">
                  If one of them is a course, go back and fix it (for example the subject and number, like CS 2110), then read again.
                </span>
              </div>
            )}
            {error && <p role="alert" className="m-0 text-accent">{error}</p>}
            <div className="flex items-center justify-between gap-3">
              <Button onClick={() => setStep(0)}>Back</Button>
              <span className="text-[13px] text-muted">We’ll never count a course you haven’t confirmed.</span>
              <Button variant="primary" className="h-11" disabled={left > 0 || busy || none} onClick={confirm}>
                {none ? 'Add a course to continue' : left > 0 ? `${left} left to check` : 'Looks right. Continue'}
              </Button>
            </div>
          </section>
        )}

        {step === 2 && <GoalsStep build={build} onBack={() => setStep(stage === 'incoming' ? 0 : 1)} />}
      </main>
    </div>
  )
}
