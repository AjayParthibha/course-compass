import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, auth, unwrap } from '../../api/client'
import { keys } from '../../api/hooks'
import { Button, Logo } from '../../ui'

export default function LoginPage() {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await unwrap(api.POST('/api/auth/login', { body: { code } }))
      auth.set(res.token)
      qc.setQueryData(keys.me, res.student)
      navigate(res.student.onboarded ? '/plan' : '/onboarding')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <div className="flex items-center gap-2">
        <Logo />
        <span className="text-xl font-extrabold tracking-tight">CourseCompass</span>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-3 rounded-xl border border-line bg-white p-5">
        <label htmlFor="code" className="font-semibold">
          Participant code
        </label>
        <input
          id="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="e.g. P-07"
          autoFocus
          className="h-11 rounded-md border border-[#C3C9BC] px-3 font-mono uppercase"
        />
        <p className="m-0 text-[13px] text-muted">
          Use the code you were given. A new code starts a fresh profile.
        </p>
        {error && <p className="m-0 text-[13px] text-accent">{error}</p>}
        <Button variant="primary" type="submit" disabled={busy || code.trim().length < 4} className="h-11">
          Continue
        </Button>
      </form>
    </main>
  )
}
