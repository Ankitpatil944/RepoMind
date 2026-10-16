import { useEffect, useRef, useState } from 'react'

import type { Repo } from '../api/types'

type Phase = 'idle' | 'opening' | 'fading' | 'done'

interface Props {
  repos: Repo[]
  onPick: (id: number) => void
  onDone: () => void
}

const GLYPHS = ['def', 'class', 'async', 'await', 'import', 'return', '@app.get', 'Depends()', '{ }', '=>', 'jwt.decode', 'SELECT', '/auth/login', 'raise', 'yield', 'export']

/** Envelope intro (DESIGN.md section 5): pick a repo, the seal fades, the flap opens,
 *  the letter slides up and scales to fill the screen. Always skippable; never blocks
 *  work, and is skipped entirely for reduced-motion users. */
export function Intro({ repos, onPick, onDone }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const timers = useRef<number[]>([])
  const gate = useRef<HTMLDivElement>(null)

  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), [])

  // Mouse parallax on the glyph field and the envelope.
  const onMove = (e: React.MouseEvent) => {
    const el = gate.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top) / r.height - 0.5
    el.style.setProperty('--px', `${(x * 14).toFixed(1)}px`)
    el.style.setProperty('--py', `${(y * 10).toFixed(1)}px`)
    el.style.setProperty('--tx', `${(-y * 6).toFixed(1)}deg`)
    el.style.setProperty('--ty', `${(x * 8).toFixed(1)}deg`)
  }

  const open = (id: number) => {
    if (phase !== 'idle') return
    onPick(id)
    setPhase('opening')
    timers.current.push(window.setTimeout(() => setPhase('fading'), 2950))
    timers.current.push(
      window.setTimeout(() => {
        setPhase('done')
        onDone()
      }, 3650),
    )
  }

  const skip = () => {
    timers.current.forEach((t) => window.clearTimeout(t))
    setPhase('done')
    onDone()
  }

  if (phase === 'done') return null

  return (
    <div
      ref={gate}
      className="intro-gate"
      data-s={phase}
      onMouseMove={onMove}
      role="dialog"
      aria-modal="true"
      aria-label="Choose a repository to open"
    >
      <div className="intro-bg" aria-hidden />
      <div className="intro-glyphs" aria-hidden>
        {GLYPHS.map((g, i) => (
          <span
            key={g}
            className="intro-glyph"
            style={{ left: `${(i * 37) % 96}%`, animationDuration: `${14 + (i % 5) * 3}s`, animationDelay: `${-(i * 1.7)}s` }}
          >
            {g}
          </span>
        ))}
      </div>
      <button type="button" className="intro-skip" onClick={skip}>
        Skip intro
      </button>

      <div className="intro-col">
        <div className="intro-title">
          <p className="font-mono text-[12px] text-sage">~/ repomind</p>
          <h2 className="serif text-[clamp(34px,5vw,56px)] leading-none text-cream">
            Open a <em className="text-sage">codebase</em>
          </h2>
          <p className="max-w-md text-[13px] text-text-2">
            Nothing leaves this machine. Pick an indexed repository to read it as a briefing.
          </p>
        </div>

        <div className="intro-env-tilt">
          <div className="intro-env">
            <div className="intro-env-shadow" />
            <div className="intro-env-back" />
            <div className="intro-letter-rise">
              <div className="intro-letter" />
            </div>
            <div className="intro-pk intro-pk-l" />
            <div className="intro-pk intro-pk-r" />
            <div className="intro-pk intro-pk-b" />
            <div className="intro-flap" />
            <div className="intro-seal" aria-hidden>
              <svg width="42%" viewBox="0 0 32 32">
                <circle cx="9" cy="16" r="3" fill="#12160d" />
                <circle cx="23" cy="9.5" r="3" fill="#12160d" />
                <circle cx="23" cy="22.5" r="3" fill="#12160d" />
                <path d="M12 15.5l8-5M12 16.5l8 5" stroke="#12160d" strokeWidth="1.5" />
              </svg>
            </div>
          </div>
        </div>

        <div className="intro-choices">
          {repos.slice(0, 6).map((r) => (
            <button key={r.id} type="button" className="intro-choice" onClick={() => open(r.id)}>
              <span className="font-mono text-[13px] text-cream">{r.name}</span>
              <span className="font-mono text-[11px] text-text-2">
                {r.files} files · {r.chunks} chunks
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
