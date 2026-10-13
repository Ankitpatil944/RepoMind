import ReactMarkdown from 'react-markdown'

import type { Source } from '../../api/types'
import { citationRef, linkCitations } from '../../lib/citations'

interface Props {
  text: string
  sources: Source[]
  onCite: (s: Source) => void
}

/** LLM output is untrusted: react-markdown never renders raw HTML, and links
 *  other than our own `#cite-n` markers are shown as plain text. */
export function Answer({ text, sources, onCite }: Props) {
  return (
    <div className="prose-answer text-text-1">
      <ReactMarkdown
        components={{
          a({ href, children }) {
            const ref = citationRef(href)
            if (ref === null) return <span>{children}</span>
            const source = sources.find((s) => s.ref === ref)
            if (!source) return <span className="text-text-2">[{ref}]</span>
            return (
              <button
                type="button"
                onClick={() => onCite(source)}
                title={`${source.file}:${source.start_line}-${source.end_line}`}
                aria-label={`Source ${ref}: ${source.name}`}
                className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border border-border-control bg-bg-2 px-1 align-baseline font-mono text-[11px] text-accent-400 transition-colors duration-150 hover:bg-bg-3"
              >
                {ref}
              </button>
            )
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  )
}

export function SourceList({ sources, onCite }: { sources: Source[]; onCite: (s: Source) => void }) {
  if (sources.length === 0) return null
  return (
    <section aria-label="Sources" className="mt-4">
      <h4 className="mb-1.5 text-[12px] font-medium uppercase tracking-wide text-text-3">Sources</h4>
      <ul className="space-y-1">
        {sources.map((s) => (
          <li key={s.ref}>
            <button
              type="button"
              onClick={() => onCite(s)}
              className="flex w-full items-center gap-2 rounded-md border border-border-subtle bg-bg-2 px-2 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3"
            >
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-border-control px-1 font-mono text-[11px] text-accent-400">
                {s.ref}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-[12.5px]">{s.name}</span>
                <span className="block truncate font-mono text-[11.5px] text-text-2">
                  {s.file}:{s.start_line}-{s.end_line}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
