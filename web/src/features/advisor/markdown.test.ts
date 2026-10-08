import { describe, expect, it } from 'vitest'
import { parseInline, parseMarkdown } from './markdown'

const t = (text: string) => ({ type: 'text', text })

describe('parseInline', () => {
  it('reads bold, italic and code', () => {
    expect(parseInline('Spring ’27: **15 → 12 credits**, *lighter*, `CS 3110`')).toEqual([
      t('Spring ’27: '),
      { type: 'strong', children: [t('15 → 12 credits')] },
      t(', '),
      { type: 'em', children: [t('lighter')] },
      t(', '),
      { type: 'code', text: 'CS 3110' },
    ])
  })

  it('nests emphasis', () => {
    expect(parseInline('**a *b* c**')).toEqual([
      { type: 'strong', children: [t('a '), { type: 'em', children: [t('b')] }, t(' c')] },
    ])
    expect(parseInline('***both***')).toEqual([{ type: 'strong', children: [{ type: 'em', children: [t('both')] }] }])
  })

  it('leaves stray and spaced asterisks and snake_case alone', () => {
    expect(parseInline('3 * 4 = 12')).toEqual([t('3 * 4 = 12')])
    expect(parseInline('an **unclosed tag')).toEqual([t('an **unclosed tag')])
    expect(parseInline('max_credits_per_term')).toEqual([t('max_credits_per_term')])
    expect(parseInline('_fine_ and __bold__')).toEqual([
      { type: 'em', children: [t('fine')] },
      t(' and '),
      { type: 'strong', children: [t('bold')] },
    ])
  })

  it('honours backslash escapes and ignores markers inside code', () => {
    expect(parseInline('\\*not italic\\*')).toEqual([t('*not italic*')])
    expect(parseInline('`a*b*c`')).toEqual([{ type: 'code', text: 'a*b*c' }])
  })

  it('turns single newlines into line breaks', () => {
    expect(parseInline('one\ntwo')).toEqual([t('one'), { type: 'br' }, t('two')])
  })

  it('only links http and https urls', () => {
    expect(parseInline('[Class roster](https://classes.cornell.edu/browse)')).toEqual([
      { type: 'link', href: 'https://classes.cornell.edu/browse', children: [t('Class roster')] },
    ])
    expect(parseInline('[click](javascript:alert(1))')).toEqual([t('click')])
    expect(parseInline('[wiki](https://en.wikipedia.org/wiki/Go_(game))')).toEqual([
      { type: 'link', href: 'https://en.wikipedia.org/wiki/Go_(game)', children: [t('wiki')] },
    ])
    expect(parseInline('[x](data:text/html,hi)')).toEqual([t('x')])
  })

  it('autolinks bare urls without trailing punctuation', () => {
    expect(parseInline('See https://cornell.edu/cs.')).toEqual([
      t('See '),
      { type: 'link', href: 'https://cornell.edu/cs', children: [t('https://cornell.edu/cs')] },
      t('.'),
    ])
  })

  it('treats an unclosed marker as running to the end while streaming', () => {
    expect(parseInline('Spring: **15 → 1', { streaming: true })).toEqual([
      t('Spring: '),
      { type: 'strong', children: [t('15 → 1')] },
    ])
    expect(parseInline('try `CS 31', { streaming: true })).toEqual([t('try '), { type: 'code', text: 'CS 31' }])
    expect(parseInline('ends with **', { streaming: true })).toEqual([t('ends with **')])
  })
})

describe('parseMarkdown', () => {
  it('splits paragraphs on blank lines', () => {
    expect(parseMarkdown('First.\n\nSecond\nline.')).toEqual([
      { type: 'paragraph', children: [t('First.')] },
      { type: 'paragraph', children: [t('Second'), { type: 'br' }, t('line.')] },
    ])
  })

  it('reads bullet lists right after a paragraph', () => {
    expect(parseMarkdown('Here is the change:\n- Spring ’27: **15 → 12 credits**\n- Fall ’27: 16')).toEqual([
      { type: 'paragraph', children: [t('Here is the change:')] },
      {
        type: 'list',
        ordered: false,
        start: 1,
        items: [
          { children: [t('Spring ’27: '), { type: 'strong', children: [t('15 → 12 credits')] }], lists: [] },
          { children: [t('Fall ’27: 16')], lists: [] },
        ],
      },
    ])
  })

  it('keeps numbered lists together across blank lines and nests indented items', () => {
    const [list] = parseMarkdown('3. Move CS 3110\n   - prereq met\n\n4. Drop PE')
    expect(list).toEqual({
      type: 'list',
      ordered: true,
      start: 3,
      items: [
        {
          children: [t('Move CS 3110')],
          lists: [{ type: 'list', ordered: false, start: 1, items: [{ children: [t('prereq met')], lists: [] }] }],
        },
        { children: [t('Drop PE')], lists: [] },
      ],
    })
  })

  it('ends a list at a blank line followed by a paragraph', () => {
    const blocks = parseMarkdown('- one\n\nAfter.')
    expect(blocks.map((b) => b.type)).toEqual(['list', 'paragraph'])
  })

  it('shows headings as their own block and drops rules', () => {
    expect(parseMarkdown('## Your plan\n---\nOk')).toEqual([
      { type: 'heading', children: [t('Your plan')] },
      { type: 'paragraph', children: [t('Ok')] },
    ])
  })

  it('only applies streaming leniency to the end of the text', () => {
    const blocks = parseMarkdown('an **open\n\n- a **b', { streaming: true })
    expect(blocks).toEqual([
      { type: 'paragraph', children: [t('an **open')] },
      {
        type: 'list',
        ordered: false,
        start: 1,
        items: [{ children: [t('a '), { type: 'strong', children: [t('b')] }], lists: [] }],
      },
    ])
  })

  it('never throws on partial input', () => {
    const src = '## Plan\n1. **Spring** → `CS 3110` [roster](https://classes.cornell.edu) *done*\n   - nested _x_'
    for (let i = 0; i <= src.length; i++) {
      expect(() => parseMarkdown(src.slice(0, i), { streaming: true })).not.toThrow()
    }
  })
})
