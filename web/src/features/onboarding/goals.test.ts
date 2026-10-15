import { describe, expect, it } from 'vitest'
import { emptyGoals, factsToSupersede, goalFacts, startingChoices } from './goals'

describe('goalFacts', () => {
  it('saves nothing when everything is skipped', () => {
    expect(goalFacts(emptyGoals)).toEqual([])
    expect(goalFacts({ ...emptyGoals, after: 'other', afterOther: '  ' })).toEqual([])
  })

  it('turns answers into profile facts', () => {
    const facts = goalFacts({
      after: 'grad_school',
      afterOther: '',
      interests: ['ml', 'hci'],
      interestOther: 'robotics',
      load: 'light',
    })
    expect(facts.map((f) => [f.dimension, f.value])).toEqual([
      ['grad_school', 'yes'],
      ['interest', 'ml'],
      ['interest', 'hci'],
      ['interest', 'robotics'],
      ['term_load', 'light'],
    ])
    expect(facts[2].text).toBe('Interested in human-computer interaction')
  })

  it('supersedes earlier answers to single-choice questions', () => {
    const existing = [
      { id: 1, dimension: 'term_load', value: 'light', status: 'stated' as const },
      { id: 2, dimension: 'career_track', value: 'industry', status: 'stated' as const },
      { id: 3, dimension: 'interest', value: 'ml', status: 'stated' as const },
      { id: 4, dimension: 'grad_school', value: 'yes', status: 'superseded' as const },
      { id: 5, dimension: 'term_load', value: 'heavy', status: 'inferred' as const },
    ]
    const next = goalFacts({ ...emptyGoals, after: 'grad_school', interests: ['systems'], load: 'heavy' })
    expect(factsToSupersede(existing, next)).toEqual([1, 2])
    expect(factsToSupersede(existing, goalFacts({ ...emptyGoals, interests: ['theory'] }))).toEqual([])
  })

  it('starts onboarding from the saved setup', () => {
    const programs = ['cs-eng', 'cs-as']
    expect(startingChoices(undefined, programs)).toEqual({ program: 'cs-eng', entering: 'FA24', graduating: 'SP28' })
    expect(
      startingChoices({ program: 'cs-as', entering_term: 'SP25', graduation_term: 'FA28' }, programs),
    ).toEqual({ program: 'cs-as', entering: 'SP25', graduating: 'FA28' })
    expect(startingChoices({ program: 'math', entering_term: null, graduation_term: null }, programs).program).toBe('cs-eng')
  })

  it('keeps free text for other plans', () => {
    const [fact] = goalFacts({ ...emptyGoals, after: 'other', afterOther: 'Start a company' })
    expect(fact).toEqual({ dimension: 'career_track', value: 'Start a company', text: 'After graduating: Start a company' })
  })
})
