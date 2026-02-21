# IMPLEMENTATION - STEP 3: CONFIGURE TYPESCRIPT
**Status:** completed

## Summary
Replaced Vite 7 scaffold default tsconfig files with the 3-file pattern: solution file (`tsconfig.json`) with project references, app config (`tsconfig.app.json`) targeting ES2020/DOM/JSX, and node config (`tsconfig.node.json`) targeting vite.config.ts and eslint.config.ts. Added `@/*` path alias to solution file and app config for shadcn/ui compatibility.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/tsconfig.json, llm_pipeline/ui/frontend/tsconfig.app.json, llm_pipeline/ui/frontend/tsconfig.node.json
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/tsconfig.json`
Added `compilerOptions.paths` for `@/*` path alias. Structure unchanged (solution file with references).

```
# Before
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}

# After
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ],
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### File: `llm_pipeline/ui/frontend/tsconfig.app.json`
Changed target from ES2022 to ES2020, lib from ES2022 to ES2020. Added `baseUrl: "."` and `paths: {"@/*": ["./src/*"]}` for path alias resolution. All other options preserved from scaffold.

```
# Before
"target": "ES2022",
"lib": ["ES2022", "DOM", "DOM.Iterable"],
(no baseUrl or paths)

# After
"target": "ES2020",
"lib": ["ES2020", "DOM", "DOM.Iterable"],
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

### File: `llm_pipeline/ui/frontend/tsconfig.node.json`
Added `eslint.config.ts` to `include` array. All other options unchanged from scaffold.

```
# Before
"include": ["vite.config.ts"]

# After
"include": ["vite.config.ts", "eslint.config.ts"]
```

## Decisions
### ES2020 target for app config
**Choice:** ES2020 instead of scaffold default ES2022
**Rationale:** Plan specifies ES2020 explicitly. Broader browser compatibility with negligible impact since Vite handles transpilation anyway.

### baseUrl required for paths
**Choice:** Added `baseUrl: "."` alongside `paths` in tsconfig.app.json
**Rationale:** TypeScript requires `baseUrl` when `paths` is used in a non-solution tsconfig. Without it, path alias resolution fails. The solution file (`tsconfig.json`) does not need `baseUrl` since it only serves as reference for IDEs.

### Preserved scaffold linting options
**Choice:** Kept `noUnusedLocals`, `noUnusedParameters`, `erasableSyntaxOnly`, `noUncheckedSideEffectImports`
**Rationale:** These strict checks from the Vite 7 scaffold are beneficial. Plan did not specify removing them.

## Verification
[x] `tsc -b --noEmit` runs without tsconfig parsing errors (only TS2307 for deleted App.tsx, expected)
[x] Path alias `@/*` defined in both solution file and app config
[x] tsconfig.node.json includes both vite.config.ts and eslint.config.ts
[x] No DOM lib in tsconfig.node.json
[x] moduleResolution bundler in both app and node configs
[x] verbatimModuleSyntax true in both configs
[x] noEmit true in both configs
[x] strict true in both configs
