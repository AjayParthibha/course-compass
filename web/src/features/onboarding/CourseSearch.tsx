import { useQuery } from '@tanstack/react-query'
import { useEffect, useId, useState } from 'react'
import { api, unwrap } from '../../api/client'

export type PickedCourse = { code: string; title: string; credits: number }

/** Search the roster by code or title ("CS 2110", "linear algebra") and pick a course. */
export default function CourseSearch({
  label,
  onPick,
  onCancel,
  autoFocus = false,
}: {
  label: string
  onPick: (course: PickedCourse) => void
  onCancel?: () => void
  autoFocus?: boolean
}) {
  const id = useId()
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setQuery(text.trim()), 200)
    return () => clearTimeout(t)
  }, [text])
  const { data, isFetching } = useQuery({
    queryKey: ['course-search', query],
    queryFn: () => unwrap(api.GET('/api/courses', { params: { query: { q: query, limit: 8 } } })),
    enabled: query.length >= 2,
    staleTime: 60_000,
  })
  const results = query.length >= 2 ? (data ?? []) : []

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`${id}-q`} className="sr-only">{label}</label>
        <input
          id={`${id}-q`}
          type="search"
          autoFocus={autoFocus}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && onCancel?.()}
          placeholder="Search by code or title, e.g. CS 2110"
          aria-controls={`${id}-results`}
          className="h-9 w-72 max-w-full rounded-md border border-[#C3C9BC] bg-white px-2.5 text-[14px]"
        />
        {onCancel && (
          <button type="button" onClick={onCancel} className="border-0 bg-transparent p-0 text-[13px] text-muted underline">
            Cancel
          </button>
        )}
      </div>
      <ul id={`${id}-results`} aria-label={`${label}: results`} className="m-0 flex list-none flex-col p-0">
        {results.map((c) => (
          <li key={c.code}>
            <button
              type="button"
              onClick={() =>
                onPick({ code: c.code, title: c.title, credits: Math.round(c.credits_max ?? c.credits_min ?? 0) })
              }
              className="flex w-full items-baseline gap-3 rounded-md border-0 bg-transparent px-2 py-1.5 text-left hover:bg-chip"
            >
              <span className="w-24 shrink-0 font-mono text-[13px] font-semibold">{c.code}</span>
              <span className="min-w-0 flex-1 truncate text-[13.5px]">{c.title}</span>
            </button>
          </li>
        ))}
      </ul>
      {query.length >= 2 && !isFetching && results.length === 0 && (
        <span className="text-[13px] text-muted">No course matches “{query}”.</span>
      )}
    </div>
  )
}
