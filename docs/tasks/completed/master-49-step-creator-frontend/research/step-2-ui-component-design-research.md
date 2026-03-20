# Step 2: UI Component Design Research -- Step Creator Frontend

## 1. Three-Column Layout Patterns

### Existing Codebase Pattern (live.tsx)

The Live page establishes the 3-column layout convention:

```
Desktop (lg+):    grid grid-cols-3 gap-4
Mobile (<lg):     Tabs component with 3 TabsContent panels
```

Key structural patterns from `live.tsx`:
- Outer container: `flex h-full flex-col gap-4 p-6`
- Desktop grid: `hidden min-h-0 flex-1 lg:grid lg:grid-cols-3 lg:gap-4`
- Each column wrapped in `overflow-auto` or `overflow-hidden` div
- Content extracted into `const` variables, rendered in both desktop grid and mobile tabs
- Page header outside the grid (title + subtitle)

### Recommended Step Creator Layout

```
+------------------------------------------------------------------+
| Page Header: "Step Creator"                                       |
| Subtitle: "Generate pipeline steps from descriptions"             |
+------------------------------------------------------------------+
| Col 1: Input      | Col 2: Editor        | Col 3: Results        |
| +--------------+  | +----------------+   | +----------------+    |
| | Step Name    |  | | [Tab Bar]      |   | | Generation/Test |    |
| | [input]      |  | | Step | Instr.. |   | | results panel  |    |
| |              |  | |                |   | |                |    |
| | Description  |  | | Monaco Editor  |   | |                |    |
| | [textarea]   |  | | (lazy loaded)  |   | |                |    |
| |              |  | |                |   | |                |    |
| | [Generate]   |  | |                |   | |                |    |
| |              |  | | [Test] [Accept]|   | |                |    |
| +--------------+  | +----------------+   | +----------------+    |
+------------------------------------------------------------------+
```

### Responsive Breakpoint Strategy

Following the existing mobile-first pattern:
- **lg+ (1024px+)**: Full 3-column grid
- **Below lg**: Tab-based layout with 3 tabs: "Input", "Editor", "Results"
- Tab switching uses existing `Tabs`/`TabsList` from shadcn/ui

### Column Proportions

The default `grid-cols-3` gives equal 1:1:1 ratio. For the creator, a weighted split is better:

```
Recommendation: grid-cols-[280px_1fr_350px]
```

Rationale:
- Col 1 (Input): Fixed narrow width -- only 2 form fields + button. 280px is sufficient.
- Col 2 (Editor): Flexible/growing -- code editor needs maximum horizontal space.
- Col 3 (Results): Semi-fixed -- results/events need readable width but not as much as editor.

Alternative: `grid-cols-[1fr_2fr_1fr]` for simpler proportional layout.

Decision point: The Live page uses equal `grid-cols-3`. Using weighted columns deviates from that pattern but is more appropriate for an IDE-like interface where the editor panel is the primary workspace.

---

## 2. Monaco Editor Integration

### Package Selection

`@monaco-editor/react` (npm: `@monaco-editor/react`)
- NOT currently in `package.json` -- must be added
- Loads Monaco from CDN by default (no bundler config needed)
- React 19 compatible
- Provides `Editor`, `useMonaco` hook, and `loader` utility

### Lazy Loading Strategy

Double lazy loading for optimal bundle size:

```tsx
// Level 1: React.lazy for the component itself
const MonacoEditor = lazy(() => import('@monaco-editor/react'))

// Level 2: @monaco-editor/react internally lazy-loads Monaco core from CDN
// No additional configuration needed for this
```

Suspense fallback should match editor dimensions:

```tsx
<Suspense fallback={<EditorSkeleton />}>
  <MonacoEditor ... />
</Suspense>
```

EditorSkeleton: A div with `bg-muted animate-pulse rounded-md` matching the editor's `h-[calc(100vh-XXXpx)]` height. Include faint horizontal lines to suggest code.

### Bundle Size Considerations

Add to `vite.config.ts` manualChunks:

```ts
if (id.includes('node_modules/monaco-editor/')) {
  return 'monaco'
}
```

This ensures Monaco core (loaded lazily) doesn't inflate the main bundle. The `@monaco-editor/react` wrapper itself is tiny (~5KB).

### Multi-Model Tab Switching

Use the `path` prop pattern (from Context7 docs) for preserving editor state across tabs:

```tsx
const files = {
  step: {
    path: `${stepName}_step.py`,
    language: 'python',
    value: generatedCode[`${stepName}_step.py`] ?? '',
  },
  instructions: {
    path: `${stepName}_instructions.py`,
    language: 'python',
    value: generatedCode[`${stepName}_instructions.py`] ?? '',
  },
  prompts: {
    path: `${stepName}_prompts.py`,
    language: 'python',
    value: generatedCode[`${stepName}_prompts.py`] ?? '',
  },
  extractions: {
    path: `${stepName}_extraction.py`,
    language: 'python',
    value: generatedCode[`${stepName}_extraction.py`] ?? '',
  },
}

<Editor
  path={files[activeTab].path}
  defaultLanguage={files[activeTab].language}
  defaultValue={files[activeTab].value}
  theme="vs-dark"
  saveViewState={true}  // preserves scroll, selection, undo
  options={{
    automaticLayout: true,
    scrollBeyondLastLine: false,
    minimap: { enabled: false },  // save horizontal space
    fontSize: 13,
    lineNumbers: 'on',
    renderWhitespace: 'selection',
    wordWrap: 'on',
  }}
  onChange={(value) => handleCodeChange(activeTab, value)}
/>
```

### Language Modes

**Deviation from task 49 spec**: Task 49 description mentions `language="yaml"` for the Prompts tab. However, examining the actual generated artifacts in `creator/models.py`, the prompts artifact is `{name}_prompts.py` -- a Python file that registers prompt content via `CREATOR_PROMPTS` list. All 4 artifacts are Python files. Recommendation: Use `language="python"` for all tabs.

### Editor Configuration

```tsx
const editorOptions = {
  automaticLayout: true,      // responsive to container resize
  scrollBeyondLastLine: false, // no extra scroll space
  minimap: { enabled: false }, // save space in constrained layout
  fontSize: 13,
  lineNumbers: 'on',
  renderWhitespace: 'selection',
  wordWrap: 'on',
  readOnly: false,             // editable after generation
  tabSize: 4,                  // Python convention
}
```

---

## 3. Input Form Design (Column 1)

### Form Fields

Two fixed fields (NOT schema-driven like InputForm/FormField in live.tsx):

1. **Step Name** (`Input` component)
   - Label: "Step Name"
   - Placeholder: e.g. "sentiment_analysis"
   - Validation: required, snake_case pattern
   - Helper text: "Used for file naming (snake_case)"

2. **Description** (`Textarea` component)
   - Label: "Description"
   - Placeholder: "Describe what this step should do..."
   - Validation: required, min length
   - Multi-line, auto-grow via `field-sizing-content` (existing Textarea CSS)

### Form Container

Wrapped in a `Card` component (matches live.tsx pipelineColumn pattern):

```tsx
<Card className="flex h-full flex-col overflow-hidden">
  <CardContent className="flex flex-col gap-4 p-4">
    <div className="space-y-2">
      <Label htmlFor="step-name">Step Name</Label>
      <Input id="step-name" placeholder="sentiment_analysis" ... />
    </div>
    <div className="space-y-2">
      <Label htmlFor="step-description">Description</Label>
      <Textarea id="step-description" placeholder="Describe what this step should do..." ... />
    </div>
    <Button onClick={handleGenerate} disabled={!isValid || isGenerating} className="w-full">
      {isGenerating ? <Loader2 className="animate-spin" /> : <Wand2 className="size-4" />}
      {isGenerating ? 'Generating...' : 'Generate'}
    </Button>
  </CardContent>
</Card>
```

### Validation

Simple client-side validation:
- Step name: required, matches `/^[a-z][a-z0-9_]*$/`
- Description: required, min 10 chars
- Show inline errors using `aria-invalid` + `text-destructive` (matches existing Input/Textarea error styling)

---

## 4. Tab Component Design (Editor Tabs)

### Tab Structure

Use existing `Tabs`/`TabsList`/`TabsTrigger`/`TabsContent` from shadcn:

```tsx
<Tabs value={activeTab} onValueChange={setActiveTab}>
  <TabsList>
    <TabsTrigger value="step">Step</TabsTrigger>
    <TabsTrigger value="instructions">Instructions</TabsTrigger>
    <TabsTrigger value="extractions" disabled={!hasExtractions}>
      Extractions
    </TabsTrigger>
    <TabsTrigger value="prompts">Prompts</TabsTrigger>
  </TabsList>

  {/* Single shared Monaco editor below -- NOT inside TabsContent */}
  {/* Tab switching changes the `path` prop, not the entire editor */}
</Tabs>
```

**Important pattern**: The Monaco editor sits OUTSIDE of `TabsContent`. The tabs only control which `path`/value the editor displays. This avoids unmounting/remounting the editor on tab switch (which would lose undo history and cause flickering).

### Tab Labels and Mapping to Artifacts

| Tab Label      | Artifact Key Pattern          | Language |
|---------------|-------------------------------|----------|
| Step          | `{name}_step.py`              | python   |
| Instructions  | `{name}_instructions.py`      | python   |
| Extractions   | `{name}_extraction.py`        | python   |
| Prompts       | `{name}_prompts.py`           | python   |

### Empty/Disabled States

- **Pre-generation**: All tabs disabled, show placeholder message: "Generate a step to start editing"
- **No extraction**: Extractions tab disabled (based on `include_extraction` flag or absence of key in `generated_code`)
- **During generation**: Tabs show skeleton/loading state

---

## 5. Action Button Patterns

### Workflow State Machine

```
idle -> generating -> draft -> testing -> tested -> accepting -> accepted
                                  |                    |
                                  v                    v
                               error               error
```

### Button Layout

Action buttons sit below the editor in column 2:

```tsx
<div className="flex items-center gap-2 border-t pt-3">
  <Button
    variant="outline"
    onClick={handleTest}
    disabled={!hasDraft || isTesting}
  >
    {isTesting ? <Loader2 className="animate-spin" /> : <FlaskConical className="size-4" />}
    {isTesting ? 'Testing...' : 'Test'}
  </Button>

  <Button
    onClick={handleAccept}
    disabled={!isTested || isAccepting}
  >
    {isAccepting ? <Loader2 className="animate-spin" /> : <Check className="size-4" />}
    {isAccepting ? 'Accepting...' : 'Accept'}
  </Button>
</div>
```

### Button States by Workflow Phase

| Phase       | Generate    | Test        | Accept      |
|-------------|-------------|-------------|-------------|
| idle        | enabled     | disabled    | disabled    |
| generating  | disabled+spin | disabled  | disabled    |
| draft       | enabled     | enabled     | disabled    |
| testing     | disabled    | disabled+spin | disabled  |
| tested      | enabled     | enabled     | enabled     |
| accepting   | disabled    | disabled    | disabled+spin |
| accepted    | enabled     | disabled    | disabled    |
| error       | enabled     | enabled*    | disabled    |

*Test re-enabled on error so user can fix code and retry.

### Icon Choices (lucide-react)

- Generate: `Wand2` (creation/magic metaphor)
- Test: `FlaskConical` (testing/experiment metaphor)
- Accept: `Check` (confirmation metaphor)
- Loading: `Loader2` with `animate-spin`

---

## 6. Results Panel Design (Column 3)

### Approach: Dual-Mode Results

The results panel serves two purposes at different stages:

**During generation**: Show pipeline execution progress (generation is a real pipeline run with events streamed via WebSocket).

**After testing**: Show test/sandbox results.

### Generation Phase -- Reusing StepDetailPanel Content

The generate endpoint creates a real `PipelineRun` and broadcasts `run_created` via WebSocket. The existing `useWebSocket`, `useEvents`, `useSteps` hooks can track progress. The results panel can show:

1. `EventStream` component (from live.tsx) during generation -- shows real-time events
2. `StepTimeline` component after generation completes -- shows the 4 creator pipeline steps

**Refactoring recommendation**: Extract the inner `StepContent` component from `StepDetailPanel.tsx` into a separate file so it can be rendered inline (not inside a Sheet). Current structure:

```
StepDetailPanel (public) -> Sheet wrapper
  StepContent (private) -> the actual content with tabs
```

Proposed:
```
StepContent (new export) -> reusable content component
StepDetailPanel (public) -> Sheet wrapper around StepContent (unchanged API)
CreatorResultsPanel (new) -> inline wrapper around StepContent for creator
```

### Test Results Phase

Test results come from `POST /api/creator/test/{draft_id}` returning `TestResponse`:

```typescript
interface TestResponse {
  import_ok: boolean
  security_issues: string[]
  sandbox_skipped: boolean
  output: string
  errors: string[]
  modules_found: string[]
  draft_status: string
}
```

Display as a structured card:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Test Results</CardTitle>
    <Badge variant={testResults.import_ok ? 'secondary' : 'destructive'}>
      {testResults.import_ok ? 'Pass' : 'Fail'}
    </Badge>
  </CardHeader>
  <CardContent>
    {/* Import status */}
    {/* Security issues (if any) */}
    {/* Output (pre-formatted) */}
    {/* Errors (if any, in destructive styling) */}
    {/* Modules found (badge list) */}
  </CardContent>
</Card>
```

### Results Panel State Machine

| Workflow Phase | Results Panel Shows                  |
|---------------|--------------------------------------|
| idle          | Empty state: "Generate a step to see results" |
| generating    | EventStream (real-time pipeline events) |
| draft         | Generation complete summary          |
| testing       | Loading spinner                      |
| tested        | TestResponse card                    |
| accepting     | Loading spinner                      |
| accepted      | AcceptResponse card (files written)  |
| error         | Error details with retry guidance    |

---

## 7. Responsive Considerations

### Desktop (lg+, 1024px+)

- 3-column grid with weighted columns
- Monaco editor takes maximum available height
- All panels visible simultaneously

### Tablet/Mobile (<1024px)

Following live.tsx pattern:

```tsx
<Tabs defaultValue="input" className="flex min-h-0 flex-1 flex-col">
  <TabsList>
    <TabsTrigger value="input">Input</TabsTrigger>
    <TabsTrigger value="editor">Editor</TabsTrigger>
    <TabsTrigger value="results">Results</TabsTrigger>
  </TabsList>

  <TabsContent value="input">{inputColumn}</TabsContent>
  <TabsContent value="editor">{editorColumn}</TabsContent>
  <TabsContent value="results">{resultsColumn}</TabsContent>
</Tabs>
```

### Monaco on Small Screens

- `wordWrap: 'on'` prevents horizontal scrolling
- `minimap: { enabled: false }` saves space
- `automaticLayout: true` responds to container resize
- Minimum viable editor height: `min-h-[300px]` on mobile

### Touch Considerations

- All buttons meet 44x44px minimum tap target (existing Button component sizes handle this)
- Tab triggers have adequate spacing for touch
- Monaco has built-in touch support

---

## 8. Loading States

### Monaco Lazy Load

```tsx
function EditorSkeleton() {
  return (
    <div className="flex h-full flex-col gap-1 rounded-md bg-muted p-4">
      {/* Simulated code lines */}
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-muted-foreground/10"
          style={{ width: `${40 + Math.random() * 50}%` }}
        />
      ))}
    </div>
  )
}
```

### Generate Mutation (Async)

- Generate button: `<Loader2 className="animate-spin" />` + "Generating..."
- Results panel: `EventStream` showing real-time events from WebSocket
- Editor panel: Skeleton until generation completes, then populated with code

### Test Mutation

- Test button: Spinner + "Testing..."
- Results panel: Pulse skeleton replacing previous content
- Duration: Can take up to 60s (sandbox timeout)

### Accept Mutation

- Accept button: Spinner + "Accepting..."
- Duration: Usually fast (file writes + DB operations)

---

## 9. Component Hierarchy

### Proposed File Structure

```
src/routes/creator.tsx                    -- Route component (main page)
src/components/creator/
  CreatorInputForm.tsx                    -- Col 1: name + description + generate button
  CreatorEditor.tsx                       -- Col 2: tabs + Monaco + action buttons
  CreatorResultsPanel.tsx                 -- Col 3: results display
  EditorSkeleton.tsx                      -- Loading fallback for Monaco
  TestResultsCard.tsx                     -- Sandbox test results display
  AcceptResultsCard.tsx                   -- Integration results display
src/api/creator.ts                        -- API hooks (useGenerateStep, useTestDraft, etc.)
```

### Component Props Flow

```
StepCreator (route)
  |-- manages: workflow state, generated code, active draft
  |
  +-- CreatorInputForm
  |     props: stepName, description, onGenerate, isGenerating
  |
  +-- CreatorEditor
  |     props: generatedCode, activeTab, onTabChange, onCodeChange,
  |            onTest, onAccept, workflowState
  |
  +-- CreatorResultsPanel
        props: activeRunId, testResults, acceptResults, workflowState
```

### State Management

Local `useState` in the route component (matches live.tsx pattern -- no Zustand for page-specific state):

```typescript
// Workflow state
const [workflowState, setWorkflowState] = useState<WorkflowState>('idle')

// Form inputs
const [stepName, setStepName] = useState('')
const [description, setDescription] = useState('')

// Generation outputs
const [activeDraftId, setActiveDraftId] = useState<number | null>(null)
const [activeRunId, setActiveRunId] = useState<string | null>(null)
const [generatedCode, setGeneratedCode] = useState<Record<string, string>>({})

// Editor state
const [activeTab, setActiveTab] = useState<string>('step')
const [codeOverrides, setCodeOverrides] = useState<Record<string, string>>({})

// Results
const [testResults, setTestResults] = useState<TestResponse | null>(null)
const [acceptResults, setAcceptResults] = useState<AcceptResponse | null>(null)
```

---

## 10. Sidebar Navigation Update

### New Nav Item

Add to `navItems` array in `Sidebar.tsx`:

```typescript
import { Wand2 } from 'lucide-react'

const navItems: NavItem[] = [
  { to: '/', label: 'Runs', icon: List },
  { to: '/live', label: 'Live', icon: Play },
  { to: '/prompts', label: 'Prompts', icon: FileText },
  { to: '/pipelines', label: 'Pipelines', icon: Box },
  { to: '/creator', label: 'Creator', icon: Wand2 },  // NEW
]
```

Icon rationale: `Wand2` (magic wand) conveys code generation/creation. Alternatives considered: `Sparkles` (too decorative), `Code` (ambiguous), `Hammer` (too construction-focused).

---

## 11. API Layer Requirements

### Required Hooks (src/api/creator.ts)

```typescript
// Mutations
useGenerateStep()     // POST /api/creator/generate -> 202
useTestDraft()        // POST /api/creator/test/{draft_id}
useAcceptDraft()      // POST /api/creator/accept/{draft_id}

// Queries
useDrafts()           // GET /api/creator/drafts
useDraft(draftId)     // GET /api/creator/drafts/{draft_id}
```

### Backend API Gap

`GET /api/creator/drafts/{draft_id}` returns `DraftItem` which does NOT include `generated_code` or `test_results`. Task 48 summary recommendation #5 explicitly deferred this. The frontend needs a `DraftDetail` response model that includes these fields, or a separate endpoint.

**Options**:
1. Add a `DraftDetail` Pydantic model and `/drafts/{id}/detail` endpoint
2. Extend existing `GET /drafts/{id}` to include `generated_code` + `test_results`
3. Frontend stores generated code locally and only sends overrides to test endpoint

Option 3 is viable because:
- Generate returns `run_id` -- frontend can track via WS and get code from draft after completion
- Test endpoint already accepts `code_overrides` relative to stored `generated_code`
- But we still need `generated_code` from the backend to populate the editor after a page refresh

Recommendation: Option 2 -- extend `GET /drafts/{id}` with an optional `?include=code` query parameter.

### Query Key Extension

```typescript
export const queryKeys = {
  // ... existing keys
  creator: {
    all: ['creator'] as const,
    drafts: () => ['creator', 'drafts'] as const,
    draft: (draftId: number) => ['creator', 'drafts', draftId] as const,
  },
}
```

---

## 12. Deviations from Task 49 Spec

| Spec Item | Deviation | Rationale |
|-----------|-----------|-----------|
| Prompts tab: `language="yaml"` | All tabs use `language="python"` | Generated prompts artifact is `{name}_prompts.py`, a Python file |
| Equal 3-column grid | Weighted `grid-cols-[280px_1fr_350px]` | IDE-like interface needs larger editor panel |
| StepDetailPanel direct reuse | Extract StepContent for inline rendering | StepDetailPanel is Sheet-wrapped; column 3 needs inline component |
| Simple input fields | Same but with snake_case validation | Step name must be valid Python identifier for file naming |

---

## 13. Accessibility Checklist

- [ ] All form inputs have associated `Label` components
- [ ] Error messages use `aria-invalid` + `role="alert"`
- [ ] Tab navigation follows WAI-ARIA Tabs pattern (handled by Radix)
- [ ] Generate/Test/Accept buttons have descriptive text (not icon-only)
- [ ] Loading states announce via `aria-busy` on containers
- [ ] Monaco editor has `aria-label="Code editor"` via options
- [ ] Empty/disabled states have explanatory text for screen readers
- [ ] Color alone does not convey status (badges include text labels)
