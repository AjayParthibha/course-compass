import type { components } from './schema'

type S = components['schemas']

export type Student = S['Student']
export type Plan = S['Plan']
export type PlanState = S['PlanState']
export type Placement = S['Placement']
export type PlanEdge = S['PlanEdge']
export type Violation = S['Violation']
export type AuditResult = S['AuditResult']
export type RequirementStatus = S['RequirementStatus']
export type Course = S['Course']
export type Proposal = S['Proposal']
export type ProfileFact = S['ProfileFact']
export type Profile = S['Profile']
export type ParsedCourse = S['ParsedCourse']
export type ParseResult = S['ParseResult']
export type SlotCandidates = S['SlotCandidates']
export type Candidate = S['Candidate']
export type SlotAreas = S['SlotAreas']
export type Area = S['Area']
export type BlockedCourse = S['BlockedCourse']
export type Conversation = S['Conversation']
export type ChatMessage = S['ChatMessage']

export type PlanSettingsUpdate = S['PlanSettingsUpdate']

export type PlanOp =
  | S['AddOp-Input']
  | S['RemoveOp-Input']
  | S['MoveOp-Input']
  | S['ReplaceOp-Input']
  | S['LockOp-Input']

export type AdvisorEvent =
  | S['TextEvent']
  | S['ToolStartEvent']
  | S['ToolEndEvent']
  | S['QuestionEvent']
  | S['ProposalEvent']
  | S['ProfileUpdateEvent']
  | S['DoneEvent']
  | S['ErrorEvent']
