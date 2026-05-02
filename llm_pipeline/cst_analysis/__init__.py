"""Static analysis of user-authored Python source via libcst.

The READ direction of code <-> spec translation. Where
:mod:`llm_pipeline.codegen` writes code from spec edits, this
package walks existing code to produce the metadata that the
spec layer ships to the UI:

- :func:`analyze_code_body` returns a fully-populated
  :class:`CodeBodySpec` for a named function (Step.prepare,
  Extraction.extract, tool callable, eval scorer, etc.) — its
  source text plus all cross-artifact symbol references inside
  it.
- :func:`analyze_class_fields` returns a :class:`ClassFieldAnalysis`
  carrying both JSON-Pointer-keyed refs (``JsonSchemaWithRefs.refs``)
  and verbatim per-field annotation text
  (``JsonSchemaWithRefs.field_source``).

Both functions take a :data:`ResolverHook` callable so the analyser
stays decoupled from the per-kind registries (Phase C wires the
real one). Tests pass fakes.

No path guard: analysis can read anywhere (the analyser inspects;
it never writes). For parsing, the lower-level
:func:`llm_pipeline.codegen.read_module` is the shared parser
entry point — reused here.
"""
from llm_pipeline.cst_analysis.api import (
    AnalysisError,
    ClassFieldAnalysis,
    ResolverHook,
    analyze_class_fields,
    analyze_code_body,
    analyze_imports,
)


__all__ = [
    "AnalysisError",
    "ClassFieldAnalysis",
    "ResolverHook",
    "analyze_class_fields",
    "analyze_code_body",
    "analyze_imports",
]
