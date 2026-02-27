# IMPLEMENTATION - STEP 4: INTROSPECTION METADATA
**Status:** completed

## Summary
Added `pipeline_input_schema` key to `PipelineIntrospector.get_metadata()` return dict. Uses existing `_get_schema()` static method to extract JSON schema from `INPUT_DATA` ClassVar when declared on pipeline class.

## Files
**Created:** none
**Modified:** `llm_pipeline/introspection.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/introspection.py`
Added `pipeline_input_schema` computation after `execution_order` derivation, included in metadata dict. Updated docstring to document new key.

```
# Before (L255-262)
        metadata: Dict[str, Any] = {
            "pipeline_name": pipeline_name,
            "registry_models": registry_models,
            "strategies": strategies,
            "execution_order": execution_order,
        }

# After (L255-266)
        # Pipeline input schema (from INPUT_DATA ClassVar if declared)
        pipeline_input_schema = self._get_schema(
            getattr(self._pipeline_cls, "INPUT_DATA", None)
        )

        metadata: Dict[str, Any] = {
            "pipeline_name": pipeline_name,
            "registry_models": registry_models,
            "strategies": strategies,
            "execution_order": execution_order,
            "pipeline_input_schema": pipeline_input_schema,
        }
```

## Decisions
None

## Verification
[x] `_get_schema()` already handles None input (returns None) - no INPUT_DATA = pipeline_input_schema is None
[x] `_get_schema()` handles BaseModel subclasses via `model_json_schema()` - INPUT_DATA declared = full JSON schema
[x] `getattr` with default None safely handles pipeline classes without INPUT_DATA ClassVar
[x] New key included in both metadata dict and cache assignment (same dict object)
[x] Docstring updated to list `pipeline_input_schema` in returned keys
