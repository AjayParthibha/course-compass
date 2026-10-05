import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'link'

const buttonStyles: Record<ButtonVariant, string> = {
  primary: 'bg-ink text-paper font-semibold border border-ink',
  secondary: 'bg-white text-ink border border-[#C3C9BC]',
  quiet: 'bg-transparent text-ink border border-transparent hover:bg-chip',
  link: 'bg-transparent text-ink underline underline-offset-3 font-semibold px-1!',
}

export function Button({
  variant = 'secondary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      type="button"
      className={`inline-flex h-9 items-center justify-center gap-2 rounded-md px-3.5 whitespace-nowrap disabled:opacity-50 ${buttonStyles[variant]} ${className}`}
      {...props}
    />
  )
}

export function Logo() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10.25" stroke="#A8232B" strokeWidth="1.5" />
      <path d="M12 4.5 L14.2 12 L12 19.5 L9.8 12 Z" fill="#A8232B" />
      <circle cx="12" cy="12" r="1.4" fill="#FAFAF7" />
    </svg>
  )
}

export function SectionLabel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <h2 className={`m-0 text-[11px] font-bold tracking-[0.08em] text-muted uppercase ${className}`}>
      {children}
    </h2>
  )
}

type TagKind = 'said' | 'plan' | 'guess' | 'open' | 'neutral'

const tagStyles: Record<TagKind, string> = {
  said: 'bg-ink text-paper',
  plan: 'bg-chip text-ink',
  guess: 'border border-dashed border-muted text-muted',
  open: 'bg-highlight text-ink',
  neutral: 'bg-chip text-ink-soft',
}

export function Tag({ kind, children }: { kind: TagKind; children: ReactNode }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11.5px] font-semibold whitespace-nowrap ${tagStyles[kind]}`}>
      {children}
    </span>
  )
}
