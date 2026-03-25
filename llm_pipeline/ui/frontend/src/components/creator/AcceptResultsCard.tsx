import type { AcceptResponse } from '@/api/creator'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LabeledPre } from '@/components/shared'

interface AcceptResultsCardProps {
  results: AcceptResponse
}

export function AcceptResultsCard({ results }: AcceptResultsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Accept Results</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Files written */}
        <LabeledPre
          label="Files Written"
          content={results.files_written.join('\n')}
        />

        {/* Prompts registered */}
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">
            Prompts Registered
          </p>
          <p className="text-sm">{results.prompts_registered}</p>
        </div>

        {/* Pipeline file updated */}
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">
            Pipeline File
          </p>
          <Badge
            variant={results.pipeline_file_updated ? 'default' : 'secondary'}
          >
            {results.pipeline_file_updated ? 'Updated' : 'Not updated'}
          </Badge>
        </div>

        {/* Target directory */}
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">
            Target Directory
          </p>
          <p className="break-all font-mono text-xs">{results.target_dir}</p>
        </div>
      </CardContent>
    </Card>
  )
}
