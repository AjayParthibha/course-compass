import { useSearchParams } from 'react-router'
import { useMe, usePlan, usePlanOps, useUndo } from '../../api/hooks'
import AdvisorPanel from '../advisor/AdvisorPanel'
import DegreeGraph from './DegreeGraph'
import Inspector from './Inspector'
import ProposalView from './ProposalView'
import RequirementBar from './RequirementBar'
import SemesterList from './SemesterList'
import { Button } from '../../ui'
import { termLabel } from '../../ui/terms'
import { usePlanUI } from './store'

const PROGRAM_LABEL: Record<string, string> = {
  'cs-eng': 'Computer Science B.S., College of Engineering',
  'cs-as': 'Computer Science B.A., College of Arts & Sciences',
}

function Legend() {
  const item = (cls: string, label: string) => (
    <span className="flex items-center gap-1.5">
      <span className={`inline-block h-3 w-4 rounded-[3px] ${cls}`} />
      {label}
    </span>
  )
  return (
    <div className="flex flex-wrap gap-4 border-t border-line-soft px-4 py-2.5 text-[12px] text-muted">
      {item('bg-done border border-[#BFC6B8]', 'Completed')}
      {item('bg-white border-[1.5px] border-ink', 'In progress')}
      {item('bg-white border border-line-strong', 'Planned')}
      {item('border-[1.5px] border-dashed border-[#8C9488]', 'Open slot')}
      {item('bg-ink h-0.5! mt-1', 'Prerequisite chain')}
    </div>
  )
}

export default function PlanPage() {
  const [params] = useSearchParams()
  const proposalId = params.get('proposal') ? Number(params.get('proposal')) : null
  const { data: me } = useMe()
  const { data: state, error, isLoading } = usePlan()
  const ops = usePlanOps()
  const undo = useUndo()
  const { selected, select, view, setView, highlightReq } = usePlanUI()

  if (isLoading) return <div className="p-10 text-muted">Loading your plan…</div>
  if (error || !state) return <div className="p-10 text-accent">Couldn’t load your plan: {error?.message}</div>

  const highlight = highlightReq
    ? new Set(
        state.audit.requirements
          .filter((r) => r.id === highlightReq)
          .flatMap((r) => [...r.filled, ...r.children.flatMap((c) => c.filled)]),
      )
    : null
  const problems = state.violations.filter((v) => v.blocking)

  return (
    <div className="mx-auto flex max-w-[1680px] flex-wrap items-start gap-5 px-5 py-6">
      <div className="flex min-w-0 flex-[999_1_700px] flex-col gap-4">
        {proposalId ? (
          <ProposalView id={proposalId} current={state} />
        ) : (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h1 className="m-0 text-[28px] leading-tight font-extrabold tracking-tight">Your degree plan</h1>
                <p className="m-0 text-muted">
                  {PROGRAM_LABEL[me?.program ?? ''] ?? me?.program}. Graduating {me?.graduation_term ? termLabel(me.graduation_term, true) : ''}.
                </p>
              </div>
              <div className="flex rounded-md border border-line bg-white p-0.5" role="group" aria-label="View">
                {(['graph', 'semesters'] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    aria-pressed={view === v}
                    onClick={() => setView(v)}
                    className={`h-8 rounded border-0 px-3 capitalize ${view === v ? 'bg-ink text-paper' : 'bg-transparent'}`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>

            <RequirementBar audit={state.audit} />

            {(problems.length > 0 || ops.error) && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/40 bg-accent/5 px-4 py-2.5 text-[13px]">
                <div className="flex flex-col gap-0.5">
                  {ops.error && <span className="text-accent">{ops.error.message}</span>}
                  {problems.map((v) => (
                    <span key={v.message}>{v.message}</span>
                  ))}
                </div>
                <Button onClick={() => undo.mutate()}>Undo last change</Button>
              </div>
            )}

            <div className="flex flex-col gap-4">
              <section className="min-w-0 overflow-hidden rounded-xl border border-line bg-white">
                {view === 'graph' ? (
                  <DegreeGraph
                    state={state}
                    selected={selected}
                    highlight={highlight}
                    onSelect={select}
                    onMove={(p, term) => ops.mutate([{ op: 'move', placement_id: p.id, term }])}
                  />
                ) : (
                  <SemesterList state={state} />
                )}
                <Legend />
              </section>
              <aside className="min-w-0 rounded-xl border border-line bg-white">
                <Inspector state={state} />
              </aside>
            </div>
          </>
        )}
      </div>
      <AdvisorPanel />
    </div>
  )
}
