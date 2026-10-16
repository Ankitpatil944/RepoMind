import { CornerDownLeft } from 'lucide-react'
import { forwardRef, useState } from 'react'

import { Kbd } from '../../design/primitives'

interface Props {
  disabled: boolean
  pending: boolean
  aiStatus?: 'ready' | 'unreachable' | 'error' | null
  onAsk: (question: string) => void
}

/** The ask box lives in the header (DESIGN.md): `/` focuses it, Enter submits. */
export const AskBar = forwardRef<HTMLInputElement, Props>(function AskBar({ disabled, pending, aiStatus, onAsk }, ref) {
  const [text, setText] = useState('')
  return (
    <form
      role="search"
      aria-label="Ask about this repository"
      onSubmit={(e) => {
        e.preventDefault()
        const q = text.trim()
        if (q && !disabled && !pending) onAsk(q)
      }}
      className="flex h-[34px] min-w-0 flex-1 items-center gap-2 rounded-[7px] border border-border-control bg-bg-0 pl-3 pr-1.5 text-text-2 transition-colors duration-150 focus-within:border-sage"
    >
      <label htmlFor="ask-input" className="sr-only">
        Ask
      </label>
      <input
        id="ask-input"
        ref={ref}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        placeholder={
          aiStatus && aiStatus !== 'ready'
            ? 'Search the code (AI is off: you get matching code, not a written answer)'
            : 'Ask: how do users log in? which endpoints need auth?'
        }
        className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-text-1 outline-none placeholder:text-text-3 disabled:opacity-60"
      />
      <span className="hidden md:inline-flex">
        <Kbd>/</Kbd>
      </span>
      <button
        type="submit"
        aria-label={pending ? 'Asking' : 'Submit question'}
        disabled={disabled || pending || !text.trim()}
        className="inline-flex h-6 shrink-0 items-center gap-1 rounded-[5px] bg-raised px-2 text-[12px] font-medium text-text-1 transition-colors duration-150 hover:bg-bg-3 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {pending ? 'Asking…' : 'Ask'}
        <CornerDownLeft size={12} aria-hidden />
      </button>
    </form>
  )
})
