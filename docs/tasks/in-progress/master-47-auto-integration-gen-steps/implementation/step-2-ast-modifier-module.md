# IMPLEMENTATION - STEP 2: AST MODIFIER MODULE
**Status:** completed

## Summary
Created `llm_pipeline/creator/ast_modifier.py` implementing the hybrid AST-locate + string-splice approach. Single read/parse/splice/write cycle modifies all three targets in a pipeline file: `get_steps()` return list, `Registry.models=[...]` class keyword, `AgentRegistry.agents={...}` class keyword. Handles inline imports (creator/pipeline.py style) and top-level imports (demo/pipeline.py style). Single-line lists/dicts expanded to multiline before insertion.

## Files
**Created:** `llm_pipeline/creator/ast_modifier.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/ast_modifier.py`
New file. 340 lines.

Public API:
- `modify_pipeline_file()` - orchestrates full read/backup/parse/splice/write cycle
- `ASTModificationError` - custom exception

Internal helpers:
- `_find_function_def` - locates FunctionDef at module or class level
- `_find_class_keyword_node` - locates keyword value node by class name substring + keyword name
- `_splice_into_list` - handles multiline and single-line list splicing
- `_splice_into_dict` - handles multiline and single-line dict splicing
- `_expand_list_and_insert` - single-line list expansion + insertion
- `_expand_dict_and_insert` - single-line dict expansion + insertion
- `_detect_and_add_import` - inline vs top-level import detection and injection
- `_detect_and_add_registry_import` - top-level only import injection with dedup
- `_splice_into_inline_import` - adds name to existing ImportFrom node
- `_add_toplevel_import` - appends new from-import after last top-level import
- `_find_return_list` - finds List node from last return in a function
- `_reparse` - re-parses after each splice to keep line numbers accurate

## Decisions

### Re-parse After Each Splice
**Choice:** Re-parse source_lines with `_reparse()` after every splice step rather than accumulating all edits in one pass.
**Rationale:** Each splice changes line numbers. Subsequent `ast.List`/`ast.Dict` node `.lineno`/`.end_lineno` from the original parse become stale after insertion. Re-parsing ensures accurate positions for each subsequent operation. Performance cost is negligible (small files, 4 re-parses max).

### shutil.copy2 for Backup Restore
**Choice:** `shutil.copy2(bak_path, pipeline_file)` on failure rather than `os.replace()`.
**Rationale:** `os.replace()` on Windows can fail with PermissionError if the target is open. `Path.write_text()` / `shutil.copy2()` avoids the rename-over-existing-file issue. Consistent with PLAN.md Windows file locking mitigation.

### _find_class_keyword_node Uses Substring Match
**Choice:** `class_name_pattern in node.name` (substring) rather than exact match.
**Rationale:** Pipeline files use prefixed names like `TextAnalyzerRegistry` and `StepCreatorAgentRegistry`. Searching for `"Registry"` and `"AgentRegistry"` via substring match finds both without requiring knowledge of the pipeline-specific prefix.

### Backup Created Before Any Splice
**Choice:** `.bak` written immediately after reading source, before any modification attempt.
**Rationale:** If any splice raises mid-way, the backup already exists and `_reparse` failure triggers restore. Aligns with PLAN.md: "bak created before any write; rollback restores from bak".

## Verification
- [x] Module imports cleanly: `python -c "import llm_pipeline.creator.ast_modifier; print('import ok')"` -> `import ok`
- [x] `ASTModificationError` defined and exported in `__all__`
- [x] `modify_pipeline_file` exported in `__all__`
- [x] All three splice targets handled: get_steps list, models list, agents dict
- [x] Inline import detection via `ast.walk(get_steps_func)` for `ImportFrom` nodes
- [x] Top-level import fallback via `_add_toplevel_import`
- [x] Single-line list expansion in `_expand_list_and_insert`
- [x] Single-line dict expansion in `_expand_dict_and_insert`
- [x] Backup restore on `ASTModificationError` and unexpected exceptions
- [x] `extraction_model` param is optional (skips models splice if None)
