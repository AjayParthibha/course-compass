// Sample student from the design mockups ("Sam"). Used when running with
// VITE_MOCK=1 so the UI works without the backend or an API key.
import type {
  Candidate,
  Course,
  Placement,
  PlanState,
  ProfileFact,
  Proposal,
  RequirementStatus,
  SlotCandidates,
  Student,
} from '../api/types'

export const TERMS = ['FA24', 'SP25', 'FA25', 'SP26', 'FA26', 'SP27', 'FA27', 'SP28']
const CURRENT = 'FA26'

// code, title, credits, term, requirement, typically offered
type Row = [string, string, number, string, string, string]
const ROWS: Row[] = [
  ['CS 1110', 'Intro to Computing', 4, 'FA24', 'intro', 'Fall, spring, summer'],
  ['MATH 1910', 'Calculus for Engineers', 4, 'FA24', 'math', 'Fall, spring'],
  ['CHEM 2090', 'Engineering General Chemistry', 4, 'FA24', 'eng-chem', 'Fall, spring'],
  ['ENGL 1170', 'First-year writing seminar', 3, 'FA24', 'fws', 'Every term'],
  ['CS 2110', 'OOP and Data Structures', 4, 'SP25', 'intro', 'Fall, spring, summer'],
  ['MATH 1920', 'Multivariable Calculus', 4, 'SP25', 'math', 'Fall, spring'],
  ['PHYS 1112', 'Mechanics', 4, 'SP25', 'eng-physics', 'Fall, spring'],
  ['HIST 1200', 'First-year writing seminar', 3, 'SP25', 'fws', 'Every term'],
  ['CS 2800', 'Math Foundations of Computing', 4, 'FA25', 'core', 'Fall, spring'],
  ['MATH 2940', 'Linear Algebra for Engineers', 4, 'FA25', 'math', 'Fall, spring'],
  ['PHYS 2213', 'Electromagnetism', 4, 'FA25', 'eng-physics', 'Fall, spring'],
  ['ECON 1110', 'Intro Microeconomics', 3, 'FA25', 'ls', 'Fall, spring'],
  ['CS 3110', 'Functional Programming', 4, 'SP26', 'core', 'Fall, spring'],
  ['CS 3410', 'Computer System Organization', 4, 'SP26', 'core', 'Fall, spring'],
  ['ENGRD 2700', 'Engineering Probability', 3, 'SP26', 'probability', 'Fall, spring'],
  ['PSYCH 1101', 'Intro Psychology', 3, 'SP26', 'ls', 'Fall'],
  ['CS 4820', 'Analysis of Algorithms', 4, 'FA26', 'core', 'Fall, spring'],
  ['CS 3780', 'Intro to Machine Learning', 4, 'FA26', 'core', 'Fall, spring'],
  ['ORIE 3300', 'Optimization I', 4, 'FA26', 'ext', 'Fall'],
  ['GOVT 1111', 'Intro American Government', 3, 'FA26', 'ls', 'Fall, spring'],
  ['CS 4740', 'Natural Language Processing', 4, 'SP27', 'e4000', 'Fall, spring'],
  ['CS 4410', 'Operating Systems', 4, 'SP27', 'core', 'Fall, spring'],
  ['CS 4320', 'Database Systems', 3, 'SP27', 'tech', 'Fall, spring'],
  ['ORIE 3500', 'Probability and Statistics II', 4, 'SP27', 'ext', 'Spring'],
  ['', 'Liberal studies', 3, 'SP27', 'ls', ''],
  ['CS 4701', 'Practicum in AI', 3, 'FA27', 'practicum', 'Fall, spring'],
  ['CS 4780', 'ML for Intelligent Systems', 4, 'FA27', 'e4000', 'Fall, spring'],
  ['ORIE 4741', 'Learning with Big Messy Data', 4, 'FA27', 'ext', 'Fall'],
  ['', 'Liberal studies', 3, 'FA27', 'ls', ''],
  ['CS 5150', 'Software Engineering', 4, 'SP28', 'aae', 'Fall, spring'],
  ['', 'Technical elective', 3, 'SP28', 'tech', ''],
  ['', 'Liberal studies', 3, 'SP28', 'ls', ''],
]

const EDGES: [string, string][] = [
  ['CS 1110', 'CS 2110'], ['CS 1110', 'CS 2800'], ['MATH 1910', 'MATH 1920'], ['MATH 1920', 'MATH 2940'],
  ['CS 2110', 'CS 3110'], ['CS 2800', 'CS 3110'], ['CS 2110', 'CS 3410'], ['CS 2800', 'CS 4820'],
  ['CS 3110', 'CS 4820'], ['CS 2110', 'CS 3780'], ['MATH 2940', 'CS 3780'], ['ENGRD 2700', 'CS 3780'],
  ['MATH 2940', 'ORIE 3300'], ['CS 3410', 'CS 4410'], ['CS 3780', 'CS 4740'], ['CS 2110', 'CS 4320'],
  ['ENGRD 2700', 'ORIE 3500'], ['CS 3780', 'CS 4780'], ['CS 3780', 'CS 4701'], ['ORIE 3300', 'ORIE 4741'],
  ['CS 3110', 'CS 5150'],
]

const REQ_LABELS: [string, string, number][] = [
  ['intro', 'Intro computing', 2],
  ['math', 'Math', 3],
  ['core', 'CS core', 6],
  ['probability', 'Probability', 1],
  ['e4000', '4000+ electives', 2],
  ['practicum', 'Practicum', 1],
  ['tech', 'Technical electives', 2],
  ['ext', 'External spec.', 3],
  ['aae', 'Advisor-approved', 1],
  ['eng-physics', 'Physics', 2],
  ['eng-chem', 'Chemistry', 1],
  ['fws', 'Writing seminars', 2],
  ['ls', 'Liberal studies', 6],
]

function statusFor(term: string) {
  const i = TERMS.indexOf(term)
  const now = TERMS.indexOf(CURRENT)
  return i < now ? 'completed' : i === now ? 'in_progress' : 'planned'
}

export const placements: Placement[] = ROWS.map(([code, title, credits, term, req], i) => ({
  id: code ? code.replace(' ', '').toLowerCase() : `slot-${req}-${i}`,
  term,
  course: code || null,
  title: code ? title : null,
  slot: code ? null : req,
  slot_label: code ? null : title,
  credits,
  status: statusFor(term) as Placement['status'],
  locked: false,
  origin: 'import',
}))

export const titles: Record<string, string> = Object.fromEntries(
  ROWS.filter((r) => r[0]).map((r) => [r[0], r[1]]),
)

const reqOf: Record<string, string> = Object.fromEntries(ROWS.map((r, i) => [placements[i].id, r[4]]))

export function auditFor(ps: Placement[]): PlanState['audit'] {
  const requirements: RequirementStatus[] = REQ_LABELS.map(([id, label, needed]) => {
    const filled = ps.filter((p) => reqOf[p.id] === id || p.slot === id)
    const enough = filled.length >= needed
    const done = enough && filled.slice(0, needed).every((p) => p.status === 'completed')
    const chosen = filled.filter((p) => p.course).length
    return {
      id,
      label,
      needed,
      filled: filled.map((p) => p.id),
      open_slots: Math.max(0, Math.min(filled.length, needed) - Math.min(chosen, needed)),
      status: id === 'aae' ? 'flagged' : done ? 'done' : enough ? 'planned' : 'missing',
      children: [],
    }
  })
  return {
    complete: requirements.every((r) => r.status !== 'missing'),
    requirements,
    unassigned: [],
  }
}

const idOf = (code: string) => code.replace(' ', '').toLowerCase()

export function planState(ps: Placement[] = placements, version = 4): PlanState {
  const ids = new Set(ps.map((p) => p.id))
  return {
    plan: {
      id: 1,
      name: 'Plan A',
      version,
      program: 'cs-eng',
      terms: TERMS,
      current_term: CURRENT,
      placements: ps,
    },
    audit: auditFor(ps),
    violations: [],
    edges: EDGES.map(([a, b]) => ({ source: idOf(a), target: idOf(b) })).filter(
      (e) => ids.has(e.source) && ids.has(e.target),
    ),
  }
}

export const student: Student = {
  id: 1,
  code: 'DEMO-SAM',
  program: 'cs-eng',
  catalog_year: '2024-25',
  entering_term: 'FA24',
  graduation_term: 'SP28',
  max_credits: 18,
  term_caps: {},
  memory_enabled: true,
  onboarded: true,
}

export function courseDetail(code: string): Course {
  const row = ROWS.find((r) => r[0] === code)
  const [subject, number] = code.split(' ')
  const prereqs = EDGES.filter(([, b]) => b === code).map(([a]) => a)
  return {
    code,
    subject,
    number,
    title: row?.[1] ?? code,
    description: `${row?.[1] ?? code}. (Sample data.)`,
    credits_min: row?.[2] ?? 3,
    credits_max: row?.[2] ?? 3,
    attributes: [],
    cross_listed: [],
    terms_offered: ['FA24', 'SP25', 'FA25', 'SP26', 'FA26'],
    typical_seasons: row?.[5] === 'Fall' ? ['FA'] : row?.[5] === 'Spring' ? ['SP'] : ['FA', 'SP'],
    instructors: [],
    prereq_text: prereqs.join(' and '),
    coreq_text: '',
    prereqs:
      prereqs.length === 0
        ? null
        : { kind: 'all', items: prereqs.map((c) => ({ kind: 'course', code: c, concurrent: false })) },
    prereqs_reviewed: true,
  }
}

const day = (d: string) => `2026-${d}T12:00:00Z`

export const facts: ProfileFact[] = [
  { id: 1, dimension: 'career_track', value: 'ml-eng', text: 'Wants an ML engineering job after graduating', status: 'stated', confidence: 1, evidence: null, created_at: day('09-12'), updated_at: day('09-12'), last_confirmed_at: day('09-12') },
  { id: 2, dimension: 'max_heavy_per_term', value: '2', text: 'At most two heavy courses in a term', status: 'stated', confidence: 1, evidence: null, created_at: day('09-12'), updated_at: day('09-12'), last_confirmed_at: day('09-12') },
  { id: 3, dimension: 'note', value: 'core-early', text: 'Wants CS core finished before senior year', status: 'stated', confidence: 1, evidence: null, created_at: day('09-20'), updated_at: day('09-20'), last_confirmed_at: day('09-20') },
  { id: 4, dimension: 'interest', value: 'nlp', text: 'Curious about NLP', status: 'stated', confidence: 1, evidence: null, created_at: day('10-02'), updated_at: day('10-02'), last_confirmed_at: day('10-02') },
  { id: 5, dimension: 'grad_school', value: 'no', text: 'Not planning on grad school', status: 'conflict', confidence: 1, evidence: '“I’m not planning on grad school.”', created_at: day('09-12'), updated_at: day('10-02'), last_confirmed_at: day('09-12') },
  { id: 6, dimension: 'grad_school', value: 'meng', text: 'Asked about fitting the CS MEng in right after graduating', status: 'conflict', confidence: 1, evidence: '“Could I fit the CS MEng in right after graduating?”', created_at: day('10-02'), updated_at: day('10-02'), last_confirmed_at: day('10-02') },
  { id: 7, dimension: 'work_style', value: 'projects', text: 'Enjoys project-heavy courses more than problem sets', status: 'inferred', confidence: 0.5, evidence: 'From how you talked about CS 3110 and CS 4820', created_at: day('10-01'), updated_at: day('10-01'), last_confirmed_at: null },
  { id: 8, dimension: 'ls_goal', value: '', text: 'What you want from liberal studies courses', status: 'open', confidence: 0, evidence: 'You asked me to hold off on Oct 3', created_at: day('10-03'), updated_at: day('10-03'), last_confirmed_at: null },
]

export function lighterSpringProposal(base: number): Proposal {
  return {
    id: 101,
    plan_id: 1,
    base_version: base,
    summary: 'Spring ’27 goes from 18 to 14 credits. Two courses move, nothing else changes, and you still graduate May 2028.',
    ops: [
      { op: 'move', placement_id: 'cs4740', term: 'FA27' },
      { op: 'move', placement_id: 'cs4780', term: 'SP28' },
    ],
    changes: [
      { course: 'CS 4740', from_term: 'SP27', to_term: 'FA27', reason: 'Frees 4 credits in spring. Its only prerequisite in your plan, CS 3780, finishes this fall.' },
      { course: 'CS 4780', from_term: 'FA27', to_term: 'SP28', reason: 'Makes room for CS 4740 so fall stays at 14 credits.' },
    ],
    rejected: [
      { title: 'Move CS 4410.', reason: 'It’s your last core course and you told me you want core done before senior year.' },
      { title: 'Drop ORIE 3500.', reason: 'Your external specialization would end up one course short.' },
      { title: 'Start over.', reason: 'A fresh plan also works, but it moves 7 courses instead of 2.' },
    ],
    checks: [
      'Every prerequisite still comes before the course that needs it',
      'No remaining term goes above 14 credits',
      'Requirement progress is identical to before',
    ],
    violations: [],
    status: 'pending',
    created_at: day('10-04'),
  }
}

const candidate = (
  rank: number,
  code: string,
  title: string,
  reasons: Candidate['reasons'],
  offering: string,
  reviews: Candidate['reviews'],
): Candidate => ({
  course: { code, title, credits: 4 },
  rank,
  reasons,
  official: {
    prereqs_met: true,
    prereq_note: 'Prerequisites met by CS 3780 (Fall ’26)',
    offering_note: offering,
    assumed: true,
  },
  reviews,
})

export function candidates(slot: string, term: string): SlotCandidates {
  return {
    slot_id: slot,
    slot_label: 'Technical elective',
    term,
    eligible_count: 63,
    candidates: [
      candidate(
        1,
        'CS 4782',
        'Introduction to Deep Learning',
        [
          { text: 'Closest match to wanting an ML engineering job after graduation', basis: 'stated', fact_id: 1, date: 'Sep 12' },
          { text: 'Builds on CS 3780 and CS 4780, both already in your plan', basis: 'plan', fact_id: null, date: null },
          { text: 'Project-heavy, which you seem to enjoy', basis: 'inference', fact_id: 7, date: null },
        ],
        'Offered the last 4 fall and spring terms',
        { overall: 4.3, difficulty: 3.6, workload: 3.9, count: 27, url: 'https://www.cureviews.org/' },
      ),
      candidate(
        2,
        'CS 4787',
        'Principles of Large-Scale Machine Learning',
        [
          { text: 'Systems side of ML, which ties your CS 4410 and CS 4780 together', basis: 'plan', fact_id: null, date: null },
          { text: 'More problem sets than projects, so it ranks below #1 for now', basis: 'inference', fact_id: 7, date: null },
        ],
        'Usually fall and spring',
        { overall: 4.0, difficulty: 4.1, workload: 4.0, count: 19, url: 'https://www.cureviews.org/' },
      ),
      candidate(
        3,
        'CS 4744',
        'Computational Linguistics',
        [{ text: 'Pairs with CS 4740 if NLP turns into a real interest', basis: 'stated', fact_id: 4, date: 'Oct 2' }],
        'Offered spring only, last 3 years',
        null,
      ),
    ],
    factors: [
      { label: 'Career: ML engineering', strength: 'strong', basis: 'You said · Sep 12' },
      { label: 'At most 2 heavy courses a term', strength: 'strong', basis: 'You said · Sep 12' },
      { label: 'Likes project-heavy courses', strength: 'medium', basis: 'My guess from 2 conversations' },
      { label: 'Instructor ratings', strength: 'not used', basis: 'Spring ’28 instructors aren’t announced' },
    ],
  }
}
