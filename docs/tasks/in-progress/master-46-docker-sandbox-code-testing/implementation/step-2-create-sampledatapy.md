# IMPLEMENTATION - STEP 2: CREATE SAMPLE_DATA.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/sample_data.py` with `SampleDataGenerator` class that auto-generates test data dicts from `FieldDefinition` specs. Handles all 8 type mappings, Optional/union-None stripping, eval-safe default parsing via `ast.literal_eval`, and unknown type fallback.

## Files
**Created:** `llm_pipeline/creator/sample_data.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/sample_data.py`
New file. Key components:

- `_TYPE_MAP` ClassVar: maps `str`, `int`, `float`, `bool`, `list[str]`, `dict[str, str]`, `list[int]`, `dict[str, Any]` to sample values. `str` uses `test_{name}` template.
- `_strip_optional()`: handles `Optional[X]`, `X | None`, `None | X` via regex.
- `_parse_default()`: uses `ast.literal_eval` for safe parsing of string/numeric/None/bool/list/dict literals. Falls back to raw string.
- `generate(fields)`: priority chain -- default > optional-not-required(None) > type-map > string fallback.
- `generate_json(fields)`: `json.dumps` with `default=str`.

## Decisions
### Default Parsing Strategy
**Choice:** `ast.literal_eval` with raw string fallback
**Rationale:** Safe (no eval/exec), handles Python literal syntax naturally (strings, numbers, None, True/False, lists, dicts). Unparseable defaults returned as-is rather than raising.

### Optional Stripping via Regex
**Choice:** Two compiled regex patterns for `Optional[X]` and `X | None` / `None | X`
**Rationale:** Simple, no dependency on `typing` introspection. Type annotations are strings in FieldDefinition, not actual types.

### Unknown Type Fallback
**Choice:** Return `f"test_{field.name}"` for unrecognized type annotations
**Rationale:** Spec requires no exceptions on unknown types. String fallback is safe for JSON serialization and provides identifiable test data.

## Verification
[x] All 8 _TYPE_MAP types generate correct values
[x] Optional[str] required field generates test_name (stripped to str)
[x] str | None and None | str both strip correctly
[x] Optional not-required field returns None
[x] Default '""' parses to empty string
[x] Default '42' parses to int 42
[x] Default 'None' parses to None
[x] Empty fields list returns empty dict
[x] Unknown type returns string fallback without exception
[x] generate_json returns valid parseable JSON
[x] Imports resolve correctly (from .models import FieldDefinition)
