import { Sparkles } from 'lucide-react'

import type { AskResponse, ExplainResponse, FlowNode, Source } from '../../api/types'
import { EmptyState, ErrorNote, Spinner } from '../../design/primitives'
import { Answer, SourceList } from './Answer'

export interface AskState {
  question: string
  pending: boolean
  result: AskResponse | null
  error: string | null
}

export interface ExplainState {
  chunkId: number
  pending: boolean
  result: ExplainResponse | null
  error: string | null
}

interface Props {
  node: FlowNode | null
  ask: AskState | null
  explain: ExplainState | null
  onExplain: (chunkId: number) => void
  onCite: (s: Source) => void
}

const LLM_HELP = (
  <>
    No language model is configured, so there is no written answer, but the retrieved sources are
    below. See <strong>Enable /ask</strong> in the README to set up Ollama, Groq or Gemini.
  </>
)

export function ExplainPane({ node, ask, explain, onExplain, onCite }: Props) {
  const chunkId = node?.chunk_id ?? null
  const showExplain = explain && explain.chunkId === chunkId

  return (
    <div className="h-full overflow-auto p-4">
      {ask && (
        <section aria-label="Answer to your question" className="mb-6">
          <h3 className="mb-2 text-[12px] font-medium uppercase tracking-wide text-text-3">Your question</h3>
          <p className="mb-3 text-[15px] font-medium text-text-1">{ask.question}</p>
          <div aria-live="polite">
            {ask.pending && <Spinner label="Searching the code and asking the model" />}
            {ask.error && <ErrorNote>{ask.error}</ErrorNote>}
            {ask.result && (
              <>
                {ask.result.answer ? (
                  <Answer text={ask.result.answer} sources={ask.result.sources} onCite={onCite} />
                ) : (
                  <ErrorNote title="No written answer">
                    {ask.result.error ? <p className="mb-1">{ask.result.error}</p> : null}
                    {LLM_HELP}
                  </ErrorNote>
                )}
                <SourceList sources={ask.result.sources} onCite={onCite} />
              </>
            )}
          </div>
        </section>
      )}

      <section aria-label="Explain the selected code">
        <h3 className="mb-2 text-[12px] font-medium uppercase tracking-wide text-text-3">Explain selection</h3>
        {!chunkId && (
          <p className="text-text-2">
            Select a function in the graph or explorer, then ask for an explanation grounded in what it
            calls and who calls it.
          </p>
        )}
        {chunkId && node && (
          <>
            <p className="mb-3 text-text-2">
              <span className="font-mono text-text-1">{node.label}</span>
              {node.file ? (
                <span className="font-mono">
                  {' '}
                  · {node.file}:{node.start_line}
                </span>
              ) : null}
            </p>
            <button
              type="button"
              onClick={() => onExplain(chunkId)}
              disabled={explain?.pending && explain.chunkId === chunkId}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-accent-600 px-3.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Sparkles size={15} aria-hidden />
              {showExplain && explain.result ? 'Explain again' : 'Explain this'}
            </button>
          </>
        )}
        <div aria-live="polite" className="mt-4">
          {showExplain && explain.pending && <Spinner label="Reading the code" />}
          {showExplain && explain.error && <ErrorNote>{explain.error}</ErrorNote>}
          {showExplain && explain.result && (
            <>
              {explain.result.answer ? (
                <Answer text={explain.result.answer} sources={explain.result.sources} onCite={onCite} />
              ) : (
                <ErrorNote title="No written explanation">
                  {explain.result.error ? <p className="mb-1">{explain.result.error}</p> : null}
                  {LLM_HELP}
                </ErrorNote>
              )}
              {explain.result.callers.length > 0 && (
                <p className="mt-3 text-[13px] text-text-2">
                  Called by: <span className="font-mono">{explain.result.callers.join(', ')}</span>
                </p>
              )}
              <SourceList sources={explain.result.sources} onCite={onCite} />
            </>
          )}
        </div>
      </section>

      {!ask && !chunkId && (
        <EmptyState title="Ask anything about this repo">
          Use the box at the bottom, for example “How do users log in?”.
        </EmptyState>
      )}
    </div>
  )
}
