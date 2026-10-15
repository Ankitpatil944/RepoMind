/** Language colours come from the syntax tokens so they stay in the palette. */
const LANG_COLOR: Record<string, string> = {
  python: 'var(--syn-function)',
  javascript: 'var(--syn-number)',
  typescript: 'var(--syn-type)',
}

const LANG_NAME: Record<string, string> = {
  python: 'Python',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
}

export const langColor = (language: string): string => LANG_COLOR[language] ?? 'var(--text-2)'

export const langName = (language: string): string =>
  LANG_NAME[language] ?? language.charAt(0).toUpperCase() + language.slice(1)
