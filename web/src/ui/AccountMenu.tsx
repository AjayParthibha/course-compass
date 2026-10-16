import { useEffect, useId, useRef, useState } from 'react'
import { useMatch, useNavigate } from 'react-router'
import { initials, termLabel } from './terms'

type Props = {
  code: string
  program?: string | null
  graduation?: string | null
  onSignOut: () => void
}

const item =
  'flex w-full items-center rounded-md border-0 bg-transparent px-2.5 py-2 text-left text-[14px] text-ink no-underline hover:bg-chip focus-visible:bg-chip focus-visible:outline-none!'

/**
 * The avatar opens this menu: who's signed in, their profile and plan settings, and
 * sign-out last. Signing in takes the code, so the menu offers to copy it.
 */
export default function AccountMenu({ code, program, graduation, onSignOut }: Props) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const navigate = useNavigate()
  const onProfile = useMatch('/profile') !== null

  const items = () => Array.from(menu.current?.querySelectorAll<HTMLElement>('[role=menuitem]') ?? [])
  const close = (refocus = true) => {
    setOpen(false)
    if (refocus) button.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    items()[0]?.focus()
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (!menu.current?.contains(t) && !button.current?.contains(t)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 1600)
    return () => clearTimeout(t)
  }, [copied])

  const onKeyDown = (e: React.KeyboardEvent) => {
    const list = items()
    const at = list.indexOf(document.activeElement as HTMLElement)
    const go = (i: number) => list[(i + list.length) % list.length]?.focus()
    if (e.key === 'Escape') close()
    else if (e.key === 'Tab') close(false)
    else if (e.key === 'ArrowDown') go(at + 1)
    else if (e.key === 'ArrowUp') go(at - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(-1)
    else return
    if (e.key !== 'Tab') e.preventDefault()
  }

  const goTo = (to: string) => {
    close(false)
    navigate(to)
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
    } catch {
      // clipboard can be blocked; the code is shown in the menu header to copy by hand
    }
  }

  return (
    <div className="relative shrink-0">
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Account: signed in as ${code}`}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            setOpen(true)
          }
        }}
        className={`h-9 w-9 rounded-full border-0 bg-ink text-[13px] font-bold text-paper ${open || onProfile ? 'ring-2 ring-line-strong ring-offset-2 ring-offset-paper' : ''}`}
      >
        {initials(code)}
      </button>
      {open && (
        <div
          ref={menu}
          id={menuId}
          role="menu"
          aria-label="Account"
          onKeyDown={onKeyDown}
          className="absolute top-[calc(100%+8px)] right-0 z-50 w-64 rounded-xl border border-line bg-white p-1.5 shadow-[0_12px_32px_-12px_rgba(23,27,23,0.35),0_2px_6px_rgba(23,27,23,0.08)] motion-safe:animate-sheet-fade"
        >
          <div className="px-2.5 pt-1.5 pb-2.5">
            <p className="m-0 text-[12px] text-muted">Signed in as</p>
            <p className="m-0 font-mono text-[14px] font-semibold">{code}</p>
            {(program || graduation) && (
              <p className="m-0 mt-0.5 text-[12.5px] text-muted">
                {[program, graduation && `Graduating ${termLabel(graduation, true)}`].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>
          <div className="border-t border-line-soft py-1">
            <button type="button" role="menuitem" tabIndex={-1} className={item} onClick={() => goTo('/profile')}>
              Profile
            </button>
            <button type="button" role="menuitem" tabIndex={-1} className={item} onClick={() => goTo('/profile#plan-settings')}>
              Plan settings
            </button>
            <button type="button" role="menuitem" tabIndex={-1} className={`${item} justify-between`} onClick={copy}>
              Copy sign-in code
              <span aria-live="polite" className="text-[12px] text-muted">
                {copied ? 'Copied' : ''}
              </span>
            </button>
          </div>
          <div className="border-t border-line-soft pt-1">
            <button
              type="button"
              role="menuitem"
              tabIndex={-1}
              className={item}
              onClick={() => {
                close(false)
                onSignOut()
              }}
            >
              Sign out
            </button>
            <p className="m-0 px-2.5 pb-1.5 text-[12px] text-muted">
              You’ll need <span className="font-mono">{code}</span> to sign back in.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
