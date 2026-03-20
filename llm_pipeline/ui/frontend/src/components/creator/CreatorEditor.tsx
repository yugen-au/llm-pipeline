import { lazy, Suspense, useMemo } from 'react'
import { FlaskConical, Check, Loader2 } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared'
import { EditorSkeleton } from './EditorSkeleton'

const MonacoEditor = lazy(() => import('@monaco-editor/react'))

type WorkflowState =
  | 'idle'
  | 'generating'
  | 'draft'
  | 'testing'
  | 'tested'
  | 'accepting'
  | 'accepted'
  | 'error'

interface CreatorEditorProps {
  generatedCode: Record<string, string>
  draftName: string | null
  activeTab: string
  onTabChange: (tab: string) => void
  onCodeChange: (filename: string, value: string) => void
  onTest: () => void
  onAccept: () => void
  workflowState: WorkflowState
  hasExtraction: boolean
}

const EDITOR_OPTIONS = {
  automaticLayout: true,
  scrollBeyondLastLine: false,
  minimap: { enabled: false },
  fontSize: 13,
  tabSize: 4,
  wordWrap: 'on' as const,
} as const

const TABS = [
  { value: 'step', label: 'Step' },
  { value: 'instructions', label: 'Instructions' },
  { value: 'prompts', label: 'Prompts' },
  { value: 'extractions', label: 'Extractions' },
] as const

const TEST_ENABLED_STATES = new Set<WorkflowState>(['draft', 'tested', 'error'])

export function CreatorEditor({
  generatedCode,
  draftName,
  activeTab,
  onTabChange,
  onCodeChange,
  onTest,
  onAccept,
  workflowState,
  hasExtraction,
}: CreatorEditorProps) {
  const hasCode = Object.keys(generatedCode).length > 0

  const currentPath = useMemo(
    () => `${draftName ?? 'draft'}_${activeTab}.py`,
    [draftName, activeTab],
  )

  const currentValue = generatedCode[currentPath] ?? ''

  const isTesting = workflowState === 'testing'
  const isAccepting = workflowState === 'accepting'
  const testDisabled = !TEST_ENABLED_STATES.has(workflowState) || isTesting || isAccepting
  const acceptDisabled = workflowState !== 'tested' || isAccepting

  return (
    <div className="flex h-full flex-col gap-2">
      {/* Tab bar */}
      <Tabs value={activeTab} onValueChange={onTabChange}>
        <TabsList>
          {TABS.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              disabled={tab.value === 'extractions' && !hasExtraction}
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Editor area */}
      <div className="min-h-0 flex-1">
        {hasCode ? (
          <Suspense fallback={<EditorSkeleton />}>
            <MonacoEditor
              height="100%"
              defaultLanguage="python"
              path={currentPath}
              value={currentValue}
              theme="vs-dark"
              options={EDITOR_OPTIONS}
              saveViewState
              onChange={(value) => onCodeChange(currentPath, value ?? '')}
            />
          </Suspense>
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState message="Generate a step to start editing" />
          </div>
        )}
      </div>

      {/* Action buttons */}
      {hasCode && (
        <div className="flex shrink-0 gap-2">
          <Button
            variant="outline"
            onClick={onTest}
            disabled={testDisabled}
          >
            {isTesting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <FlaskConical className="size-4" />
            )}
            {isTesting ? 'Testing...' : 'Test'}
          </Button>
          <Button
            onClick={onAccept}
            disabled={acceptDisabled}
          >
            {isAccepting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Check className="size-4" />
            )}
            {isAccepting ? 'Accepting...' : 'Accept'}
          </Button>
        </div>
      )}
    </div>
  )
}
