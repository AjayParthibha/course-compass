import { useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet, useNavigate } from 'react-router'
import { auth } from '../api/client'
import { useMe, usePlan } from '../api/hooks'
import { Logo } from '.'
import { initials } from './terms'

const PROGRAM_SHORT: Record<string, string> = { 'cs-eng': 'Eng B.S.', 'cs-as': 'A&S B.A.' }

function PlanStatus() {
  const { data } = usePlan()
  const { data: me } = useMe()
  if (!data || !me) return null
  const blocking = data.violations.filter((v) => v.blocking).length
  const missing = data.audit.requirements.filter((r) => r.status === 'missing').length
  const unplaced = data.plan.placements.filter((p) => p.slot && !p.course).length
  const ok = blocking === 0 && missing === 0
  return (
    <div className="order-last flex basis-full flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] lg:order-none lg:basis-auto lg:rounded-lg lg:border lg:border-line lg:bg-white lg:px-3 lg:py-1.5 lg:text-[13px]">
      <span className="font-semibold">{data.plan.name}</span>
      <span className="hidden text-muted sm:inline">
        {PROGRAM_SHORT[me.program ?? ''] ?? me.program} · {me.catalog_year} rules
      </span>
      <span className={`flex items-center gap-1.5 font-semibold ${ok ? '' : 'text-accent'}`}>
        <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${ok ? 'bg-[#2F7A3E]' : 'bg-accent'}`} />
        {ok ? 'All rules pass' : blocking ? `${blocking} problem${blocking > 1 ? 's' : ''}` : `${missing} requirement${missing > 1 ? 's' : ''} open`}
      </span>
      {unplaced > 0 && <span className="text-muted">· {unplaced} open slots</span>}
    </div>
  )
}

export default function Layout() {
  const { data: me } = useMe()
  const qc = useQueryClient()
  const navigate = useNavigate()

  const signOut = () => {
    auth.clear()
    qc.clear()
    navigate('/login')
  }

  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-2.5 py-2 no-underline sm:px-3 ${isActive ? 'bg-chip font-semibold text-ink' : 'text-muted'}`

  return (
    <div className="min-h-screen">
      <header className="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-paper px-4 py-2 sm:gap-x-7 sm:px-5 sm:py-2.5">
        <NavLink to="/plan" className="flex items-center gap-2 text-ink no-underline">
          <Logo />
          <span className="sr-only text-[17px] font-extrabold tracking-tight sm:not-sr-only">CourseCompass</span>
        </NavLink>
        <nav aria-label="Main" className="flex gap-0.5 sm:gap-1">
          <NavLink to="/plan" className={link}>Plan</NavLink>
          <NavLink to="/explore" className={link}>Explore</NavLink>
          <NavLink to="/profile" className={link}>Profile</NavLink>
        </nav>
        <div className="flex-1" />
        <PlanStatus />
        <button
          type="button"
          onClick={signOut}
          title="Sign out"
          aria-label={`Signed in as ${me?.code ?? ''}. Sign out`}
          className="h-9 w-9 shrink-0 rounded-full border-0 bg-ink text-[13px] font-bold text-paper"
        >
          {initials(me?.code ?? '')}
        </button>
      </header>
      <Outlet />
    </div>
  )
}
