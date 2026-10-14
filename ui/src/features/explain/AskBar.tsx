import { CornerDownLeft } from 'lucide-react'
import { forwardRef, useState } from 'react'

import { Kbd } from '../../design/primitives'

interface Props {
  disabled: boolean
  pending: boolean
  aiStatus?: 'ready' | 'unreachable' | 'error' | null
  onAsk: (question: string) => void
}

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
      className="flex items-center gap-3 border-t border-border-subtle bg-bg-1 px-4 py-2.5"
    >
      <label htmlFor="ask-input" className="shrink-0 text-[13px] font-medium text-text-2">
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
            ? 'Search the code (AI is off, so you get the matching code, not a written answer)'
            : 'How do users log in? Which endpoints require authentication?'
        }
        className="h-9 min-w-0 flex-1 rounded-md border border-border-control bg-bg-2 px-3 text-[14px] text-text-1 placeholder:text-text-3 disabled:opacity-60"
      />
      <span className="hidden items-center gap-1 text-[12px] text-text-3 md:inline-flex">
        press <Kbd>/</Kbd> to focus
      </span>
      <button
        type="submit"
        disabled={disabled || pending || !text.trim()}
        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md bg-accent-600 px-3.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {pending ? 'Asking…' : 'Ask'}
        <CornerDownLeft size={14} aria-hidden />
      </button>
    </form>
  )
})
