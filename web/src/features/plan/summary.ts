import type { AuditResult } from '../../api/types'

/**
 * One-line overview for small screens. Missing requirements and blocking problems need
 * attention; flagged ones only need someone to confirm them, so they're counted apart.
 */
export function summarizeRequirements(audit: AuditResult, problems = 0) {
  const reqs = audit.requirements
  const count = (status: string) => reqs.filter((r) => r.status === status).length
  const done = count('done')
  const planned = count('planned')
  const toConfirm = count('flagged')
  const attention = count('missing') + problems
  const openSlots = reqs.reduce((n, r) => n + r.open_slots, 0)

  const details: string[] = []
  if (planned) details.push(`${planned} planned`)
  if (openSlots) details.push(`${openSlots} slot${openSlots === 1 ? '' : 's'} to fill`)
  if (toConfirm) details.push(`${toConfirm} to confirm`)
  if (attention) details.push(`${attention} need${attention === 1 ? 's' : ''} attention`)
  return {
    total: reqs.length,
    done,
    planned,
    toConfirm,
    attention,
    openSlots,
    headline: `${done} of ${reqs.length} requirements done`,
    details,
  }
}
