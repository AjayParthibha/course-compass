import type { AuditResult } from '../../api/types'

export function summarizeRequirements(audit: AuditResult) {
  const reqs = audit.requirements
  const count = (status: string) => reqs.filter((r) => r.status === status).length
  const done = count('done')
  const planned = count('planned')
  const attention = count('missing') + count('flagged')
  const openSlots = reqs.reduce((n, r) => n + r.open_slots, 0)

  const details: string[] = []
  if (planned) details.push(`${planned} planned`)
  if (openSlots) details.push(`${openSlots} slot${openSlots === 1 ? '' : 's'} to fill`)
  if (attention) details.push(`${attention} need${attention === 1 ? 's' : ''} attention`)
  return {
    total: reqs.length,
    done,
    planned,
    attention,
    openSlots,
    headline: `${done} of ${reqs.length} requirements done`,
    details,
  }
}
