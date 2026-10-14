import { useEffect, useMemo, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useMe, usePlan } from '../../api/hooks'
import AdvisorPanel from '../advisor/AdvisorPanel'
import DegreeGraph from './DegreeGraph'
import EditNotice, { FOCUS_FALLBACK_ID } from './EditNotice'
import Inspector, { INSPECTOR_ID } from './Inspector'
import ProposalView from './ProposalView'
import RequirementBar from './RequirementBar'
import SemesterList from './SemesterList'
import { Button } from '../../ui'
import { Placeholder } from '../../ui/Loading'
import { termLabel } from '../../ui/terms'
import { usePlanEdits } from './edits'
import { usePlanUI } from './store'

const PROGRAM_LABEL: Record<string, string> = {
  'cs-eng': 'Computer Science B.S., College of Engineering',
  'cs-as': 'Computer Science B.A., College of Arts & Sciences',
}

// Matches when the inspector sits beside the graph (Tailwind `xl`).
const SIDE_BY_SIDE = '(min-width: 1280px)'

const scrollBehavior = (): ScrollBehavior =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'

function Legend({ graph }: { graph: boolean }) {
  const item = (cls: string, label: string) => (
    <span className="flex items-center gap-1.5">
      <span aria-hidden="true" className={`inline-block h-3 w-4 rounded-[3px] ${cls}`} />
      {label}
    </span>
  )
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 border-t border-line-soft px-4 py-2.5 text-[12px] text-muted">
      {item('bg-done border border-[#BFC6B8]', 'Completed')}
      {item('bg-white border-[1.5px] border-ink', 'In progress')}
      {item('bg-white border border-line-strong', 'Planned')}
      {item('border-[1.5px] border-dashed border-[#8C9488]', 'Open slot')}
      {graph && item('bg-ink h-0.5! mt-1', 'Prerequisite chain')}
    </div>
  )
}

function PlanSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <p role="status" className="sr-only">Loading your plan…</p>
      <div className="flex flex-col gap-2">
        <Placeholder className="h-8 w-64 max-w-full" />
        <Placeholder className="h-4 w-96 max-w-full" />
      </div>
      <Placeholder className="h-10 md:h-[72px]" />
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
        <Placeholder className="h-[480px] min-w-0 flex-1 rounded-xl" />
        <Placeholder className="h-40 rounded-xl xl:h-[320px] xl:w-[300px]" />
      </div>
    </div>
  )
}

export default function PlanPage() {
  const [params] = useSearchParams()
  const proposalId = params.get('proposal') ? Number(params.get('proposal')) : null
  const { data: me } = useMe()
  const { data: state, error, isLoading } = usePlan()
  const edits = usePlanEdits()
  const { selected, select, view, setView, highlightReq, notice, editError, setEditError, undoneAt } = usePlanUI()
  const inspector = useRef<HTMLElement>(null)
  const lastSelected = useRef(selected)

  const audit = state?.audit
  const highlight = useMemo(
    () =>
      highlightReq && audit
        ? new Set(
            audit.requirements
              .filter((r) => r.id === highlightReq)
              .flatMap((r) => [...r.filled, ...r.children.flatMap((c) => c.filled)]),
          )
        : null,
    [highlightReq, audit],
  )

  // an undo or an applied proposal can take the selected course out of the plan
  const placements = state?.plan.placements
  useEffect(() => {
    if (selected && placements && !placements.some((p) => p.id === selected)) select(null)
  }, [selected, placements, select])

  useEffect(() => () => setEditError(null), [setEditError])

  // When the inspector sits below the graph, bring it into view for a new selection.
  useEffect(() => {
    if (selected === lastSelected.current) return
    lastSelected.current = selected
    const el = inspector.current
    if (!selected || !el || window.matchMedia(SIDE_BY_SIDE).matches) return
    const { top, bottom } = el.getBoundingClientRect()
    if (top < window.innerHeight - 160 && bottom > 0) return
    el.scrollIntoView({ behavior: scrollBehavior(), block: 'start' })
  }, [selected])

  const jumpToAdvisor = () =>
    document.getElementById('advisor')?.firstElementChild?.scrollIntoView({ behavior: scrollBehavior(), block: 'start' })

  let content
  if (isLoading) {
    content = <PlanSkeleton />
  } else if (error || !state) {
    content = (
      <p role="alert" className="m-0 rounded-lg border border-accent/40 bg-accent/5 px-4 py-3 text-accent">
        Couldn’t load your plan{error?.message ? `: ${error.message}` : '.'}
      </p>
    )
  } else if (proposalId) {
    content = <ProposalView id={proposalId} current={state} />
  } else {
    const problems = state.violations.filter((v) => v.blocking)
    // right after an undo, "Undo last change" would step further back, not undo something new
    const canUndo = !notice?.undoable && undoneAt !== state.plan.version

    content = (
      <>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="m-0 text-[26px] leading-tight font-extrabold tracking-tight sm:text-[28px]">Your degree plan</h1>
            <p className="m-0 text-muted">
              {PROGRAM_LABEL[me?.program ?? ''] ?? me?.program}. Graduating {me?.graduation_term ? termLabel(me.graduation_term, true) : ''}.{' '}
              <Link to="/profile#plan-settings" className="text-[13px] font-semibold whitespace-nowrap text-ink underline underline-offset-3">
                Plan settings
              </Link>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button className="h-8! px-2.5! text-[13px] min-[1120px]:hidden" onClick={jumpToAdvisor}>
              Jump to advisor
            </Button>
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
        </div>

        <RequirementBar audit={state.audit} problems={problems.length} />

        {editError && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/40 bg-accent/5 px-4 py-2.5 text-[13px]">
            <span className="text-accent">Couldn’t make that change: {editError}</span>
            <Button className="h-8! text-[13px]" onClick={() => setEditError(null)}>
              Dismiss
            </Button>
          </div>
        )}

        {problems.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/40 bg-accent/5 px-4 py-2.5 text-[13px]">
            <div className="flex flex-col gap-0.5">
              {problems.map((v) => (
                <span key={v.message}>{v.message}</span>
              ))}
            </div>
            {canUndo && (
              <Button disabled={edits.pending} onClick={edits.undo}>
                Undo last change
              </Button>
            )}
          </div>
        )}

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
          <section
            id={FOCUS_FALLBACK_ID}
            tabIndex={-1}
            aria-label={view === 'graph' ? 'Degree graph' : 'Semesters'}
            className="min-w-0 flex-1 overflow-hidden rounded-xl border border-line bg-white"
          >
            {view === 'graph' ? (
              <DegreeGraph
                state={state}
                selected={selected}
                highlight={highlight}
                onSelect={select}
                onMove={edits.move}
              />
            ) : (
              <SemesterList state={state} />
            )}
            <Legend graph={view === 'graph'} />
          </section>
          <aside
            ref={inspector}
            id={INSPECTOR_ID}
            tabIndex={-1}
            aria-label="Course details"
            className="min-w-0 scroll-mt-4 rounded-xl border border-line bg-white xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:w-[300px] xl:shrink-0 xl:overflow-y-auto"
          >
            <Inspector state={state} />
          </aside>
        </div>
      </>
    )
  }

  return (
    <main className="mx-auto flex max-w-[1680px] flex-wrap items-start gap-5 px-4 py-5 sm:px-5 sm:py-6">
      <div className="flex min-w-0 flex-[999_1_700px] flex-col gap-4">{content}</div>
      {/* display: contents keeps the panel a direct flex child so its sticky positioning still works */}
      <div id="advisor" className="contents">
        <AdvisorPanel />
      </div>
      <EditNotice />
    </main>
  )
}
