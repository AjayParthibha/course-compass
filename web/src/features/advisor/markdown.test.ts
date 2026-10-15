import { describe, expect, it } from 'vitest'
import { misleadingLinkHost, parseInline, parseMarkdown, type Inline } from './markdown'

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

  it('keeps balanced parentheses in bare urls', () => {
    expect(parseInline('(https://a.com/x_(y))')).toEqual([
      t('('),
      { type: 'link', href: 'https://a.com/x_(y)', children: [t('https://a.com/x_(y)')] },
      t(')'),
    ])
  })

  it('nests emphasis of the same kind', () => {
    expect(parseInline('*a *b* c*')).toEqual([
      { type: 'em', children: [t('a '), { type: 'em', children: [t('b')] }, t(' c')] },
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

  it('only lets a list starting at 1 interrupt a paragraph', () => {
    expect(parseMarkdown('In\n2026. was a year').map((b) => b.type)).toEqual(['paragraph'])
    expect(parseMarkdown('Steps:\n1. a\n2. b').map((b) => b.type)).toEqual(['paragraph', 'list'])
    expect(parseMarkdown('2026. That year').map((b) => b.type)).toEqual(['list'])
  })

  it('starts a new list when numbers and bullets switch', () => {
    const blocks = parseMarkdown('1. a\n2. b\n- c\n- d')
    expect(blocks.map((b) => b.type === 'list' && b.ordered)).toEqual([true, false])
  })

  it('keeps a less-indented item in the sublist it continues', () => {
    const [list] = parseMarkdown('- a\n    - b\n  - c')
    expect(list.type === 'list' && list.items[0].lists).toEqual([
      {
        type: 'list',
        ordered: false,
        start: 1,
        items: [
          { children: [t('b')], lists: [] },
          { children: [t('c')], lists: [] },
        ],
      },
    ])
  })

  it('strips a heading’s closing hashes but keeps C#', () => {
    expect(parseMarkdown('## Plan ##')).toEqual([{ type: 'heading', children: [t('Plan')] }])
    expect(parseMarkdown('# Learn C#')).toEqual([{ type: 'heading', children: [t('Learn C#')] }])
  })

  it('never throws on partial input', () => {
    const src = '## Plan\n1. **Spring** → `CS 3110` [roster](https://classes.cornell.edu) *done*\n   - nested _x_'
    for (let i = 0; i <= src.length; i++) {
      expect(() => parseMarkdown(src.slice(0, i), { streaming: true })).not.toThrow()
    }
  })
})

describe('misleadingLinkHost', () => {
  it('names the real host when the label looks like another address', () => {
    expect(misleadingLinkHost('classes.cornell.edu', 'https://evil.example/login')).toBe('evil.example')
    expect(misleadingLinkHost('https://cornell.edu/cs', 'https://evil.example/')).toBe('evil.example')
    expect(misleadingLinkHost('cornеll.edu', 'https://cornell.edu/')).toBe('cornell.edu')
  })

  it('stays quiet for matching hosts and ordinary labels', () => {
    expect(misleadingLinkHost('cornell.edu', 'https://www.cornell.edu/about')).toBeNull()
    expect(misleadingLinkHost('https://classes.cornell.edu', 'https://classes.cornell.edu/browse')).toBeNull()
    expect(misleadingLinkHost('Class roster', 'https://evil.example/')).toBeNull()
    expect(misleadingLinkHost('CS 2110', 'https://www.cureviews.org/course/CS/2110')).toBeNull()
  })
})

describe('parser cost', () => {
  const N = 50_000
  const rep = (s: string) => s.repeat(Math.ceil(N / s.length)).slice(0, N)
  const inputs = {
    'open asterisks': rep('*a '),
    'open strong': rep('**a '),
    'open underscores': rep(' _a'),
    brackets: '['.repeat(N),
    'nested emphasis': '*a '.repeat(N / 6) + 'a* '.repeat(N / 6),
    'mixed delimiters': rep('*a _'),
    'backtick runs': rep('`` ` '),
    'heading spaces': '# a' + ' '.repeat(N) + 'b',
    'blank lines': rep('- a\n\n'),
  }

  it.each(Object.entries(inputs))('parses 50k chars of %s quickly', (_, src) => {
    for (const streaming of [false, true]) {
      const start = performance.now()
      parseMarkdown(src, { streaming })
      expect(performance.now() - start).toBeLessThan(500)
    }
  })

  it('handles a long reply that is still streaming without overflowing the stack', () => {
    const src = '*a '.repeat(20_000)
    expect(() => parseMarkdown(src, { streaming: true })).not.toThrow()
    const depth = (nodes: Inline[]): number =>
      Math.max(0, ...nodes.map((n) => ('children' in n ? 1 + depth(n.children) : 0)))
    const [block] = parseMarkdown(src, { streaming: true })
    expect(block.type === 'paragraph' && depth(block.children)).toBeLessThanOrEqual(5)
  })
})
