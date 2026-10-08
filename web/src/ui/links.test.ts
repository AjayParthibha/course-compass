import { describe, expect, it } from 'vitest'
import { cureviewsUrl } from './links'

describe('cureviewsUrl', () => {
  it('splits subject and number', () => {
    expect(cureviewsUrl('CS 2110')).toBe('https://www.cureviews.org/course/CS/2110')
    expect(cureviewsUrl('INFO 4320')).toBe('https://www.cureviews.org/course/INFO/4320')
  })

  it('uppercases and tolerates missing space', () => {
    expect(cureviewsUrl('math1910')).toBe('https://www.cureviews.org/course/MATH/1910')
  })

  it('falls back to the home page for odd codes', () => {
    expect(cureviewsUrl('not a course')).toBe('https://www.cureviews.org/')
  })
})
