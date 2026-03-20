import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { Card } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import type { CompileResponse } from '@/api/editor'

export const Route = createFileRoute('/editor')({
  component: EditorPage,
})

// ---------------------------------------------------------------------------
// Editor-local types
// ---------------------------------------------------------------------------

/** UI step item -- id is a UUID for DnD key, distinct from step_ref */
export interface EditorStepItem {
  id: string
  step_ref: string
  source: 'draft' | 'registered'
}

export interface EditorStrategyState {
  strategy_name: string
  steps: EditorStepItem[]
}

type CompileStatus = 'idle' | 'pending' | 'error'

// ---------------------------------------------------------------------------
// Placeholder panel components
// ---------------------------------------------------------------------------

function EditorPalettePanel() {
  return (
    <Card className="flex h-full flex-col overflow-hidden p-4">
      <h2 className="mb-2 text-xs font-medium text-muted-foreground">
        Step Palette
      </h2>
      <p className="text-sm text-muted-foreground">
        Available steps will appear here.
      </p>
    </Card>
  )
}

function EditorStrategyCanvas() {
  return (
    <Card className="flex h-full flex-col overflow-hidden p-4">
      <h2 className="mb-2 text-xs font-medium text-muted-foreground">
        Strategy Canvas
      </h2>
      <p className="text-sm text-muted-foreground">
        Drag-and-drop strategy editor will appear here.
      </p>
    </Card>
  )
}

function EditorPropertiesPanel() {
  return (
    <Card className="flex h-full flex-col overflow-hidden p-4">
      <h2 className="mb-2 text-xs font-medium text-muted-foreground">
        Properties
      </h2>
      <p className="text-sm text-muted-foreground">
        Step properties and compile status will appear here.
      </p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// EditorPage
// ---------------------------------------------------------------------------

function EditorPage() {
  // -- Editor state (wired in Steps 4-7) --
  const [_strategies, _setStrategies] = useState<EditorStrategyState[]>([])
  const [_selectedStepId, _setSelectedStepId] = useState<string | null>(null)
  const [_activeDraftPipelineId, _setActiveDraftPipelineId] = useState<
    number | null
  >(null)
  const [_compileResult, _setCompileResult] =
    useState<CompileResponse | null>(null)
  const [_compileStatus, _setCompileStatus] = useState<CompileStatus>('idle')

  // -- Shared column content --

  const paletteColumn = <EditorPalettePanel />

  const canvasColumn = <EditorStrategyCanvas />

  const propertiesColumn = <EditorPropertiesPanel />

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-card-foreground">
          Pipeline Editor
        </h1>
        <p className="text-sm text-muted-foreground">
          Assemble and validate pipeline strategies from available steps
        </p>
      </div>

      {/* Desktop layout (lg+): 3-column grid */}
      <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-[280px_1fr_350px] lg:gap-4">
        {/* Col 1: Step Palette */}
        <div className="overflow-auto">{paletteColumn}</div>

        {/* Col 2: Strategy Canvas */}
        <div className="overflow-hidden">{canvasColumn}</div>

        {/* Col 3: Properties Panel */}
        <div className="overflow-hidden">{propertiesColumn}</div>
      </div>

      {/* Mobile/tablet layout (below lg): tab-based */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <Tabs defaultValue="palette" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="shrink-0">
            <TabsTrigger value="palette">Palette</TabsTrigger>
            <TabsTrigger value="editor">Editor</TabsTrigger>
            <TabsTrigger value="properties">Properties</TabsTrigger>
          </TabsList>

          <TabsContent
            value="palette"
            className="min-h-0 flex-1 overflow-auto"
          >
            {paletteColumn}
          </TabsContent>
          <TabsContent
            value="editor"
            className="min-h-0 flex-1 overflow-hidden"
          >
            {canvasColumn}
          </TabsContent>
          <TabsContent
            value="properties"
            className="min-h-0 flex-1 overflow-hidden"
          >
            {propertiesColumn}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
