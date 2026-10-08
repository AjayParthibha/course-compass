/**
 * A small markdown subset for advisor replies: paragraphs, line breaks, headings (shown as bold
 * lines), bullet and numbered lists, **bold**, *italic*, `code` and http(s) links.
 * Produces a plain tree that the renderer turns into React elements; nothing is ever HTML.
 */

export type Inline =
  | { type: 'text'; text: string }
  | { type: 'strong'; children: Inline[] }
  | { type: 'em'; children: Inline[] }
  | { type: 'code'; text: string }
  | { type: 'link'; href: string; children: Inline[] }
  | { type: 'br' }

export type ListItem = { children: Inline[]; lists: ListBlock[] }
export type ListBlock = { type: 'list'; ordered: boolean; start: number; items: ListItem[] }
export type MdBlock = { type: 'paragraph'; children: Inline[] } | { type: 'heading'; children: Inline[] } | ListBlock

type Options = {
  /** Text is still streaming in: an unclosed `**`, `*` or `` ` `` on the last line runs to the end. */
  streaming?: boolean
  inLink?: boolean
}

const LIST_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/
const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/

type RawItem = { indent: number; ordered: boolean; start: number; lines: string[] }

export function parseMarkdown(src: string, opts: Options = {}): MdBlock[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const blocks: MdBlock[] = []
  let para: string[] = []
  let items: RawItem[] = []

  // only the text at the very end can still be mid-stream
  const settled = { ...opts, streaming: false }
  const flushPara = (atEnd = false) => {
    if (para.length) blocks.push({ type: 'paragraph', children: parseInline(para.join('\n'), atEnd ? opts : settled) })
    para = []
  }
  const flushList = (atEnd = false) => {
    if (items.length) blocks.push(buildList(items, atEnd ? opts : settled))
    items = []
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const item = LIST_ITEM.exec(line)
    if (item) {
      flushPara()
      const marker = item[2]
      const ordered = /\d/.test(marker)
      items.push({ indent: item[1].length, ordered, start: ordered ? parseInt(marker, 10) : 1, lines: [item[3]] })
      continue
    }
    if (!line.trim()) {
      flushPara()
      // a blank line between items or before an indented continuation keeps the list going
      const next = lines.slice(i + 1).find((l) => l.trim())
      if (items.length && !(next && (LIST_ITEM.test(next) || /^\s{2,}/.test(next)))) flushList()
      continue
    }
    const heading = HEADING.exec(line)
    if (heading || RULE.test(line)) {
      flushPara()
      flushList()
      const last = i === lines.length - 1
      if (heading?.[1]) blocks.push({ type: 'heading', children: parseInline(heading[1], last ? opts : settled) })
      continue
    }
    if (items.length) {
      items[items.length - 1].lines.push(line.trim())
      continue
    }
    para.push(line)
  }
  flushPara(true)
  flushList(true)
  return blocks
}

function buildList(raw: RawItem[], opts: Options): ListBlock {
  const newList = (r: RawItem): ListBlock => ({ type: 'list', ordered: r.ordered, start: r.start, items: [] })
  const root = newList(raw[0])
  const stack: { indent: number; list: ListBlock }[] = [{ indent: raw[0].indent, list: root }]
  raw.forEach((r, n) => {
    while (stack.length > 1 && r.indent < stack[stack.length - 1].indent) stack.pop()
    let top = stack[stack.length - 1]
    const parent = top.list.items[top.list.items.length - 1]
    if (r.indent > top.indent && parent) {
      const sub = newList(r)
      parent.lists.push(sub)
      top = { indent: r.indent, list: sub }
      stack.push(top)
    }
    const itemOpts = n === raw.length - 1 ? opts : { ...opts, streaming: false }
    top.list.items.push({ children: parseInline(r.lines.join('\n'), itemOpts), lists: [] })
  })
  return root
}

const URL_RE = /^https?:\/\/[^\s<>]*[^\s<>.,;:!?'")\]*_]/i
const ESCAPABLE = /[\\`*_[\]()#+\-.!]/
const isSpace = (c: string | undefined) => c === undefined || /\s/.test(c)
const isWordChar = (c: string | undefined) => c !== undefined && /[\p{L}\p{N}]/u.test(c)

export function safeHref(href: string): string | null {
  try {
    const url = new URL(href)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

export function parseInline(src: string, opts: Options = {}): Inline[] {
  const out: Inline[] = []
  let text = ''
  const pushText = (t: string) => {
    text += t
  }
  const flush = () => {
    if (text) out.push({ type: 'text', text })
    text = ''
  }
  const push = (node: Inline) => {
    flush()
    out.push(node)
  }

  let i = 0
  while (i < src.length) {
    const c = src[i]
    const rest = src.slice(i)

    if (c === '\\' && i + 1 < src.length && ESCAPABLE.test(src[i + 1])) {
      pushText(src[i + 1])
      i += 2
      continue
    }

    if (c === '\n') {
      push({ type: 'br' })
      i++
      continue
    }

    if (c === '`') {
      const run = /^`+/.exec(rest)![0]
      const end = src.indexOf(run, i + run.length)
      if (end !== -1) {
        push({ type: 'code', text: src.slice(i + run.length, end) })
        i = end + run.length
        continue
      }
      if (opts.streaming && run.length === 1 && !src.includes('\n', i)) {
        push({ type: 'code', text: src.slice(i + 1) })
        break
      }
      pushText(run)
      i += run.length
      continue
    }

    if (c === '[' && !opts.inLink) {
      const link = /^\[([^\]\n]*)\]\(\s*((?:[^\s()]|\([^\s()]*\))+)\s*\)/.exec(rest)
      if (link) {
        const href = safeHref(link[2])
        const label = parseInline(link[1], { ...opts, inLink: true })
        if (href) push({ type: 'link', href, children: label.length ? label : [{ type: 'text', text: href }] })
        else {
          flush()
          out.push(...label)
        }
        i += link[0].length
        continue
      }
    }

    if ((c === 'h' || c === 'H') && !opts.inLink && !isWordChar(src[i - 1])) {
      const url = URL_RE.exec(rest)
      if (url) {
        const href = safeHref(url[0])
        if (href) {
          push({ type: 'link', href, children: [{ type: 'text', text: url[0] }] })
          i += url[0].length
          continue
        }
      }
    }

    if (c === '*' || c === '_') {
      const span = emphasis(src, i, opts)
      if (span) {
        flush()
        out.push(span.node)
        i = span.end
        continue
      }
      const run = c === '*' ? /^\*+/.exec(rest)![0] : /^_+/.exec(rest)![0]
      pushText(run)
      i += run.length
      continue
    }

    pushText(c)
    i++
  }
  flush()
  return out
}

/** Try to read `**strong**`, `*em*` (or the `_` forms) starting at `i`. */
function emphasis(src: string, i: number, opts: Options): { node: Inline; end: number } | null {
  const ch = src[i]
  const runLen = /^[*_]+/.exec(src.slice(i))![0].length
  // underscores only count at word boundaries, so snake_case stays as written
  if (ch === '_' && isWordChar(src[i - 1])) return null
  const strong = runLen >= 2
  const delim = strong ? ch + ch : ch
  const open = i + delim.length
  if (isSpace(src[open])) return null

  const close = findCloser(src, open, ch, strong)
  if (close !== -1) {
    const inner = parseInline(src.slice(open, close), opts)
    return { node: { type: strong ? 'strong' : 'em', children: inner }, end: close + delim.length }
  }
  if (opts.streaming && !src.slice(open).includes('\n')) {
    const inner = parseInline(src.slice(open), opts)
    return { node: { type: strong ? 'strong' : 'em', children: inner }, end: src.length }
  }
  return null
}

function findCloser(src: string, from: number, ch: string, strong: boolean): number {
  for (let j = from; j < src.length; j++) {
    const c = src[j]
    if (c === '\\') {
      j++
      continue
    }
    if (c === '`') {
      const run = /^`+/.exec(src.slice(j))![0]
      const end = src.indexOf(run, j + run.length)
      if (end !== -1) j = end + run.length - 1
      continue
    }
    if (c !== ch) continue
    const run = /^[*_]+/.exec(src.slice(j))![0].length
    const closes = j > from && !isSpace(src[j - 1]) && !(ch === '_' && isWordChar(src[j + run]))
    if (strong) {
      // `***x***` closes as `*x*` inside `**…**`
      if (run >= 2 && closes) return j + run - 2
    } else if (run === 1 && closes) {
      return j
    } else if (run >= 3 && closes) {
      return j + run - 1
    }
    j += run - 1
  }
  return -1
}
