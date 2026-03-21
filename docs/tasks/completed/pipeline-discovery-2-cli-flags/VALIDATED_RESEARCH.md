# Research Summary

## Executive Summary

Validated research from two agents (CLI & Module Loading, App Factory Integration) covering --pipelines and --model CLI flag design. All 5 open questions resolved via CEO decisions. The --model flag follows existing patterns exactly (prod: kwarg passthrough, dev: env var bridge). The --pipelines flag will scan modules for PipelineConfig subclasses (not PIPELINE_REGISTRY dict), use repeatable argparse append syntax, pass module_paths into create_app for engine-dependent seed_prompts, and treat explicit import failures as fatal (exit 1). 3 pre-existing test failures in test_cli.py will be fixed in task 2 scope. Found 3 pre-existing test failures in test_cli.py confirmed by running test suite.

## Domain Findings

### --model Flag (Fully Resolved)
**Source:** step-1 sections 3/6, step-2 sections 2/5

Prod: `create_app(db_path=args.db, default_model=args.model)`. Dev: set `os.environ["LLM_PIPELINE_MODEL"] = args.model`. create_app already reads LLM_PIPELINE_MODEL as fallback (app.py L186). No changes to `_create_dev_app` needed for model -- it already picks up env vars. Fallback chain: CLI flag > env var > None (warn at startup, 422 at execution). Verified against actual code -- no gaps.

### --pipelines Module Loading (Resolved: Scan Approach)
**Source:** step-1 section 4, step-2 sections 6/7, CEO decision Q1

**CEO decision: scan for PipelineConfig subclasses** (consistent with entry-point auto-discovery, zero effort for module authors). Step-1's PIPELINE_REGISTRY dict assumption is overridden. Implementation: `importlib.import_module(path)` then `inspect.getmembers(mod, predicate)` filtering for `issubclass(cls, PipelineConfig) and cls is not PipelineConfig and not inspect.isabstract(cls)`. Registry keys derived via `to_snake_case(cls.__name__, strip_suffix="Pipeline")`.

### --pipelines Argument Syntax (Resolved: Repeatable Append)
**Source:** step-1 section 5, step-2 section 6, CEO decision Q2

**CEO decision: repeatable `--pipelines mod1 --pipelines mod2`** (standard argparse append). argparse: `add_argument("--pipelines", action="append", default=None, metavar="MODULE")`. Dev mode env var: `LLM_PIPELINE_PIPELINES` comma-separated, split on comma in `_create_dev_app`.

### Module Loading Inside create_app (Resolved: New Param)
**Source:** seed_prompts gap analysis, CEO decision Q3

**CEO decision: pass module_paths into create_app as new param.** This resolves the seed_prompts design tension -- engine is available inside create_app after DB init. create_app gains `pipeline_modules: Optional[List[str]] = None` param. Module loading + subclass scanning + factory building + seed_prompts all happen inside create_app, after engine init, before registry merge. Merge order: `{**auto_discovered, **module_loaded, **(explicit or {})}`. The _load_pipeline_modules helper lives inside app.py as a private function (no cross-module import needed since CLI just passes paths).

### Error Severity (Resolved: Fatal for Explicit)
**Source:** step-1 section 4, step-2 section 6, CEO decision Q4

**CEO decision: fatal error (exit 1) for failed explicit --pipelines imports.** Rationale: user explicitly requested these modules. Implementation: _load_pipeline_modules raises on import failure (ImportError, no PipelineConfig subclasses found, etc). CLI catches and exits with sys.exit(1) + error message. Inside create_app, the function can raise ValueError which CLI translates to exit 1. Auto-discovery retains warning + skip behavior (unchanged).

### Dev Mode Env Var Bridge
**Source:** step-1 sections 4/6, step-2 section 6

`LLM_PIPELINE_PIPELINES` comma-separated env var for dev mode. Matches established pattern (--db -> LLM_PIPELINE_DB). Verified: dotenv is loaded at main() entry, so .env-based values are available. `_create_dev_app` reads env var, splits on comma, passes to create_app(pipeline_modules=...).

### Test Impact (Resolved: Fix in Task 2)
**Source:** step-2 section 9, verified by running test suite, CEO decision Q5

**CEO decision: fix 3 pre-existing test failures in task 2 scope.** Confirmed failures:
- `TestCreateDevApp::test_reads_env_var_and_passes_to_create_app` -- asserts `create_app(db_path=X)` but actual call is `create_app(db_path=X, database_url=None)`
- `TestCreateDevApp::test_passes_none_when_env_var_absent` -- same root cause
- `TestDevModeWithFrontend::test_uvicorn_no_reload_in_vite_mode` -- asserts reload=False but actual is True

Prod mode tests (`TestDbFlag`) will also break when adding `default_model=args.model` kwarg. Fix strategy: switch from `assert_called_once_with` (exact match) to asserting specific kwargs individually via `mock.call_args.kwargs["key"]`, resilient to future param additions.

### Helper Function Design (Refined by CEO Decisions)
**Source:** step-1 section 4, step-2 section 8, refined by Q3 decision

Since module loading now happens inside create_app (not CLI), `_load_pipeline_modules` stays private in app.py. Signature: `_load_pipeline_modules(module_paths: List[str], model: Optional[str], engine: Engine) -> Tuple[Dict[str, Callable], Dict[str, Type[PipelineConfig]]]`. Reuses `_make_pipeline_factory`. Calls `seed_prompts(engine)` per class (same pattern as `_discover_pipelines`). Raises on import failure (not warning+skip).

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should modules export PIPELINE_REGISTRY dict or be scanned for PipelineConfig subclasses? | Scan for subclasses (consistent with entry-point auto-discovery) | Step-1's dict assumption overridden. Registry keys auto-derived via to_snake_case. No PIPELINE_REGISTRY convention needed. Module authors just define subclasses. |
| Should --pipelines use repeatable append, nargs+, or comma-separated? | Repeatable append (--pipelines mod1 --pipelines mod2) | Standard argparse pattern. No comma-in-path edge cases. Dev mode env var uses comma-separated (consistent with shell convention). |
| Should seed_prompts be called for CLI-loaded modules? Engine not available pre-create_app. | Pass module_paths into create_app as new param | Resolves design tension. create_app handles full lifecycle: import, scan, factory, seed_prompts. CLI stays thin (just passes paths). Helper stays private in app.py. |
| Should failed --pipelines module imports be fatal or warning? | Fatal error (exit 1) -- user explicitly requested it | Different error model than auto-discovery (warning+skip). create_app raises ValueError on module load failure. CLI catches, prints error, exits 1. |
| Should 3 pre-existing test_cli.py failures be fixed in task 2? | Yes, fix in task 2 scope | Switch to individual kwarg assertions. Fix stale reload assertion. Ensures clean test suite after implementation. |

## Assumptions Validated
- [x] --model flag follows exact same pattern as --db (prod: kwarg passthrough, dev: env var bridge)
- [x] create_app already reads LLM_PIPELINE_MODEL as fallback -- no changes to create_app needed for --model
- [x] _make_pipeline_factory in app.py is reusable for CLI-loaded modules (verified signature L24-46)
- [x] to_snake_case utility exists in naming.py and handles consecutive-caps correctly (double-regex)
- [x] Dev mode env var bridge pattern is established and sound (dotenv loaded at main() entry)
- [x] Merge order {**auto_discovered, **module_loaded, **(explicit or {})} correctly gives precedence: explicit > module > auto
- [x] PipelineConfig.__init__ requires model: str with no default (pipeline.py L209-211)
- [x] importlib.import_module is available in stdlib -- new to this codebase but zero-dep
- [x] Factory closure absorbs extra kwargs safely via **kwargs (confirmed in code L37)
- [x] Existing prod mode tests use exact assert_called_once_with(db_path=...) -- WILL break when adding default_model kwarg
- [x] inspect.isabstract(cls) correctly filters abstract intermediate PipelineConfig subclasses
- [x] Scan approach: `issubclass(cls, PipelineConfig) and cls is not PipelineConfig` catches user-defined subclasses only
- [x] create_app pipeline_modules param with default None is backward-compatible with all 3 CLI call sites

## Open Items
- **PipelineIntrospector single-regex naming bug**: carried forward from task 1 validation, still unresolved. Not blocking task 2 since registry keys from scan approach use to_snake_case (double-regex) which matches PipelineConfig.pipeline_name behavior. Mismatch only matters if PipelineIntrospector._pipeline_name is used to look up registry entries.
- **Abstract intermediate subclass filtering**: `inspect.isabstract(cls)` depends on classes having at least one abstractmethod. PipelineConfig subclasses that are intended as base classes but don't declare abstractmethods will be incorrectly registered. Document convention: intermediate bases should use ABC or declare at least one abstractmethod.

## Recommendations for Planning
1. Implement --model first (fully resolved, no dependencies on --pipelines decisions)
2. Implement --pipelines second: create_app gains `pipeline_modules: Optional[List[str]] = None`, `_load_pipeline_modules` helper scans for subclasses, raises on failure
3. Fix 3 pre-existing test failures + update prod mode test assertions -- switch to individual kwarg checks
4. Three-tier merge order in create_app: auto-discovered (lowest) < module-loaded (middle) < explicit registries (highest)
5. Dev mode: `_create_dev_app` reads `LLM_PIPELINE_PIPELINES` env var, splits on comma, passes to `create_app(pipeline_modules=[...])`
6. Prod mode: `_run_ui` passes `args.pipelines` (list or None from argparse append) directly to `create_app(pipeline_modules=args.pipelines)`
7. Error handling: _load_pipeline_modules raises ValueError with descriptive message. In create_app, this propagates up. CLI catches ValueError from create_app and calls sys.exit(1).
8. Test new paths: module scan happy path, module import failure (exit 1), no subclasses found in module (exit 1), abstract subclass filtered out, --model passthrough, dev mode env var bridge, pre-existing test fixes
