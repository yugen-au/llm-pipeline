# IMPLEMENTATION - STEP 8: OTEL OPTIONAL DEPS
**Status:** completed

## Summary
Added `[otel]` optional dependency group to pyproject.toml with opentelemetry-sdk and OTLP HTTP exporter. Both packages also added to `[dev]` group.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added new `otel` optional dependency group and added both OTel packages to `dev` group.

```
# Before
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
dev = [
    ...
    "pydantic-ai>=1.0.5",
]

# After
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
otel = [
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp-proto-http>=1.20.0",
]
dev = [
    ...
    "pydantic-ai>=1.0.5",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp-proto-http>=1.20.0",
]
```

## Decisions
None -- plan was fully specified.

## Verification
[x] `otel` group contains opentelemetry-sdk>=1.20.0 and opentelemetry-exporter-otlp-proto-http>=1.20.0
[x] Both packages added to `dev` group
[x] Existing groups unchanged
[x] TOML syntax valid (verified by reading final file)
