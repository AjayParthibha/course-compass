export type AcademicYear = { start: number; fall: string | null; spring: string | null; other: string[] }

/** Terms grouped by academic year: Fall '24 and Spring '25 share the 2024–25 row; summer joins the year it ends. */
export function groupByYear(terms: string[]): AcademicYear[] {
  const years = new Map<number, AcademicYear>()
  for (const term of terms) {
    const yy = Number(term.slice(2))
    const fall = term.startsWith('FA')
    const start = fall ? yy : yy - 1
    if (!years.has(start)) years.set(start, { start, fall: null, spring: null, other: [] })
    const year = years.get(start)!
    if (fall) year.fall = term
    else if (term.startsWith('SP')) year.spring = term
    else year.other.push(term)
  }
  return [...years.values()].sort((a, b) => a.start - b.start)
}
