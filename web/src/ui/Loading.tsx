import { Logo } from '.'

/** Full-screen placeholder while the session is being checked. */
export function PageLoading({ label = 'Loading CourseCompass…' }: { label?: string }) {
  return (
    <div role="status" aria-busy="true" className="flex min-h-screen items-center justify-center px-4">
      <div className="flex items-center gap-2.5 text-[14px] text-muted motion-safe:animate-pulse">
        <Logo />
        <span>{label}</span>
      </div>
    </div>
  )
}

/** A soft grey block standing in for content that is still loading. */
export function Placeholder({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`rounded-lg bg-chip/70 motion-safe:animate-pulse ${className}`} />
}
