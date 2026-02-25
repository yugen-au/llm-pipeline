# JSON Diff Library Research

## 1. Library Comparison

### 1.1 microdiff (RECOMMENDED)

| Attribute | Value |
|---|---|
| Version | 1.5.0 (Dec 24, 2024) |
| Bundle (unpacked) | 12.6 KB |
| Bundle (minified) | ~0.9 KB |
| Bundle (gzip) | ~0.5 KB |
| Dependencies | 0 |
| TypeScript | Native types (included) |
| Module format | ESM + CJS dual export |
| Tree-shaking | Yes (ESM, single default export) |
| Stars / Issues | 3.8k / 2 open |
| License | MIT |

**Diff output format:**
```typescript
// Discriminated union - perfect for switch-based rendering
export interface DifferenceCreate {
  type: "CREATE"
  path: (string | number)[]
  value: any
}
export interface DifferenceRemove {
  type: "REMOVE"
  path: (string | number)[]
  oldValue: any
}
export interface DifferenceChange {
  type: "CHANGE"
  path: (string | number)[]
  value: any
  oldValue: any
}
export type Difference = DifferenceCreate | DifferenceRemove | DifferenceChange
```

**Output example:**
```typescript
diff(
  { user: { name: "Alice", age: 30 }, tags: ["a"] },
  { user: { name: "Bob", age: 30 }, role: "admin" }
)
// Returns:
// [
//   { type: "CHANGE", path: ["user", "name"], value: "Bob", oldValue: "Alice" },
//   { type: "REMOVE", path: ["tags"], oldValue: ["a"] },
//   { type: "CREATE", path: ["role"], value: "admin" }
// ]
```

**Strengths:**
- Smallest bundle by a large margin (<1KB)
- Native discriminated union types align perfectly with our rendering needs
- Flat path-based output is easy to group into a tree structure for recursive rendering
- `cyclesFix: false` option for parsed JSON (no cycles) = faster
- Zero dependencies = zero supply chain risk
- Performance: benchmarks show fastest among all competitors

**Limitations:**
- Array diffing is index-based (no key-based matching) - acceptable for pipeline context objects which are primarily key-value maps
- No built-in formatters (we build our own - this is actually a strength since we need full control for shadcn/Tailwind styling)

---

### 1.2 jsondiffpatch

| Attribute | Value |
|---|---|
| Version | 0.7.3 (Mar 31, 2025) |
| Bundle (unpacked) | 159 KB (57 files) |
| Bundle (gzip) | ~16 KB |
| Dependencies | 1 (@dmsnell/diff-match-patch) |
| TypeScript | Native types (included) |
| Module format | ESM-only |
| Tree-shaking | Partial (multiple exports/formatters) |
| Stars / Issues | 5.3k / 41 open |
| License | MIT |

**Diff output format:** Compact nested delta
```typescript
type Delta =
  | AddedDelta      // [value]
  | ModifiedDelta   // [oldValue, newValue]
  | DeletedDelta    // [value, 0, 0]
  | ObjectDelta     // { [key]: Delta }
  | ArrayDelta      // { _t: "a", [index]: Delta }
  | MovedDelta      // [value, destIndex, 3]
  | TextDiffDelta   // [diffString, 0, 2]
  | undefined
```

**Strengths:**
- Most mature and feature-rich library (5.3k stars)
- Built-in HTML formatter with CSS for visual diffs
- Built-in type guard functions (isAddedDelta, isModifiedDelta, etc.)
- Text diff support via diff-match-patch
- Smart array diffing using LCS algorithm

**Limitations:**
- 16KB gzip is 32x larger than microdiff
- Compact delta format is hard to map to custom React rendering (arrays of 2 or 3 items with positional meaning)
- Built-in HTML formatter uses `dangerouslySetInnerHTML` approach, not React-native rendering
- HTML formatter CSS would conflict with Tailwind
- ESM-only (not a problem for Vite, but less flexible)
- The one dependency (@dmsnell/diff-match-patch) is unnecessary for our use case (we diff JSON objects, not text)

**Verdict:** Overkill. The built-in formatters are opinionated and don't integrate with shadcn/Tailwind. The delta format adds rendering complexity. Bundle is unnecessarily large for our needs.

---

### 1.3 fast-json-patch

| Attribute | Value |
|---|---|
| Version | 3.1.1 (Mar 24, 2022) |
| Bundle (unpacked) | 159 KB |
| Dependencies | 0 |
| TypeScript | Native types (included) |
| Module format | ESM + CJS |
| Stars / Issues | not checked |
| License | MIT |

**Diff output format:** RFC 6902 JSON Patch
```typescript
interface Operation {
  op: "add" | "remove" | "replace" | "move" | "copy" | "test"
  path: string  // JSON Pointer (e.g., "/user/name")
  value?: any
}
```

**Critical limitation:** RFC 6902 does NOT include `oldValue` in operations. For visual diff rendering, we need to show "before -> after" for changes. This library would require a separate pass over the original object to retrieve old values, defeating the purpose.

**Additional concerns:**
- Last publish: March 2022 (4 years old)
- Designed for PATCHING, not visual DIFFING
- JSON Pointer path format ("/a/b/c") needs parsing vs microdiff's array format

**Verdict:** DISQUALIFIED. Missing oldValue makes it unsuitable for visual diff rendering.

---

### 1.4 json-diff-ts

| Attribute | Value |
|---|---|
| Version | 4.9.1 (Jun 2026) |
| Bundle (unpacked) | 190 KB |
| Dependencies | 0 |
| TypeScript | Native types (included, TypeScript-first) |
| Module format | ESM + CJS |
| Tree-shaking | Yes (tsup build) |
| Stars / Issues | 181 / 1 open |
| License | MIT |

**Diff output format:** Nested tree
```typescript
enum Operation { REMOVE = 'REMOVE', ADD = 'ADD', UPDATE = 'UPDATE' }
interface IChange {
  type: Operation
  key: string
  embeddedKey?: string
  value?: any
  oldValue?: any
  changes?: IChange[]  // nested children
}
```

**Strengths:**
- TypeScript-first, zero dependencies
- Nested tree output maps naturally to recursive React rendering
- Key-based array matching via `embeddedObjKeys`
- `atomizeChangeset()` for flat path format when needed
- Very actively maintained (latest v4.9.1)
- `applyChangeset` and `revertChangeset` utilities

**Limitations:**
- 190KB unpacked is significantly larger than microdiff (12.6KB)
- Nested output requires recursive component even for simple flat changes
- `changes` being `IChange[] | undefined` adds null-checking noise
- Key-based array matching (main differentiator) is unnecessary for pipeline context objects
- Less battle-tested (181 stars vs microdiff's 3.8k)

**Verdict:** Strong alternative. Better if pipeline contexts had complex array structures needing key-based matching. For our use case (primarily key-value maps), microdiff's simpler output is preferable.

---

### 1.5 deep-diff

| Attribute | Value |
|---|---|
| Version | 1.0.2 (Aug 2018) |
| Bundle (minified) | 5.5 KB |
| Bundle (gzip) | 1.9 KB |
| Bundle (unpacked) | 542 KB (40 files, mostly tests) |
| Dependencies | 0 |
| TypeScript | @types/deep-diff (separate, stale) |
| Module format | CJS only, NO ESM |
| Stars / Issues | not checked |
| License | MIT |

**Diff output format:**
```typescript
// From @types/deep-diff (DefinitelyTyped)
interface DiffNew<RHS> { kind: 'N'; path?: any[]; rhs: RHS }
interface DiffDeleted<LHS> { kind: 'D'; path: any[]; lhs: LHS }
interface DiffEdit<LHS, RHS> { kind: 'E'; path: any[]; lhs: LHS; rhs: RHS }
interface DiffArray<LHS, RHS> { kind: 'A'; path: any[]; index: number; item: Diff<LHS, RHS> }
```

**Verdict:** DISQUALIFIED.
- No ESM support (Vite requires ESM or bundler workarounds)
- TypeScript types are separate and stale (last updated 2+ years ago)
- Last publish: 2018 (8 years old, effectively abandoned)
- `kind` uses single-letter codes ('N','D','E','A') instead of readable strings
- Our tsconfig has `verbatimModuleSyntax: true` which conflicts with CJS-only packages

---

## 2. Library Recommendation

**Primary: microdiff v1.5.0**

Rationale:
1. **Bundle impact:** 0.5KB gzip adds negligible weight to the frontend bundle
2. **TypeScript:** Native discriminated union (`DifferenceCreate | DifferenceRemove | DifferenceChange`) enables exhaustive switch rendering with zero type gymnastics
3. **Output format:** Flat `path[]` arrays are easy to reconstruct into a tree structure for collapsible rendering, while also trivial to render as a flat list
4. **Performance:** Fastest library in benchmarks; `cyclesFix: false` for parsed JSON makes it even faster
5. **Maintenance:** Active development, 3.8k stars, MIT license, zero dependencies
6. **Compatibility:** ESM + CJS, works seamlessly with Vite + strict TS config

**Fallback: json-diff-ts v4.9.x** if array key-based matching becomes necessary in the future.

---

## 3. Rendering Approach

### 3.1 Recommended: Grouped Tree with Collapsible Nodes

The flat diff output from microdiff needs to be grouped by path segments to form a tree for rendering. This gives us full control over the visual output within the shadcn/Tailwind design system.

**Tree reconstruction algorithm:**
```
1. Compute diffs: microdiff(before, after, { cyclesFix: false })
2. Group by path[0] (first segment) into a Map<string, Difference[]>
3. For each group:
   a. If all diffs in group have path.length === 1 -> render as leaf (direct change)
   b. If diffs have path.length > 1 -> create branch node, recurse with path.slice(1)
4. Render unchanged keys from `after` object as grey/muted
```

**Internal tree type:**
```typescript
type DiffTreeNode = {
  key: string
  diff?: Difference       // leaf: direct change at this key
  children?: DiffTreeNode[]  // branch: nested changes
  unchangedValue?: unknown   // key exists in both but unchanged
}
```

### 3.2 Why Not Flat List

A flat list of changes (path -> value) loses structural context. Pipeline context objects are nested (e.g., `context.extraction.results.items`). Showing changes within their structural hierarchy makes it easier to understand what changed at each step.

### 3.3 Why Not Side-by-Side

Side-by-side requires 2x the horizontal space. The ContextEvolution panel is already constrained to `w-80` (320px) in the run detail layout. An inline diff (single column, additions/removals/changes inline) is the only viable approach at this width.

### 3.4 Collapsible Tree Nodes

Each non-leaf node should be collapsible:
- Nodes at depth < maxDepth: expanded by default
- Nodes at depth >= maxDepth: collapsed by default
- User can toggle any node
- Collapsed nodes show summary: `{3 changes}` or `{...}` indicator
- Use local `useState` per collapsible node (or a single `Set<string>` of expanded paths at the JsonDiff level)

---

## 4. TypeScript Patterns

### 4.1 Component Props

```typescript
interface JsonDiffProps {
  before: Record<string, unknown>
  after: Record<string, unknown>
  maxDepth?: number  // default: 3
}
```

Generic typing (`<T extends Record<string, unknown>>`) was considered but adds no value since `ContextSnapshot.context_snapshot` is already typed as `Record<string, unknown>`. Keeping props simple.

### 4.2 Discriminated Union for Rendering

microdiff's `Difference` type is already a discriminated union on the `type` field. This enables exhaustive `switch` in the renderer:

```typescript
function renderLeaf(diff: Difference): ReactNode {
  switch (diff.type) {
    case "CREATE":
      return <AddedValue value={diff.value} />
    case "REMOVE":
      return <RemovedValue oldValue={diff.oldValue} />
    case "CHANGE":
      return <ChangedValue oldValue={diff.oldValue} newValue={diff.value} />
  }
}
```

TypeScript will flag if a case is missing (exhaustive check with `noFallthroughCasesInSwitch: true` in tsconfig, which is already enabled).

### 4.3 Recursive Rendering Types

```typescript
interface DiffNodeProps {
  node: DiffTreeNode
  depth: number
  maxDepth: number
}

// Each level renders either a leaf or recurses into children
function DiffNode({ node, depth, maxDepth }: DiffNodeProps) {
  // ...
}
```

### 4.4 Color Coding Classes

```typescript
const diffColors = {
  CREATE: 'bg-green-950/50 text-green-400',           // green background
  REMOVE: 'bg-red-950/50 text-red-400 line-through',  // red + strikethrough
  CHANGE: 'bg-yellow-950/50 text-yellow-400',          // yellow background
} as const satisfies Record<Difference['type'], string>
```

Uses `satisfies` for type safety while preserving literal types. These Tailwind classes work within the existing dark theme design system.

---

## 5. Performance Considerations

### 5.1 Diff Computation Memoization

```typescript
const diffs = useMemo(
  () => diff(before, after, { cyclesFix: false }),
  [before, after]
)
```

Since `before` and `after` come from TanStack Query (new object reference per fetch), React's shallow comparison will re-compute on every query refetch. For terminal runs (completed/failed), `staleTime: Infinity` means no refetch, so the memo is stable. For active runs, refetches happen every 3s but context snapshots are append-only (new step = new snapshot, previous snapshots don't change).

**Optimization:** The tree reconstruction should also be memoized:

```typescript
const tree = useMemo(() => buildDiffTree(diffs, after), [diffs, after])
```

### 5.2 Virtual Scrolling: NOT NEEDED

Pipeline context objects typically have 10-50 top-level keys, nested 2-4 levels deep. With `maxDepth=3`, the total visible DOM nodes rarely exceed ~200. This is well within React's efficient rendering range.

Virtual scrolling (e.g., react-window, @tanstack/react-virtual) adds complexity and should only be introduced if profiling reveals performance issues with context objects exceeding ~500 keys.

### 5.3 React.memo on Node Components

Wrap `DiffNode` in `React.memo` to prevent unnecessary re-renders when sibling nodes collapse/expand:

```typescript
const DiffNode = memo(function DiffNode({ node, depth, maxDepth }: DiffNodeProps) {
  // ...
})
```

Since `DiffTreeNode` objects are created fresh during tree construction, the memo is effective only if the tree is stable (memoized via `useMemo`).

### 5.4 Collapse State Management

Two approaches considered:

**A. Per-node useState:** Each collapsible node manages its own `[expanded, setExpanded]`. Simple but creates many state holders.

**B. Single Set at root (recommended):** `JsonDiff` manages a `Set<string>` of expanded path keys. Pass `isExpanded(path)` and `toggleExpand(path)` down. Fewer state updates, easier to implement "expand all" / "collapse all".

```typescript
const [expanded, setExpanded] = useState<Set<string>>(() => {
  // Initialize: expand all paths at depth < maxDepth
  return computeInitialExpanded(tree, maxDepth)
})
```

---

## 6. Integration with Existing Codebase

### 6.1 Existing ContextEvolution Component

Current `ContextEvolution.tsx` renders raw JSON via `JSON.stringify(snapshot.context_snapshot, null, 2)` in `<pre>` tags. Task 34's SUMMARY explicitly states: "Task 36 should replace this with a collapsible JsonDiff view. The ContextEvolutionProps interface (snapshots, isLoading, isError) and ScrollArea structure can be preserved as the scaffold."

**Integration plan:**
1. Create `src/components/JsonDiff.tsx` (new, reusable)
2. Modify `src/components/runs/ContextEvolution.tsx` to import and use `JsonDiff`
3. Preserve `ContextEvolutionProps` interface and loading/error/empty states
4. Replace `<pre>{JSON.stringify(...)}</pre>` with `<JsonDiff before={prev} after={curr} />`
5. First snapshot (step 1) has no "before" - show as all-additions or raw JSON

### 6.2 Existing Package Dependencies

The project already uses:
- React 19, TypeScript 5.9, Vite 7.3
- shadcn/ui components (Card, ScrollArea, Badge, etc.)
- Tailwind CSS v4.2
- TanStack Query + Router
- Vitest for testing

microdiff has zero conflicts with any of these. It adds ~0.5KB to the bundle.

### 6.3 File Placement

Per task description:
- `src/components/JsonDiff.tsx` - reusable diff component
- `src/components/runs/ContextEvolution.tsx` - modified to use JsonDiff

The `JsonDiff` component goes in `src/components/` (not `src/components/runs/`) because it is reusable across the app, not run-specific.

---

## 7. Existing Package Check

Scanned `package.json` dependencies. No JSON diff library is currently installed. The following existing packages are relevant:
- `clsx` + `tailwind-merge` - for conditional class composition on diff color classes
- `lucide-react` - for collapse/expand chevron icons
- `radix-ui` - could use Collapsible primitive for animated expand/collapse, but simple CSS transitions are lighter
- `zustand` - NOT needed for diff state (component-local state is sufficient)

---

## 8. Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| microdiff abandoned | Low (active, last release Dec 2024) | Library is 100 LOC, could inline if needed |
| Pipeline context too large for DOM | Low (typical: 10-50 keys) | Add virtual scrolling later if profiling shows issues |
| Array index-based diff confusing for array changes | Medium | Pipeline contexts are primarily key-value maps; array values shown as whole-value changes |
| Color classes don't render correctly in dark theme | Low | Use Tailwind opacity modifiers (e.g., `bg-green-950/50`) which work in both themes |
