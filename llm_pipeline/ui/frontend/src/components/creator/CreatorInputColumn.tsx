import type { DraftItem } from '@/api/creator'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { DraftPicker } from './DraftPicker'
import { CreatorInputForm } from './CreatorInputForm'

interface CreatorInputColumnProps {
  /* DraftPicker props */
  drafts: DraftItem[]
  draftsLoading: boolean
  selectedDraftId: number | null
  onSelectDraft: (draft: DraftItem) => void
  onNewDraft: () => void
  /* CreatorInputForm props */
  description: string
  onDescriptionChange: (v: string) => void
  targetPipeline: string | null
  onTargetPipelineChange: (v: string | null) => void
  includeExtraction: boolean
  onIncludeExtractionChange: (v: boolean) => void
  includeTransformation: boolean
  onIncludeTransformationChange: (v: boolean) => void
  onGenerate: () => void
  isGenerating: boolean
  formDisabled: boolean
}

export function CreatorInputColumn({
  drafts,
  draftsLoading,
  selectedDraftId,
  onSelectDraft,
  onNewDraft,
  description,
  onDescriptionChange,
  targetPipeline,
  onTargetPipelineChange,
  includeExtraction,
  onIncludeExtractionChange,
  includeTransformation,
  onIncludeTransformationChange,
  onGenerate,
  isGenerating,
  formDisabled,
}: CreatorInputColumnProps) {
  return (
    <Card className="flex h-full flex-col gap-0 overflow-hidden py-0">
      {/* Draft picker -- top ~40% */}
      <CardContent className="shrink-0 pt-4 pb-0">
        <DraftPicker
          drafts={drafts}
          isLoading={draftsLoading}
          selectedDraftId={selectedDraftId}
          onSelect={onSelectDraft}
          onNew={onNewDraft}
        />
      </CardContent>

      <Separator className="mx-6 w-auto" />

      {/* Input form -- remaining space */}
      <CardContent className="min-h-0 flex-1 overflow-y-auto pt-3 pb-4">
        <CreatorInputForm
          description={description}
          onDescriptionChange={onDescriptionChange}
          targetPipeline={targetPipeline}
          onTargetPipelineChange={onTargetPipelineChange}
          includeExtraction={includeExtraction}
          onIncludeExtractionChange={onIncludeExtractionChange}
          includeTransformation={includeTransformation}
          onIncludeTransformationChange={onIncludeTransformationChange}
          onGenerate={onGenerate}
          isGenerating={isGenerating}
          disabled={formDisabled}
        />
      </CardContent>
    </Card>
  )
}
