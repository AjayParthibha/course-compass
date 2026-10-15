import { delay, http, HttpResponse } from 'msw'
import type { AdvisorEvent, Placement, PlanOp, PlanSettingsUpdate, ProfileFact, Proposal } from '../api/types'
import { CREDIT_MAX, CREDIT_MIN, nextTerm, termIndex, TERMS_AHEAD } from '../features/profile/settings'
import * as fx from './fixtures'

// In-memory state for mock mode. Resets on page reload.
const db = {
  history: [fx.placements] as Placement[][],
  proposals: new Map<number, Proposal>(),
  facts: [...fx.facts],
  student: { ...fx.student },
  terms: fx.TERMS,
}

let nextFactId = Math.max(0, ...fx.facts.map((f) => f.id)) + 1
const current = () => db.history[db.history.length - 1]
const state = () => fx.planState(current(), db.history.length + 3, db.terms)
const error = (status: number, detail: string) => HttpResponse.json({ detail }, { status })

function termsThrough(first: string, last: string) {
  const out = [first]
  while (termIndex(out[out.length - 1]) < termIndex(last)) out.push(nextTerm(out[out.length - 1]))
  return out
}

/** The backend's checks for an edit, so mock mode fails the same way. */
function opError(ps: Placement[], ops: PlanOp[]): string | null {
  for (const op of ops) {
    if (!('placement_id' in op)) continue
    const p = ps.find((x) => x.id === op.placement_id)
    if (!p) return `no placement ${op.placement_id}`
    if (op.op === 'move' && p.status === 'completed') return `${p.course} is already completed`
    if (op.op === 'move' && p.locked && p.term !== op.term)
      return `${p.course ?? p.slot_label ?? 'That slot'} is kept in its term. Unlock it before moving it.`
  }
  return null
}

const validCredits = (n: unknown) => Number.isInteger(n) && (n as number) >= CREDIT_MIN && (n as number) <= CREDIT_MAX

function applyOps(ps: Placement[], ops: PlanOp[]): Placement[] {
  let out = ps.map((p) => ({ ...p }))
  for (const op of ops) {
    if (op.op === 'move') out = out.map((p) => (p.id === op.placement_id ? { ...p, term: op.term } : p))
    if (op.op === 'lock')
      out = out.map((p) => (p.id === op.placement_id ? { ...p, locked: op.locked ?? true } : p))
    if (op.op === 'remove') out = out.filter((p) => p.id !== op.placement_id)
    if (op.op === 'replace')
      out = out.map((p) =>
        p.id === op.placement_id
          ? { ...p, course: op.course, title: fx.titles[op.course] ?? op.course, slot_label: null }
          : p,
      )
    if (op.op === 'add')
      out.push({
        id: `new-${Math.random().toString(36).slice(2, 8)}`,
        term: op.term,
        course: op.course ?? null,
        title: op.course ? (fx.titles[op.course] ?? null) : null,
        slot: op.slot ?? null,
        slot_label: op.slot ?? null,
        credits: 4,
        status: 'planned',
        locked: false,
        origin: 'user',
      })
  }
  return out
}

function sse(events: AdvisorEvent[]) {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    async start(controller) {
      for (const e of events) {
        await delay(e.type === 'text' ? 25 : 350)
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(e)}\n\n`))
      }
      controller.close()
    },
  })
  return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream' } })
}

const words = (text: string): AdvisorEvent[] =>
  text.split(/(?<= )/).map((delta) => ({ type: 'text', delta }))

const tool = (id: string, name: string, summary: string): AdvisorEvent[] => [
  { type: 'tool_start', id, name, args: {} },
  { type: 'tool_end', id, name, summary, ok: true },
]

function scriptFor(message: string): AdvisorEvent[] {
  const m = message.toLowerCase()
  if (m.includes('lighter')) {
    const proposal = fx.lighterSpringProposal(db.history.length + 3)
    db.proposals.set(proposal.id, proposal)
    return [
      ...tool('t1', 'update_profile', 'saved (stated)'),
      ...tool('t2', 'get_plan_state', 'SP27 has 18 credits'),
      ...tool('t3', 'propose_changes', 'proposal ready'),
      { type: 'proposal', proposal },
      ...words(
        'Spring drops to 14 credits. I moved CS 4740 to fall, which meant pushing CS 4780 to your last spring so fall stays at 14. Graduation doesn’t move.',
      ),
      { type: 'done', conversation_id: 1 },
    ]
  }
  if (m.includes('liberal')) {
    return [
      ...tool('t1', 'get_plan_state', 'SP27 has 1 open liberal studies slot'),
      ...tool('t2', 'list_eligible', '41 courses fit'),
      ...tool('t3', 'read_profile', 'nothing on file about this'),
      ...words(
        '41 courses fit that slot, so this depends on you more than on the rules. Your answer would change the top pick, so one question first.',
      ),
      {
        type: 'question',
        question: 'What do you want this course to do for you?',
        options: ['Something I’d enjoy', 'Help with communication', 'Explore a new field'],
        dimension: 'ls_goal',
      },
      { type: 'done', conversation_id: 1 },
    ]
  }
  return [
    ...tool('t1', 'get_plan_state', '32 placements, 4 open slots'),
    ...words(
      'You’re on track: every requirement is either done or planned, and you still graduate in May 2028. (This is the mock advisor; start the backend with an API key for real answers.)',
    ),
    { type: 'done', conversation_id: 1 },
  ]
}

export const handlers = [
  http.post('/api/auth/login', () => HttpResponse.json({ token: 'mock', student: db.student })),
  http.get('/api/auth/me', () => HttpResponse.json(db.student)),

  http.get('/api/plan', () => HttpResponse.json(state())),
  http.post('/api/plan/ops', async ({ request }) => {
    const body = (await request.json()) as { ops: PlanOp[]; dry_run?: boolean }
    const problem = opError(current(), body.ops)
    if (problem) return error(400, problem)
    const next = applyOps(current(), body.ops)
    if (body.dry_run) return HttpResponse.json(fx.planState(next, 0, db.terms))
    db.history.push(next)
    return HttpResponse.json(state())
  }),
  http.patch('/api/plan/settings', async ({ request }) => {
    const body = (await request.json()) as PlanSettingsUpdate
    const caps = body.term_caps ?? null
    if (body.max_credits != null && !validCredits(body.max_credits)) return error(422, 'max_credits out of range')
    if (caps && !Object.values(caps).every(validCredits)) return error(422, 'term cap out of range')
    const grad = body.graduation_term ?? db.student.graduation_term!
    const ahead = termIndex(grad) - termIndex(fx.CURRENT)
    if (grad !== db.student.graduation_term && (ahead < 0 || ahead > TERMS_AHEAD))
      return error(400, 'graduation has to be between this term and 4 years from now')
    const terms = termsThrough(db.student.entering_term!, grad)
    const stranded = current().filter((p) => !terms.includes(p.term))
    if (stranded.length)
      return error(409, `Graduating then would drop ${stranded.map((p) => p.course ?? p.slot_label).join(', ')}. Move or remove them first.`)
    const remaining = terms.filter((t) => termIndex(t) > termIndex(fx.CURRENT))
    const bad = Object.keys(caps ?? {}).find((t) => !remaining.includes(t))
    if (bad) return error(400, `${bad} isn't a remaining term in your plan`)
    db.student.term_caps = caps ?? Object.fromEntries(Object.entries(db.student.term_caps).filter(([t]) => remaining.includes(t)))
    db.student.graduation_term = grad
    if (body.max_credits != null) db.student.max_credits = body.max_credits
    db.terms = terms
    return HttpResponse.json(db.student)
  }),
  http.post('/api/plan/undo', () => {
    if (db.history.length > 1) db.history.pop()
    return HttpResponse.json(state())
  }),

  http.get('/api/courses/:code', ({ params }) =>
    HttpResponse.json(fx.courseDetail(decodeURIComponent(params.code as string))),
  ),
  http.get('/api/courses', () => HttpResponse.json([])),

  http.get('/api/proposals/:id', ({ params }) => {
    const p = db.proposals.get(Number(params.id))
    return p ? HttpResponse.json(p) : HttpResponse.json({ detail: 'no such proposal' }, { status: 404 })
  }),
  http.post('/api/proposals/:id/preview', ({ params }) => {
    const p = db.proposals.get(Number(params.id))
    if (!p) return HttpResponse.json({ detail: 'no such proposal' }, { status: 404 })
    return HttpResponse.json(fx.planState(applyOps(current(), p.ops as PlanOp[]), 0, db.terms))
  }),
  http.post('/api/proposals/:id/apply', ({ params }) => {
    const p = db.proposals.get(Number(params.id))
    if (!p || p.status !== 'pending')
      return HttpResponse.json({ detail: 'proposal is not pending' }, { status: 409 })
    const problem = opError(current(), p.ops as PlanOp[])
    if (problem) return error(409, problem)
    db.history.push(applyOps(current(), p.ops as PlanOp[]))
    p.status = 'applied'
    return HttpResponse.json(state())
  }),
  http.post('/api/proposals/:id/discard', ({ params }) => {
    const p = db.proposals.get(Number(params.id))!
    p.status = 'discarded'
    return HttpResponse.json(p)
  }),

  http.get('/api/profile', () => HttpResponse.json({ student: db.student, facts: db.facts })),
  http.get('/api/profile/export', () => HttpResponse.json({ student: db.student, facts: db.facts })),
  http.patch('/api/profile/student', async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>
    // graduation and credit limits only change through /api/plan/settings
    const misplaced = ['graduation_term', 'max_credits', 'term_caps'].find((k) => k in body)
    if (misplaced) return error(422, `${misplaced} is set in plan settings`)
    Object.assign(db.student, body)
    return HttpResponse.json(db.student)
  }),
  http.post('/api/profile/facts', async ({ request }) => {
    const body = (await request.json()) as Partial<ProfileFact>
    const fact = {
      ...db.facts[0],
      ...body,
      id: nextFactId++,
      status: body.status ?? 'stated',
    } as ProfileFact
    db.facts.push(fact)
    return HttpResponse.json(fact)
  }),
  http.patch('/api/profile/facts/:id', async ({ params, request }) => {
    const fact = db.facts.find((f) => f.id === Number(params.id))!
    Object.assign(fact, await request.json())
    return HttpResponse.json(fact)
  }),
  http.delete('/api/profile/facts/:id', ({ params }) => {
    db.facts = db.facts.filter((f) => f.id !== Number(params.id))
    return new HttpResponse(null, { status: 204 })
  }),
  http.delete('/api/profile', () => {
    db.facts = []
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/slots/:slot/candidates', ({ params, request }) => {
    const term = new URL(request.url).searchParams.get('term') ?? 'SP28'
    const all = fx.candidates(params.slot as string, term)
    const notForMe = new Map(db.facts.filter((f) => f.dimension === 'not_interested').map((f) => [f.value, f.id]))
    return HttpResponse.json({
      ...all,
      eligible_count: all.eligible_count - notForMe.size,
      candidates: all.candidates.filter((c) => !notForMe.has(c.course.code)),
      hidden: all.candidates
        .filter((c) => notForMe.has(c.course.code))
        .map((c) => ({ course: c.course, fact_id: notForMe.get(c.course.code)! })),
    })
  }),
  http.put('/api/courses/:code/not-interested', ({ params }) => {
    const code = params.code as string
    const fact = {
      ...db.facts[0],
      id: nextFactId++,
      dimension: 'not_interested',
      value: code,
      text: `Not interested in ${code}`,
      status: 'stated',
      evidence: 'Marked “Not for me” on Explore',
    } as ProfileFact
    db.facts.push(fact)
    return HttpResponse.json(fact)
  }),
  http.delete('/api/courses/:code/not-interested', ({ params }) => {
    db.facts = db.facts.filter((f) => !(f.dimension === 'not_interested' && f.value === params.code))
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/onboarding/parse', () =>
    HttpResponse.json({
      catalog_year: '2024-25',
      courses: [
        { id: 'a', raw: 'CS 1110', term: 'FA24', code: 'CS 1110', title: 'Intro to Computing', credits: 4, issue: null },
        {
          id: 'b',
          raw: 'CS 211x',
          term: 'SP25',
          code: null,
          title: null,
          credits: null,
          issue: {
            kind: 'ambiguous_code',
            message: 'You wrote CS 211x. Which course was it?',
            options: [
              { label: 'CS 2110 · OOP and Data Structures', value: 'CS 2110' },
              { label: 'CS 2112 · OO Design and Data Structures, Honors', value: 'CS 2112' },
            ],
          },
        },
        {
          id: 'c',
          raw: 'ENGRD 2700',
          term: 'SP26',
          code: 'ENGRD 2700',
          title: 'Basic Engineering Probability and Statistics',
          credits: 3,
          issue: {
            kind: 'credit_mismatch',
            message: 'You listed 4 credits. The roster has 3.',
            options: [
              { label: 'Use 3 credits', value: '3' },
              { label: 'My transcript says 4', value: '4' },
            ],
          },
        },
      ],
    }),
  ),
  http.post('/api/onboarding/confirm', () => HttpResponse.json(state())),

  http.get('/api/chat/latest', () => HttpResponse.json(null)),
  http.post('/api/chat', async ({ request }) => {
    const { message } = (await request.json()) as { message: string }
    return sse(scriptFor(message))
  }),
  http.post('/api/study/events', () => new HttpResponse(null, { status: 204 })),
]
