/** Language colours come from the design palette: Python teal, TypeScript lavender, JavaScript brass. */
const LANG_COLOR: Record<string, string> = {
  python: 'var(--teal)',
  javascript: 'var(--brass)',
  typescript: 'var(--lavender)',
}

const LANG_NAME: Record<string, string> = {
  python: 'Python',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
}

export const langColor = (language: string): string => LANG_COLOR[language] ?? 'var(--text-2)'

export const langName = (language: string): string =>
  LANG_NAME[language] ?? language.charAt(0).toUpperCase() + language.slice(1)

/** Complexity bands from DESIGN.md: >= 10 terracotta, >= 6 brass, else moss. */
export const cxColor = (cx: number): string =>
  cx >= 10 ? 'var(--terracotta)' : cx >= 6 ? 'var(--brass)' : 'var(--moss)'

/** Treemap heat: interpolate a tile from cool (rgb 21,36,44) to hot (rgb 100,56,40). */
export function heat(t: number): { bg: string; border: string } {
  const k = Math.max(0, Math.min(1, t))
  const mix = (a: number, b: number) => Math.round(a + (b - a) * k)
  return {
    bg: `rgb(${mix(21, 100)},${mix(36, 56)},${mix(44, 40)})`,
    border: `rgb(${mix(42, 217)},${mix(74, 138)},${mix(88, 98)})`,
  }
}
