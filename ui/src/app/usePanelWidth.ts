import { useCallback, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'

function read(key: string, fallback: number): number {
  try {
    const v = Number(window.localStorage.getItem(key))
    return Number.isFinite(v) && v > 0 ? v : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: number): void {
  try {
    window.localStorage.setItem(key, String(Math.round(value)))
  } catch {
    /* storage unavailable (private mode): width just won't persist */
  }
}

/** Width of a side panel with a draggable, keyboard-operable separator.
 *  `side` is which edge of the panel the handle sits on. */
export function usePanelWidth(key: string, initial: number, min: number, max: number, side: 'right' | 'left') {
  const [width, setWidth] = useState(() => Math.min(max, Math.max(min, read(key, initial))))
  const drag = useRef<{ x: number; w: number } | null>(null)
  const clamp = useCallback((w: number) => Math.min(max, Math.max(min, w)), [min, max])

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    drag.current = { x: e.clientX, w: width }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    const dx = e.clientX - drag.current.x
    setWidth(clamp(drag.current.w + (side === 'right' ? dx : -dx)))
  }
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    drag.current = null
    e.currentTarget.releasePointerCapture(e.pointerId)
    write(key, width)
  }
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 48 : 16
    const grow = side === 'right' ? 'ArrowRight' : 'ArrowLeft'
    const shrink = side === 'right' ? 'ArrowLeft' : 'ArrowRight'
    if (e.key !== grow && e.key !== shrink) return
    e.preventDefault()
    const next = clamp(width + (e.key === grow ? step : -step))
    setWidth(next)
    write(key, next)
  }

  return {
    width,
    separatorProps: {
      role: 'separator' as const,
      'aria-orientation': 'vertical' as const,
      'aria-valuemin': min,
      'aria-valuemax': max,
      'aria-valuenow': Math.round(width),
      tabIndex: 0,
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onKeyDown,
    },
  }
}
