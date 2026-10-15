import { Component, useMemo, type ReactNode } from 'react'
import { misleadingLinkHost, parseMarkdown, plainText, type Inline, type ListBlock, type MdBlock } from './markdown'

type Props = { text: string; streaming?: boolean }

export default function MarkdownText({ text, streaming = false }: Props) {
  return (
    <PlainOnError text={text}>
      <Markdown text={text} streaming={streaming} />
    </PlainOnError>
  )
}

type BoundaryState = { failed: boolean; text: string }

/** If formatting a reply ever fails, show it as plain text instead of taking the page down. */
class PlainOnError extends Component<{ text: string; children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failed: false, text: this.props.text }

  static getDerivedStateFromError(): Partial<BoundaryState> {
    return { failed: true }
  }

  // try formatting again when more text streams in
  static getDerivedStateFromProps(props: { text: string }, state: BoundaryState): BoundaryState | null {
    return props.text === state.text ? null : { failed: false, text: props.text }
  }

  render() {
    if (this.state.failed) return <p className="m-0 leading-relaxed whitespace-pre-wrap">{this.props.text}</p>
    return this.props.children
  }
}

function Markdown({ text, streaming = false }: Props) {
  const blocks = useMemo(() => parseMarkdown(text, { streaming }), [text, streaming])
  return <div className="flex flex-col gap-2 leading-relaxed">{blocks.map(renderBlock)}</div>
}

function renderBlock(b: MdBlock, key: number) {
  if (b.type === 'heading')
    return (
      <p key={key} className="m-0 font-bold">
        {renderInline(b.children)}
      </p>
    )
  if (b.type === 'list') return renderList(b, key)
  return (
    <p key={key} className="m-0">
      {renderInline(b.children)}
    </p>
  )
}

function renderList(list: ListBlock, key: number) {
  const items = list.items.map((item, i) => (
    <li key={i} className="pl-0.5">
      {renderInline(item.children)}
      {item.lists.map((sub, j) => renderList(sub, j))}
    </li>
  ))
  return list.ordered ? (
    <ol key={key} start={list.start === 1 ? undefined : list.start} className="m-0 flex list-decimal flex-col gap-1 pl-5">
      {items}
    </ol>
  ) : (
    <ul key={key} className="m-0 flex list-disc flex-col gap-1 pl-5">
      {items}
    </ul>
  )
}

function renderInline(nodes: Inline[]) {
  return nodes.map((n, i) => {
    switch (n.type) {
      case 'text':
        return n.text
      case 'br':
        return <br key={i} />
      case 'strong':
        return <strong key={i}>{renderInline(n.children)}</strong>
      case 'em':
        return <em key={i}>{renderInline(n.children)}</em>
      case 'code':
        return (
          <code key={i} className="rounded bg-chip px-1 py-px font-mono text-[0.9em]">
            {n.text}
          </code>
        )
      case 'link': {
        // a label that reads like another address gets the real one next to it
        const realHost = misleadingLinkHost(plainText(n.children), n.href)
        return (
          <a
            key={i}
            href={n.href}
            title={n.href}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2"
          >
            {renderInline(n.children)}
            {realHost && <span className="text-muted"> ({realHost})</span>}
          </a>
        )
      }
    }
  })
}
