import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(__dirname, 'tokens.css'), 'utf8')

function token(name: string): string {
  const m = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))
  if (!m) throw new Error(`token --${name} not found`)
  return m[1]
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const SURFACES = ['bg-0', 'bg-1', 'bg-2'] as const

describe('colour tokens meet WCAG contrast', () => {
  const textTokens = [
    'text-1',
    'text-2',
    'text-3',
    'accent-400',
    'auth',
    'ok',
    'warn',
    'danger',
    'syn-keyword',
    'syn-string',
    'syn-number',
    'syn-comment',
    'syn-function',
    'syn-type',
  ]

  for (const surface of SURFACES) {
    for (const name of textTokens) {
      it(`${name} on ${surface} >= 4.5:1`, () => {
        expect(contrast(token(name), token(surface))).toBeGreaterThanOrEqual(4.5)
      })
    }
  }

  it('dark text on the primary button (accent-600) >= 4.5:1', () => {
    expect(contrast(token('on-accent'), token('accent-600'))).toBeGreaterThanOrEqual(4.5)
  })

  it('cream display text on ink >= 4.5:1', () => {
    expect(contrast(token('cream'), token('bg-0'))).toBeGreaterThanOrEqual(4.5)
  })

  it('sage text on its tinted selection background >= 4.5:1', () => {
    expect(contrast(token('accent-400'), token('sage-bg'))).toBeGreaterThanOrEqual(4.5)
  })

  it('control borders are visible against panels as a dim line (decorative, DESIGN.md)', () => {
    // Inputs are also distinguished by fill, focus ring and label, so the border is
    // not the only affordance. Guard against a border that vanishes entirely.
    for (const surface of ['bg-1', 'bg-2'] as const) {
      expect(contrast(token('border-control'), token(surface))).toBeGreaterThanOrEqual(1.2)
    }
  })

  it('accent-500 is kept for non-text use: it is allowed to fail text contrast but passes 3:1', () => {
    expect(contrast(token('accent-500'), token('bg-1'))).toBeGreaterThanOrEqual(3)
  })
})
