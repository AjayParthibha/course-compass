import { describe, expect, it } from 'vitest'
import { emptyGoals, goalFacts } from './goals'

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

  it('keeps free text for other plans', () => {
    const [fact] = goalFacts({ ...emptyGoals, after: 'other', afterOther: 'Start a company' })
    expect(fact).toEqual({ dimension: 'career_track', value: 'Start a company', text: 'After graduating: Start a company' })
  })
})
