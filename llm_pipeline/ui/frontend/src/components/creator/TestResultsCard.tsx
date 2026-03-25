import type { TestResponse } from '@/api/creator'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LabeledPre, BadgeSection, EmptyState } from '@/components/shared'

interface TestResultsCardProps {
  results: TestResponse
}

export function TestResultsCard({ results }: TestResultsCardProps) {
  const importPassed = results.import_ok
  const hasSecurityIssues = results.security_issues.length > 0
  const hasErrors = results.errors.length > 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Test Results</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Import status */}
        <BadgeSection
          badge={
            <Badge variant={importPassed ? 'default' : 'destructive'}>
              {importPassed ? 'Import: Pass' : 'Import: Fail'}
            </Badge>
          }
        >
          {results.sandbox_skipped && (
            <p className="text-xs text-muted-foreground">Sandbox skipped</p>
          )}
        </BadgeSection>

        {/* Security issues */}
        {hasSecurityIssues && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-destructive">Security Issues</p>
            <ul className="space-y-1">
              {results.security_issues.map((issue, i) => (
                <li
                  key={i}
                  className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-1.5 text-xs text-destructive"
                >
                  {issue}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Output */}
        {results.output ? (
          <LabeledPre label="Output" content={results.output} />
        ) : (
          <EmptyState message="No output produced" />
        )}

        {/* Errors */}
        {hasErrors && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-destructive">Errors</p>
            <ul className="space-y-1">
              {results.errors.map((err, i) => (
                <li key={i}>
                  <pre className="whitespace-pre-wrap break-all rounded-md bg-destructive/5 p-2 text-xs text-destructive">
                    {err}
                  </pre>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Modules found */}
        {results.modules_found.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Modules Found</p>
            <div className="flex flex-wrap gap-1">
              {results.modules_found.map((mod) => (
                <Badge key={mod} variant="secondary" className="text-[10px]">
                  {mod}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
