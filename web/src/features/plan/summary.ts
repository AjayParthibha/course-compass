import type { AuditResult } from '../../api/types'

/**
 * The overview above the plan. Done and planned requirements are on track; missing ones
 * need a course, and flagged ones only need someone to confirm them, so they're apart.
 */
export function summarizeRequirements(audit: AuditResult, problems = 0) {
  const reqs = audit.requirements
  const count = (status: string) => reqs.filter((r) => r.status === status).length
  const done = count('done')
  const planned = count('planned')
  const toConfirm = count('flagged')
  const missing = count('missing')
  const openSlots = reqs.reduce((n, r) => n + r.open_slots, 0)

  const details: string[] = []
  if (done) details.push(`${done} met`)
  if (planned) details.push(`${planned} planned`)
  if (openSlots) details.push(`${openSlots} slot${openSlots === 1 ? '' : 's'} to fill`)
  if (toConfirm) details.push(`${toConfirm} to confirm`)
  if (problems) details.push(`${problems} plan problem${problems === 1 ? '' : 's'}`)
  return {
    total: reqs.length,
    done,
    planned,
    toConfirm,
    missing,
    openSlots,
    headline:
      done + planned === reqs.length
        ? 'All requirements on track'
        : `${done + planned} of ${reqs.length} requirements on track`,
    details,
  }
}
