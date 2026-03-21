# IMPLEMENTATION - STEP 2: CLI ARGS & DISPATCH
**Status:** completed

## Summary
Added `--model` and `--pipelines` CLI arguments to `llm_pipeline/ui/cli.py` and wired them through to `create_app` in both prod and dev paths. Added `ValueError` catch for failed pipeline module imports. Dev mode bridges args via `LLM_PIPELINE_MODEL` and `LLM_PIPELINE_PIPELINES` env vars.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/cli.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/cli.py`

**Parser args (L31-40):** Added `--model` (type=str, default=None) and `--pipelines` (action="append", default=None, metavar="MODULE") arguments to ui_parser.

```
# Before
ui_parser.add_argument("--db", ...)
args = parser.parse_args()

# After
ui_parser.add_argument("--db", ...)
ui_parser.add_argument("--model", type=str, default=None, help="Default LLM model string")
ui_parser.add_argument("--pipelines", action="append", default=None, metavar="MODULE", help="...")
args = parser.parse_args()
```

**Prod path _run_ui (L59-63):** Extended `create_app` call with `default_model=args.model` and `pipeline_modules=args.pipelines`.

```
# Before
app = create_app(db_path=args.db)

# After
app = create_app(db_path=args.db, default_model=args.model, pipeline_modules=args.pipelines)
```

**ValueError catch (L74-76):** Added `except ValueError` alongside existing `ImportError` guard. Prints error to stderr and exits 1.

```
# Before
except ImportError as e:
    ...
    sys.exit(1)

# After
except ImportError as e:
    ...
    sys.exit(1)
except ValueError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
```

**Dev mode env bridge _run_dev_mode (L101-104):** Added env var writes for `LLM_PIPELINE_MODEL` and `LLM_PIPELINE_PIPELINES` (comma-joined) after existing `LLM_PIPELINE_DB` pattern.

```
# Before
if args.db:
    os.environ["LLM_PIPELINE_DB"] = args.db

# After
if args.db:
    os.environ["LLM_PIPELINE_DB"] = args.db
if args.model:
    os.environ["LLM_PIPELINE_MODEL"] = args.model
if args.pipelines:
    os.environ["LLM_PIPELINE_PIPELINES"] = ",".join(args.pipelines)
```

**Dev factory _create_dev_app (L165-173):** Reads `LLM_PIPELINE_MODEL` and `LLM_PIPELINE_PIPELINES` env vars, splits pipelines on comma, passes both to `create_app`.

```
# Before
return create_app(db_path=db_path, database_url=database_url)

# After
model = os.environ.get("LLM_PIPELINE_MODEL")
pipeline_modules_raw = os.environ.get("LLM_PIPELINE_PIPELINES")
pipeline_modules = pipeline_modules_raw.split(",") if pipeline_modules_raw else None
return create_app(db_path=db_path, database_url=database_url, default_model=model, pipeline_modules=pipeline_modules)
```

## Decisions
### ValueError separate from ImportError
**Choice:** Separate `except ValueError` block rather than combining with ImportError
**Rationale:** ImportError guard checks `e.name` against UI deps set and conditionally re-raises. ValueError from pipeline module loading should always be fatal. Separate blocks keep logic clean.

### Truthy check for env var writes
**Choice:** `if args.model:` and `if args.pipelines:` (truthy) rather than `is not None`
**Rationale:** Matches existing `if args.db:` pattern on L99. Empty string model or empty list pipelines should not set env vars.

## Verification
- [x] Python syntax valid (ast.parse passes)
- [x] --model arg added with type=str, default=None
- [x] --pipelines arg added with action="append", default=None
- [x] Prod path passes default_model and pipeline_modules to create_app
- [x] ValueError catch prints to stderr and exits 1
- [x] Dev mode sets LLM_PIPELINE_MODEL env var
- [x] Dev mode sets LLM_PIPELINE_PIPELINES env var (comma-joined)
- [x] _create_dev_app reads both env vars and passes to create_app
- [x] Follows existing --db / LLM_PIPELINE_DB pattern exactly
- [x] Scope limited to cli.py only (no app.py or test changes)
