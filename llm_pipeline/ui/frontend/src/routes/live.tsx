import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { Play, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useCreateRun } from '@/api/runs'
import { usePipeline } from '@/api/pipelines'
import { subscribeToRun } from '@/api/websocket'
import { useWsStore } from '@/stores/websocket'
import type { ApiError } from '@/api/types'
import { PipelineSelector } from '@/components/live/PipelineSelector'
import { InputForm, validateForm } from '@/components/live/InputForm'
import { MonitoringPanel } from '@/components/live/MonitoringPanel'
import { RunPicker } from '@/components/live/RunPicker'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

export const Route = createFileRoute('/live')({
  component: LivePage,
})

function LivePage() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
  const [inputValues, setInputValues] = useState<Record<string, unknown>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [triggerOpen, setTriggerOpen] = useState(true)
  const [pickerOpen, setPickerOpen] = useState(false)

  const createRun = useCreateRun()
  const { data: pipelineDetail } = usePipeline(selectedPipeline ?? '')
  const inputSchema = pipelineDetail?.pipeline_input_schema ?? null
  const setFocusedRun = useWsStore((s) => s.setFocusedRun)

  const handleRunPipeline = useCallback(() => {
    if (!selectedPipeline) return

    const errors = validateForm(inputSchema, inputValues)
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }
    setFieldErrors({})

    createRun.mutate(
      {
        pipeline_name: selectedPipeline,
        input_data: inputSchema ? inputValues : undefined,
      },
      {
        onSuccess: (data) => {
          subscribeToRun(data.run_id, selectedPipeline)
          setFocusedRun(data.run_id)
          setInputValues({})
          setFieldErrors({})
        },
        onError: (error) => {
          const apiErr = error as ApiError
          if (apiErr.status === 422) {
            try {
              const details = JSON.parse(apiErr.detail) as Array<{
                loc: string[]
                msg: string
              }>
              const mapped: Record<string, string> = {}
              for (const item of details) {
                const field = item.loc[item.loc.length - 1]
                mapped[field] = item.msg
              }
              if (Object.keys(mapped).length > 0) setFieldErrors(mapped)
            } catch { /* not structured JSON */ }
          }
        },
      },
    )
  }, [selectedPipeline, createRun, inputSchema, inputValues, setFocusedRun])

  useEffect(() => {
    setInputValues({})
    setFieldErrors({})
  }, [selectedPipeline])

  // -- Trigger panel content (shared between desktop + mobile) --

  const triggerContent = (
    <Card className="flex h-full flex-col overflow-hidden">
      <CardContent className="shrink-0 flex flex-col gap-4 p-4">
        <PipelineSelector
          selectedPipeline={selectedPipeline}
          onSelect={setSelectedPipeline}
          disabled={createRun.isPending}
        />
        <Button
          onClick={handleRunPipeline}
          disabled={!selectedPipeline || createRun.isPending}
          className="w-full"
        >
          <Play className="size-4" />
          {createRun.isPending ? 'Starting...' : 'Run Pipeline'}
        </Button>
      </CardContent>

      {inputSchema && (
        <ScrollArea thin className="min-h-0 flex-1">
          <div className="px-4 pb-4">
            <InputForm
              schema={inputSchema}
              values={inputValues}
              onChange={(field, value) =>
                setInputValues((prev) => ({ ...prev, [field]: value }))
              }
              fieldErrors={fieldErrors}
              isSubmitting={createRun.isPending}
            />
          </div>
        </ScrollArea>
      )}
    </Card>
  )

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-card-foreground">Live</h1>
          <p className="text-sm text-muted-foreground">Pipeline monitoring</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="hidden lg:flex"
          onClick={() => setTriggerOpen((v) => !v)}
        >
          {triggerOpen ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
        </Button>
      </div>

      {/* Desktop (lg+): 2-column with collapsible trigger panel */}
      <div className="hidden min-h-0 flex-1 lg:flex lg:gap-4">
        {triggerOpen && (
          <div className="w-72 shrink-0 overflow-hidden">
            {triggerContent}
          </div>
        )}
        <div className="min-w-0 flex-1 overflow-hidden">
          <MonitoringPanel onOpenPicker={() => setPickerOpen(true)} />
        </div>
      </div>

      {/* Mobile: tab-based */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <Tabs defaultValue="trigger" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="shrink-0">
            <TabsTrigger value="trigger">Trigger</TabsTrigger>
            <TabsTrigger value="monitor">Monitor</TabsTrigger>
          </TabsList>
          <TabsContent value="trigger" className="min-h-0 flex-1 overflow-auto">
            {triggerContent}
          </TabsContent>
          <TabsContent value="monitor" className="min-h-0 flex-1 overflow-auto">
            <MonitoringPanel onOpenPicker={() => setPickerOpen(true)} />
          </TabsContent>
        </Tabs>
      </div>

      <RunPicker open={pickerOpen} onOpenChange={setPickerOpen} />
    </div>
  )
}
