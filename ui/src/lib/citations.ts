/** Turn "[1]" / "[2][3]" markers in an LLM answer into markdown links
 *  (`#cite-1`) that the Answer component renders as clickable chips. */
export function linkCitations(text: string): string {
  return text.replace(/\[(\d{1,2})\](?!\()/g, (_m, n: string) => `[${n}](#cite-${n})`)
}

/** `#cite-3` -> 3, anything else -> null. */
export function citationRef(href: string | undefined): number | null {
  const m = href?.match(/^#cite-(\d{1,2})$/)
  return m ? Number.parseInt(m[1], 10) : null
}
