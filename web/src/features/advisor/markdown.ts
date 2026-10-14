/**
 * A small markdown subset for advisor replies: paragraphs, line breaks, headings (shown as bold
 * lines), bullet and numbered lists, **bold**, *italic*, `code` and http(s) links.
 * Produces a plain tree that the renderer turns into React elements; nothing is ever HTML.
 * Every step is linear in the input (the text is re-parsed on each streamed delta).
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
const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/
const MAX_LIST_DEPTH = 8

type RawItem = { indent: number; ordered: boolean; start: number; lines: string[] }

const isBlank = (line: string) => !line.trim()

function isRule(line: string) {
  if (line.length - line.trimStart().length > 3) return false
  const body = line.replace(/\s+/g, '')
  return body.length >= 3 && /^(?:-+|\*+|_+)$/.test(body)
}

function headingText(line: string): string | null {
  const m = HEADING.exec(line)
  if (!m) return null
  let text = m[1].trimEnd()
  // an optional closing run of #s, but only when it stands apart ("C#" keeps its #)
  let end = text.length
  while (end > 0 && text[end - 1] === '#') end--
  if (end < text.length && (end === 0 || /\s/.test(text[end - 1]))) text = text.slice(0, end).trimEnd()
  return text
}

function listItem(line: string): RawItem | null {
  const m = LIST_ITEM.exec(line)
  if (!m) return null
  const ordered = /\d/.test(m[2])
  return { indent: m[1].length, ordered, start: ordered ? parseInt(m[2], 10) : 1, lines: [m[3]] }
}

export function parseMarkdown(src: string, opts: Options = {}): MdBlock[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const blocks: MdBlock[] = []
  let para: string[] = []
  let items: RawItem[] = []

  // nextFilled[i] is the first non-blank line at or after i
  const nextFilled = new Array<number>(lines.length + 1)
  nextFilled[lines.length] = -1
  for (let i = lines.length - 1; i >= 0; i--) nextFilled[i] = isBlank(lines[i]) ? nextFilled[i + 1] : i

  // only the text at the very end can still be mid-stream
  const settled = { ...opts, streaming: false }
  const flushPara = (atEnd = false) => {
    if (para.length) blocks.push({ type: 'paragraph', children: parseInline(para.join('\n'), atEnd ? opts : settled) })
    para = []
  }
  const flushList = (atEnd = false) => {
    if (items.length) blocks.push(...buildLists(items, atEnd ? opts : settled))
    items = []
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (isBlank(line)) {
      flushPara()
      // a blank line between items or before an indented continuation keeps the list going
      const n = nextFilled[i]
      const next = n === -1 ? undefined : lines[n]
      if (items.length && !(next && (LIST_ITEM.test(next) || /^\s{2,}/.test(next)))) flushList()
      continue
    }
    const heading = headingText(line)
    if (heading !== null || isRule(line)) {
      flushPara()
      flushList()
      const last = i === lines.length - 1
      if (heading) blocks.push({ type: 'heading', children: parseInline(heading, last ? opts : settled) })
      continue
    }
    const item = listItem(line)
    // inside a paragraph only a bullet or a list starting at 1 begins a list ("2026. was a year" doesn't)
    if (item && (items.length || !para.length || !item.ordered || item.start === 1)) {
      flushPara()
      items.push(item)
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

function buildLists(raw: RawItem[], opts: Options): ListBlock[] {
  const roots: ListBlock[] = []
  type Level = { indent: number; list: ListBlock; container: ListBlock[] }
  const open = (r: RawItem, container: ListBlock[], indent: number): Level => {
    const list: ListBlock = { type: 'list', ordered: r.ordered, start: r.start, items: [] }
    container.push(list)
    return { indent, list, container }
  }
  const stack: Level[] = []
  raw.forEach((r, n) => {
    while (stack.length && r.indent < stack[stack.length - 1].indent) {
      const below = stack[stack.length - 2]
      // less indented than this list but more than its parent: still a sibling here
      if (!below || r.indent > below.indent) {
        stack[stack.length - 1].indent = r.indent
        break
      }
      stack.pop()
    }
    let top = stack[stack.length - 1]
    if (!top) {
      top = open(r, roots, r.indent)
      stack.push(top)
    } else if (r.indent > top.indent && stack.length < MAX_LIST_DEPTH) {
      top = open(r, top.list.items[top.list.items.length - 1].lists, r.indent)
      stack.push(top)
    } else if (r.ordered !== top.list.ordered) {
      // switching between numbers and bullets at the same depth starts a new list
      const next = open(r, top.container, top.indent)
      top.list = next.list
    }
    const itemOpts = n === raw.length - 1 ? opts : { ...opts, streaming: false }
    top.list.items.push({ children: parseInline(r.lines.join('\n'), itemOpts), lists: [] })
  })
  return roots
}

const ESCAPABLE = /[\\`*_[\]()#+\-.!]/
const PLAIN = /[^\\\n`[hH*_]+/y
const LINK_DEST = /\s*((?:[^\s()]|\([^\s()]*\))+)\s*\)/y
const URL_START = /https?:\/\/[^\s<>]*/iy
const URL_TRAILING = new Set(['.', ',', ';', ':', '!', '?', "'", '"', '*', '_', ']'])
const MAX_DEPTH = 24
const MAX_STREAM_OPENERS = 3
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

/** A bare URL starting at `i`, without trailing punctuation or an unbalanced closing paren. */
function autolinkAt(src: string, i: number): string | null {
  URL_START.lastIndex = i
  const m = URL_START.exec(src)
  if (!m) return null
  let url = m[0]
  let depth = 0
  for (const c of url) depth += c === '(' ? 1 : c === ')' ? -1 : 0
  for (;;) {
    const last = url[url.length - 1]
    if (URL_TRAILING.has(last)) url = url.slice(0, -1)
    else if (last === ')' && depth < 0) {
      url = url.slice(0, -1)
      depth++
    } else break
  }
  return /^https?:\/\/./i.test(url) ? url : null
}

// Inline parsing: one left-to-right pass builds a linked list of cells (text, code, links and
// `*`/`_` runs), then the CommonMark delimiter algorithm pairs the runs into emphasis.
type Cell = { node: Inline; depth: number; prev: Cell | null; next: Cell | null }
type Delim = {
  cell: Cell
  ch: string
  count: number
  orig: number
  canOpen: boolean
  canClose: boolean
  line: number
  seq: number
  prev: Delim | null
  next: Delim | null
}

class Cells {
  head: Cell | null = null
  tail: Cell | null = null
  append(node: Inline, depth = 0): Cell {
    const cell: Cell = { node, depth, prev: this.tail, next: null }
    if (this.tail) this.tail.next = cell
    else this.head = cell
    this.tail = cell
    return cell
  }
  remove(cell: Cell) {
    if (cell.prev) cell.prev.next = cell.next
    else this.head = cell.next
    if (cell.next) cell.next.prev = cell.prev
    else this.tail = cell.prev
  }
  /** Replace the cells strictly between `a` and `b` (b null: to the end) with one wrapper cell. */
  wrap(a: Cell, b: Cell | null, make: (children: Inline[]) => Inline, depth: number): Cell {
    const cell: Cell = { node: make(toInlines(a.next, b)), depth, prev: a, next: b }
    a.next = cell
    if (b) b.prev = cell
    else this.tail = cell
    return cell
  }
}

function toInlines(from: Cell | null, to: Cell | null): Inline[] {
  const out: Inline[] = []
  for (let c = from; c && c !== to; c = c.next) {
    const n = c.node
    if (n.type !== 'text') out.push(n)
    else if (n.text) {
      const last = out[out.length - 1]
      if (last?.type === 'text') out[out.length - 1] = { type: 'text', text: last.text + n.text }
      else out.push({ type: 'text', text: n.text })
    }
  }
  return out
}

function maxDepth(from: Cell | null, to: Cell | null) {
  let d = 0
  for (let c = from; c && c !== to; c = c.next) d = Math.max(d, c.depth)
  return d
}

const emphasisNode = (use: number) => (children: Inline[]): Inline =>
  use === 1
    ? { type: 'em', children }
    : use === 2
      ? { type: 'strong', children }
      : { type: 'strong', children: [{ type: 'em', children }] }

export function parseInline(src: string, opts: Options = {}): Inline[] {
  const cells = new Cells()
  let text = ''
  const flush = () => {
    if (text) cells.append({ type: 'text', text })
    text = ''
  }
  let firstDelim: Delim | null = null
  let lastDelim: Delim | null = null
  let line = 0
  let seq = 0
  // next `]` or newline at or after the cursor, for link labels
  let labelEnd = -1
  // backtick runs with no closer of that length after `from`
  const noCloser = new Map<number, number>()

  let i = 0
  while (i < src.length) {
    const c = src[i]

    if (c === '\\' && i + 1 < src.length && ESCAPABLE.test(src[i + 1])) {
      text += src[i + 1]
      i += 2
      continue
    }

    if (c === '\n') {
      flush()
      cells.append({ type: 'br' })
      line++
      i++
      continue
    }

    if (c === '`') {
      let end = i
      while (src[end] === '`') end++
      const len = end - i
      const close = findCodeCloser(src, end, len, noCloser)
      if (close !== -1) {
        flush()
        cells.append({ type: 'code', text: src.slice(end, close) })
        i = close + len
        continue
      }
      if (opts.streaming && len === 1 && !src.includes('\n', i)) {
        flush()
        cells.append({ type: 'code', text: src.slice(end) })
        i = src.length
        break
      }
      text += src.slice(i, end)
      i = end
      continue
    }

    if (c === '[' && !opts.inLink) {
      if (labelEnd < i) {
        labelEnd = i + 1
        while (labelEnd < src.length && src[labelEnd] !== ']' && src[labelEnd] !== '\n') labelEnd++
      }
      if (src[labelEnd] === ']' && src[labelEnd + 1] === '(') {
        LINK_DEST.lastIndex = labelEnd + 2
        const dest = LINK_DEST.exec(src)
        if (dest) {
          flush()
          const href = safeHref(dest[1])
          const label = parseInline(src.slice(i + 1, labelEnd), { ...opts, inLink: true })
          if (href) cells.append({ type: 'link', href, children: label.length ? label : [{ type: 'text', text: href }] }, 1)
          else for (const n of label) cells.append(n, 1)
          i = LINK_DEST.lastIndex
          continue
        }
      }
    }

    if ((c === 'h' || c === 'H') && !opts.inLink && !isWordChar(src[i - 1])) {
      const url = autolinkAt(src, i)
      const href = url && safeHref(url)
      if (url && href) {
        flush()
        cells.append({ type: 'link', href, children: [{ type: 'text', text: url }] }, 1)
        i += url.length
        continue
      }
    }

    if (c === '*' || c === '_') {
      let end = i
      while (src[end] === c) end++
      const before = src[i - 1]
      const after = src[end]
      // underscores only count at word boundaries, so snake_case stays as written
      const canOpen = !isSpace(after) && !(c === '_' && isWordChar(before))
      const canClose = !isSpace(before) && !(c === '_' && isWordChar(after))
      flush()
      const cell = cells.append({ type: 'text', text: src.slice(i, end) })
      if (canOpen || canClose) {
        const d: Delim = { cell, ch: c, count: end - i, orig: end - i, canOpen, canClose, line, seq: seq++, prev: lastDelim, next: null }
        if (lastDelim) lastDelim.next = d
        else firstDelim = d
        lastDelim = d
      }
      i = end
      continue
    }

    PLAIN.lastIndex = i
    const plain = PLAIN.exec(src)
    if (plain) {
      text += plain[0]
      i += plain[0].length
    } else {
      text += c
      i++
    }
  }
  flush()

  const unlink = (d: Delim) => {
    if (d.prev) d.prev.next = d.next
    else firstDelim = d.next
    if (d.next) d.next.prev = d.prev
    else lastDelim = d.prev
  }
  const setCount = (d: Delim, n: number) => {
    d.count = n
    d.cell.node = { type: 'text', text: d.ch.repeat(n) }
  }

  const openersBottom = new Map<string, number>()
  let closer = firstDelim
  while (closer) {
    if (!closer.canClose) {
      closer = closer.next
      continue
    }
    const key = `${closer.ch}${closer.canOpen ? 1 : 0}${closer.orig % 3}`
    const bottom = openersBottom.get(key) ?? -1
    let opener = closer.prev
    while (opener && opener.seq > bottom) {
      const oddMatch =
        (opener.canClose || closer.canOpen) &&
        (opener.orig + closer.orig) % 3 === 0 &&
        !(opener.orig % 3 === 0 && closer.orig % 3 === 0)
      if (opener.ch === closer.ch && opener.canOpen && !oddMatch) break
      opener = opener.prev
    }
    const found = opener && opener.seq > bottom ? opener : null
    const use = !found ? 0 : found.count >= 3 && closer.count >= 3 ? 3 : found.count >= 2 && closer.count >= 2 ? 2 : 1
    if (!found || maxDepth(found.cell.next, closer.cell) + (use === 3 ? 2 : 1) > MAX_DEPTH) {
      openersBottom.set(key, closer.prev ? closer.prev.seq : -1)
      const next: Delim | null = closer.next
      if (!closer.canOpen) unlink(closer)
      closer = next
      continue
    }
    cells.wrap(found.cell, closer.cell, emphasisNode(use), maxDepth(found.cell.next, closer.cell) + (use === 3 ? 2 : 1))
    for (let d = found.next; d && d !== closer; d = d.next) unlink(d)
    setCount(found, found.count - use)
    setCount(closer, closer.count - use)
    if (found.count === 0) {
      cells.remove(found.cell)
      unlink(found)
    }
    if (closer.count === 0) {
      const next: Delim | null = closer.next
      cells.remove(closer.cell)
      unlink(closer)
      closer = next
    }
  }

  if (opts.streaming) {
    // an opener on the last line that never closed runs to the end, a few levels deep at most
    const pending: Delim[] = []
    for (let d = firstDelim; d && pending.length < MAX_STREAM_OPENERS; d = d.next)
      if (d.canOpen && d.count > 0 && d.line === line) pending.push(d)
    for (let k = pending.length - 1; k >= 0; k--) {
      const d = pending[k]
      const use = Math.min(d.count, 3)
      const depth = maxDepth(d.cell.next, null) + (use === 3 ? 2 : 1)
      if (!d.cell.next || depth > MAX_DEPTH) continue
      cells.wrap(d.cell, null, emphasisNode(use), depth)
      setCount(d, d.count - use)
      if (d.count === 0) cells.remove(d.cell)
    }
  }

  return toInlines(cells.head, null)
}

/** Start of the next run of exactly `len` backticks at or after `from`, or -1. */
function findCodeCloser(src: string, from: number, len: number, noCloser: Map<number, number>): number {
  const known = noCloser.get(len)
  if (known !== undefined && known <= from) return -1
  const run = '`'.repeat(len)
  let j = src.indexOf(run, from)
  while (j !== -1) {
    let end = j + len
    if (src[end] !== '`') return j
    while (src[end] === '`') end++
    j = src.indexOf(run, end)
  }
  noCloser.set(len, from)
  return -1
}

const DOMAIN_LIKE = /^(?:https?:\/\/)?([\p{L}\p{N}-]+(?:\.[\p{L}\p{N}-]+)+)(?::\d+)?(?:[/?#]\S*)?$/iu
const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}

/** The link's real host when its label reads like a different address ("cornell.edu" → evil.example). */
export function misleadingLinkHost(label: string, href: string): string | null {
  const m = DOMAIN_LIKE.exec(label.trim())
  if (!m) return null
  const real = hostOf(href)
  return real && hostOf(`http://${m[1]}`) !== real ? real : null
}

/** The visible text of an inline tree. */
export function plainText(nodes: Inline[]): string {
  return nodes
    .map((n) => (n.type === 'text' || n.type === 'code' ? n.text : n.type === 'br' ? ' ' : plainText(n.children)))
    .join('')
}
