import { useMemo } from 'react'
import { parseMarkdown, type Inline, type ListBlock, type MdBlock } from './markdown'

export default function MarkdownText({ text, streaming = false }: { text: string; streaming?: boolean }) {
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
      case 'link':
        return (
          <a key={i} href={n.href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
            {renderInline(n.children)}
          </a>
        )
    }
  })
}
