# IMPLEMENTATION - STEP 2: ADD IMPORT GUARD
**Status:** completed

## Summary
Wrapped `_run_ui()` body in try/except ImportError to print friendly error when [ui] deps missing.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/cli.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/cli.py`
Added try/except ImportError around entire `_run_ui()` body. On catch, prints install instruction to stderr and exits with code 1.
```
# Before
def _run_ui(args: argparse.Namespace) -> None:
    """Create the FastAPI app and dispatch to prod or dev mode."""
    if args.dev:
        _run_dev_mode(args)
    else:
        from llm_pipeline.ui.app import create_app
        app = create_app(db_path=args.db)
        _run_prod_mode(app, args.port)

# After
def _run_ui(args: argparse.Namespace) -> None:
    """Create the FastAPI app and dispatch to prod or dev mode."""
    try:
        if args.dev:
            _run_dev_mode(args)
        else:
            from llm_pipeline.ui.app import create_app
            app = create_app(db_path=args.db)
            _run_prod_mode(app, args.port)
    except ImportError:
        print(
            "ERROR: UI dependencies not installed. Run: pip install llm-pipeline[ui]",
            file=sys.stderr,
        )
        sys.exit(1)
```

## Decisions
None -- plan was unambiguous.

## Verification
[x] Import guard test passes (test_ui.py::test_missing_ui_deps or similar)
[x] `llm-pipeline --help` not affected (main() has no new imports)
[x] Pre-existing test failure (events router prefix) is unrelated to this change

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Broad ImportError catch may mask application bugs - made catch targeted via e.name check
[x] No test for CLI import guard - added 4 tests in tests/ui/test_cli.py

### Changes Made
#### File: `llm_pipeline/ui/cli.py`
Made except clause targeted: catch `ImportError as e`, check `e.name` root against known UI dep set, re-raise if unknown module.
```
# Before
    except ImportError:
        print(
            "ERROR: UI dependencies not installed. Run: pip install llm-pipeline[ui]",
            file=sys.stderr,
        )
        sys.exit(1)

# After
    except ImportError as e:
        _ui_deps = {"fastapi", "uvicorn", "starlette", "multipart", "python_multipart"}
        if e.name and e.name.split(".")[0] not in _ui_deps:
            raise
        print(
            "ERROR: UI dependencies not installed. Run: pip install llm-pipeline[ui]",
            file=sys.stderr,
        )
        sys.exit(1)
```

#### File: `tests/ui/test_cli.py`
Added `TestImportGuardCli` class with 4 tests:
- `test_missing_fastapi_exits_1` - ImportError(name="fastapi") triggers sys.exit(1)
- `test_missing_fastapi_prints_install_hint` - stderr contains install instruction
- `test_missing_uvicorn_exits_1` - ImportError(name="uvicorn") triggers sys.exit(1)
- `test_unknown_import_error_reraised` - ImportError(name="bogus") is re-raised

### Verification
[x] All 46 tests in tests/ui/test_cli.py pass
[x] Known UI dep ImportError caught and exits with friendly message
[x] Unknown module ImportError re-raised (not swallowed)
