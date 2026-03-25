import { useState } from 'react'
import { Wand2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

interface CreatorInputFormProps {
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
  disabled: boolean
}

const MIN_DESC_LENGTH = 10

export function CreatorInputForm({
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
  disabled,
}: CreatorInputFormProps) {
  const [touched, setTouched] = useState(false)

  const trimmed = description.trim()
  const descError = touched && (trimmed.length === 0 || trimmed.length < MIN_DESC_LENGTH)
  const descErrorMsg =
    touched && trimmed.length === 0
      ? 'Description is required'
      : touched && trimmed.length < MIN_DESC_LENGTH
        ? `At least ${MIN_DESC_LENGTH} characters`
        : null

  const generateDisabled =
    !trimmed || trimmed.length < MIN_DESC_LENGTH || isGenerating || disabled

  return (
    <div className="flex flex-col gap-3">
      {/* Description */}
      <div className="space-y-1">
        <Label htmlFor="creator-desc" className="text-xs">
          Description
        </Label>
        <Textarea
          id="creator-desc"
          placeholder="Describe what the step should do..."
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          onBlur={() => setTouched(true)}
          aria-invalid={descError || undefined}
          className="min-h-20 resize-none text-xs"
        />
        {descErrorMsg && (
          <p className="text-[11px] text-destructive">{descErrorMsg}</p>
        )}
      </div>

      {/* Target Pipeline */}
      <div className="space-y-1">
        <Label htmlFor="creator-pipeline" className="text-xs">
          Target Pipeline
        </Label>
        <Input
          id="creator-pipeline"
          placeholder="Optional"
          value={targetPipeline ?? ''}
          onChange={(e) =>
            onTargetPipelineChange(e.target.value || null)
          }
          className="text-xs"
        />
      </div>

      {/* Checkboxes */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Checkbox
            id="creator-extraction"
            checked={includeExtraction}
            onCheckedChange={(v) => onIncludeExtractionChange(v === true)}
          />
          <Label htmlFor="creator-extraction" className="text-xs font-normal">
            Include extraction
          </Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="creator-transformation"
            checked={includeTransformation}
            onCheckedChange={(v) => onIncludeTransformationChange(v === true)}
          />
          <Label
            htmlFor="creator-transformation"
            className="text-xs font-normal"
          >
            Include transformation
          </Label>
        </div>
      </div>

      {/* Generate */}
      <Button
        className="w-full"
        disabled={generateDisabled}
        onClick={onGenerate}
      >
        {isGenerating ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            Generating...
          </>
        ) : (
          <>
            <Wand2 className="size-4" />
            Generate
          </>
        )}
      </Button>
    </div>
  )
}
