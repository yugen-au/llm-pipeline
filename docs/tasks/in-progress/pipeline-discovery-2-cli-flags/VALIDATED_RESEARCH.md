# Research Summary

## Executive Summary

Validated research from two agents (CLI & Module Loading, App Factory Integration) covering --pipelines and --model CLI flag design. The --model flag design is fully resolved with high confidence -- follows existing patterns exactly. The --pipelines flag has 2 documented open questions plus 4 additional gaps surfaced during validation: seed_prompts for CLI-loaded modules, error severity for explicit module failures, interaction with auto_discover flag, and helper function placement. Found 3 pre-existing test failures in test_cli.py that task 2 must account for. Both research files are internally consistent on --model but diverge on --pipelines module format (step-1 assumes PIPELINE_REGISTRY dict as contract, step-2 presents it as open question).

## Domain Findings

### --model Flag (Fully Resolved)
**Source:** step-1 sections 3/6, step-2 sections 2/5

Prod: `create_app(db_path=args.db, default_model=args.model)`. Dev: set `os.environ["LLM_PIPELINE_MODEL"] = args.model`. create_app already reads LLM_PIPELINE_MODEL as fallback (app.py L186). No changes to `_create_dev_app` needed. Fallback chain: CLI flag > env var > None (warn at startup, 422 at execution). Verified against actual code -- no gaps.

### --pipelines Module Loading (Open Questions)
**Source:** step-1 section 4, step-2 sections 6/7

Two approaches documented with trade-offs table. Step-1 assumes PIPELINE_REGISTRY dict contract (section 4 line 96-99). Step-2 presents both as open (section 7). These are inconsistent -- needs CEO decision.

### Dev Mode Env Var Bridge
**Source:** step-1 sections 4/6, step-2 section 6

`LLM_PIPELINE_PIPELINES` comma-separated env var for dev mode. Matches established pattern (--db -> LLM_PIPELINE_DB). Verified: dotenv is loaded at main() entry, so .env-based values are available. Pattern is sound.

### Helper Function Design
**Source:** step-1 section 4, step-2 section 8

`_load_pipeline_modules(module_paths, model)` returns `(pipeline_reg, introspection_reg)` matching `_discover_pipelines` shape. Reuses `_make_pipeline_factory`. Both agents agree on shape but placement is ambiguous -- step-1 says app.py, but CLI would import a private function. No resolution.

### Test Impact
**Source:** step-2 section 9, verified by running test suite

Prod mode `create_app(db_path=args.db)` will gain `default_model=args.model` kwarg -- breaks `TestDbFlag::test_db_none_by_default` assertion `mock_ca.assert_called_once_with(db_path=None)`. 3 pre-existing test failures already exist:
- `TestCreateDevApp::test_reads_env_var_and_passes_to_create_app` -- asserts `create_app(db_path=X)` but actual call is `create_app(db_path=X, database_url=None)`
- `TestCreateDevApp::test_passes_none_when_env_var_absent` -- same root cause
- `TestDevModeWithFrontend::test_uvicorn_no_reload_in_vite_mode` -- asserts reload=False but actual is True

### seed_prompts Gap
**Source:** app.py L84-93, step-1 section 4 (omits seed_prompts), step-2 section 8 (omits seed_prompts)

`_discover_pipelines` calls `seed_prompts(engine)` for each class. Neither research doc mentions seed_prompts in the _load_pipeline_modules helper. CLI-loaded pipelines would NOT get seed_prompts called. But seed_prompts requires engine, which is only available inside create_app after DB init. This creates a design tension: the helper runs before create_app (to build registries to pass in), but seed_prompts needs engine (created inside create_app).

### Error Severity Gap
**Source:** step-1 section 4 line 110 "don't crash", step-2 section 6

Both agents recommend warning + continue for bad imports, matching auto-discovery convention. But --pipelines is explicit user intent. Silently skipping a user-requested module is poor UX. Different error model than auto-discovery.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| (pending) | (pending) | (pending) |

## Assumptions Validated
- [x] --model flag follows exact same pattern as --db (prod: kwarg passthrough, dev: env var bridge)
- [x] create_app already reads LLM_PIPELINE_MODEL as fallback -- no changes to create_app needed for --model
- [x] _make_pipeline_factory in app.py is reusable for CLI-loaded modules (verified signature L24-46)
- [x] to_snake_case utility exists in naming.py and handles consecutive-caps correctly (double-regex)
- [x] Dev mode env var bridge pattern is established and sound (dotenv loaded at main() entry)
- [x] Merge order {**discovered, **(explicit or {})} correctly feeds CLI registries as explicit overrides
- [x] PipelineConfig.__init__ requires model: str with no default (pipeline.py L209-211)
- [x] importlib.import_module is not currently used in codebase -- new dependency for --pipelines (step-1 section 7)
- [x] Factory closure absorbs extra kwargs safely via **kwargs (confirmed in code L37)
- [x] Existing prod mode tests use exact assert_called_once_with(db_path=...) -- WILL break when adding default_model kwarg

## Open Items
- **seed_prompts for CLI-loaded modules**: engine not available when helper runs pre-create_app. Options: (a) skip seed_prompts for CLI modules (document limitation), (b) move module loading inside create_app via new param, (c) two-pass: build registries pre-create_app, seed_prompts post-create_app via lifecycle hook
- **3 pre-existing test failures in test_cli.py**: not caused by task 2 but must be addressed to get green test suite after implementation
- **PipelineIntrospector single-regex naming bug**: carried forward from task 1 validation, still unresolved

## Recommendations for Planning
1. --model implementation can proceed immediately -- no open questions, fully resolved
2. --pipelines requires CEO decisions on Q1-Q5 before planning can finalize
3. Fix the 3 pre-existing test failures as part of task 2 scope (they're in the same file being modified)
4. For seed_prompts: recommend passing module_paths to create_app as a new param, letting create_app handle import + seed in sequence after engine init. Keeps CLI thin, create_app owns all registration logic
5. Consider making _load_pipeline_modules a public function in app.py (no underscore) since CLI is a legitimate external consumer
6. Test strategy should switch from assert_called_once_with (exact match) to asserting specific kwargs individually, to be resilient to future param additions
