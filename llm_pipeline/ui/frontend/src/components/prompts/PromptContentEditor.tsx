import { useEffect, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import type { editor, Position } from 'monaco-editor'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type VarDefs = Record<
  string,
  { type: string; description: string; auto_generate?: string }
>

// ---------------------------------------------------------------------------
// Variable extraction
// ---------------------------------------------------------------------------

export const VAR_RE = /\{[a-zA-Z_][a-zA-Z0-9_]*\}/g

export function extractVariables(content: string): string[] {
  const matches = content.match(VAR_RE)
  return matches ? [...new Set(matches)] : []
}

// ---------------------------------------------------------------------------
// Dark mode helper
// ---------------------------------------------------------------------------

export function useIsDark(): boolean {
  const [dark, setDark] = useState(() =>
    typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
  )
  useEffect(() => {
    const obs = new MutationObserver(() => {
      setDark(document.documentElement.classList.contains('dark'))
    })
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return dark
}

// ---------------------------------------------------------------------------
// Prompt content editor with variable hover + autocomplete
// ---------------------------------------------------------------------------

export interface PromptContentEditorProps {
  value: string
  onChange: (v: string) => void
  varDefs: VarDefs
  isDark: boolean
  /** Optional Monaco height — defaults to 300px to preserve prior behavior. */
  height?: string
  /** Read-only mode disables edits (useful for showing prod content). */
  readOnly?: boolean
}

export function PromptContentEditor({
  value,
  onChange,
  varDefs,
  isDark,
  height = '300px',
  readOnly = false,
}: PromptContentEditorProps) {
  const varDefsRef = useRef(varDefs)
  varDefsRef.current = varDefs

  const handleMount: OnMount = (_editor, monaco) => {
    // Hover provider: show variable info on {variable}
    monaco.languages.registerHoverProvider('markdown', {
      provideHover(model: editor.ITextModel, position: Position) {
        const word = model.getWordAtPosition(position)
        if (!word) return null
        const line = model.getLineContent(position.lineNumber)
        // Check if word is inside {braces}
        const before = line.substring(0, word.startColumn - 1)
        const after = line.substring(word.endColumn - 1)
        if (!before.endsWith('{') || !after.startsWith('}')) return null

        const name = word.word
        const def = varDefsRef.current[name]
        if (!def) return null

        const parts = [`**\`{${name}}\`**  \nType: \`${def.type}\``]
        if (def.description) parts.push(`Description: ${def.description}`)
        if (def.auto_generate) parts.push(`Auto-generate: \`${def.auto_generate}\``)

        return {
          range: new monaco.Range(
            position.lineNumber, word.startColumn - 1,
            position.lineNumber, word.endColumn + 1,
          ),
          contents: [{ value: parts.join('  \n') }],
        }
      },
    })

    // Completion provider: suggest variables after {
    monaco.languages.registerCompletionItemProvider('markdown', {
      triggerCharacters: ['{'],
      provideCompletionItems(model: editor.ITextModel, position: Position) {
        const textBefore = model.getValueInRange({
          startLineNumber: position.lineNumber,
          startColumn: Math.max(1, position.column - 1),
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        })
        if (textBefore !== '{') return { suggestions: [] }

        const range = {
          startLineNumber: position.lineNumber,
          startColumn: position.column,
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        }

        const suggestions = Object.entries(varDefsRef.current).map(([name, def]) => ({
          label: name,
          kind: monaco.languages.CompletionItemKind.Variable,
          insertText: name + '}',
          range,
          detail: def.type + (def.auto_generate ? ` (${def.auto_generate})` : ''),
          documentation: def.description || undefined,
        }))

        return { suggestions }
      },
    })
  }

  return (
    <div className="min-h-[300px] rounded-md border" style={{ overflow: 'visible' }}>
      <Editor
        height={height}
        language="markdown"
        theme={isDark ? 'vs-dark' : 'light'}
        value={value}
        onChange={(v) => onChange(v ?? '')}
        onMount={handleMount}
        options={{
          minimap: { enabled: false },
          lineNumbers: 'on',
          wordWrap: 'on',
          fontSize: 13,
          scrollBeyondLastLine: false,
          readOnly,
        }}
      />
    </div>
  )
}
