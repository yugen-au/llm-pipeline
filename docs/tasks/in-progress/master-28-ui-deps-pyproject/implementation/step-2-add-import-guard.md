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
