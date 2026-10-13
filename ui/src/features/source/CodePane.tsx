import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { EditorState, StateEffect, StateField, type Extension } from '@codemirror/state'
import { Decoration, EditorView, lineNumbers, type DecorationSet } from '@codemirror/view'
import { tags as t } from '@lezer/highlight'
import { useEffect, useRef } from 'react'

const setRange = StateEffect.define<{ start: number; end: number } | null>()

const rangeField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    value = value.map(tr.changes)
    for (const e of tr.effects) {
      if (!e.is(setRange)) continue
      if (!e.value) return Decoration.none
      const doc = tr.state.doc
      const start = Math.min(Math.max(e.value.start, 1), doc.lines)
      const end = Math.min(Math.max(e.value.end, start), doc.lines)
      const marks = []
      for (let n = start; n <= end; n++) {
        marks.push(Decoration.line({ class: 'cm-active-range' }).range(doc.line(n).from))
      }
      return Decoration.set(marks)
    }
    return value
  },
  provide: (f) => EditorView.decorations.from(f),
})

const theme = EditorView.theme(
  {
    '&': {
      backgroundColor: 'var(--bg-1)',
      color: 'var(--text-1)',
      height: '100%',
      fontSize: '13px',
    },
    '.cm-scroller': { fontFamily: 'var(--font-mono)', lineHeight: '1.6' },
    '.cm-content': { caretColor: 'var(--accent-400)', padding: '8px 0' },
    '.cm-gutters': {
      backgroundColor: 'var(--bg-1)',
      color: 'var(--text-3)',
      border: 'none',
      borderRight: '1px solid var(--border-subtle)',
    },
    '.cm-activeLineGutter': { backgroundColor: 'transparent' },
    '.cm-active-range': {
      backgroundColor: 'color-mix(in srgb, var(--accent-500) 14%, transparent)',
      boxShadow: 'inset 2px 0 0 var(--accent-500)',
    },
    '&.cm-focused': { outline: '2px solid var(--accent-400)', outlineOffset: '-2px' },
    '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': {
      backgroundColor: 'color-mix(in srgb, var(--accent-500) 35%, transparent) !important',
    },
  },
  { dark: true },
)

const highlight = syntaxHighlighting(
  HighlightStyle.define([
    { tag: [t.keyword, t.controlKeyword, t.definitionKeyword, t.moduleKeyword], color: 'var(--syn-keyword)' },
    { tag: [t.string, t.special(t.string)], color: 'var(--syn-string)' },
    { tag: [t.number, t.bool, t.null], color: 'var(--syn-number)' },
    { tag: [t.comment, t.lineComment, t.blockComment], color: 'var(--syn-comment)', fontStyle: 'italic' },
    { tag: [t.function(t.variableName), t.function(t.propertyName), t.definition(t.function(t.variableName))], color: 'var(--syn-function)' },
    { tag: [t.typeName, t.className, t.definition(t.className)], color: 'var(--syn-type)' },
    { tag: [t.meta, t.annotation], color: 'var(--syn-number)' },
  ]),
)

function languageExtension(language: string): Extension {
  return language === 'python' ? python() : javascript({ jsx: true })
}

interface Props {
  content: string
  language: string
  start: number | null
  end: number | null
  label: string
}

/** Read-only source viewer. Keyboard users can still move the caret and scroll;
 *  the symbol's line range is highlighted and scrolled into view. */
export function CodePane({ content, language, start, end, label }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)

  useEffect(() => {
    if (!host.current) return
    const v = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: content,
        extensions: [
          lineNumbers(),
          EditorState.readOnly.of(true),
          EditorView.contentAttributes.of({ 'aria-label': label, 'aria-readonly': 'true' }),
          languageExtension(language),
          highlight,
          theme,
          rangeField,
        ],
      }),
    })
    view.current = v
    return () => {
      v.destroy()
      view.current = null
    }
  }, [content, language, label])

  useEffect(() => {
    const v = view.current
    if (!v) return
    if (start === null) {
      v.dispatch({ effects: setRange.of(null) })
      return
    }
    const last = Math.min(Math.max(end ?? start, start), v.state.doc.lines)
    const first = Math.min(Math.max(start, 1), v.state.doc.lines)
    v.dispatch({
      effects: [
        setRange.of({ start: first, end: last }),
        EditorView.scrollIntoView(v.state.doc.line(first).from, { y: 'center' }),
      ],
    })
  }, [start, end, content, language, label])

  return <div ref={host} className="h-full min-h-0 overflow-hidden" />
}
