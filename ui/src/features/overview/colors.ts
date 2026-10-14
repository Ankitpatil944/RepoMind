/** Language colours come from the syntax tokens so they stay in the palette. */
const LANG_COLOR: Record<string, string> = {
  python: 'var(--syn-function)',
  javascript: 'var(--syn-number)',
}

export const langColor = (language: string): string => LANG_COLOR[language] ?? 'var(--text-2)'
