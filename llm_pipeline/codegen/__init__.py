"""Code generation + modification subsystem (libcst-based).

Owns every read/write of Python source files under the configured
``llm_pipelines/`` root. Mutations of framework code (anything outside
that root) are blocked at the IO layer — these primitives only exist
to manipulate user-authored / generated state directories.

Two complementary surfaces:

- **Generation**: build a fresh ``cst.Module`` and write it to disk.
  Used by ``llm-pipeline build`` for the ``llm_pipelines/variables/``
  PromptVariables files derived from YAML.

- **Modification**: parse an existing file, apply a CSTTransformer,
  write the result. Preserves comments and formatting. Used by the
  eval-runner accept path and (eventually) by LLM-driven creator
  pipelines.

Public API lives in :mod:`llm_pipeline.codegen.api`. The lower-level
:mod:`builders`, :mod:`transformers`, and :mod:`io` modules are
exposed for power users / tests but most callers should stick to
the API surface.
"""
from llm_pipeline.codegen.api import (
    CodegenError,
    apply_instructions_delta,
    edit_code_body,
    generate_prompt_variables,
    write_code_body,
)
from llm_pipeline.codegen.io import (
    CodegenPathError,
    LLM_PIPELINES_ROOT_ENV,
    assert_under_root,
    read_module,
    resolve_root,
    write_module,
    write_module_if_changed,
)


__all__ = [
    # Public API
    "apply_instructions_delta",
    "edit_code_body",
    "generate_prompt_variables",
    "write_code_body",
    # Errors
    "CodegenError",
    "CodegenPathError",
    # IO primitives (advanced / tests)
    "LLM_PIPELINES_ROOT_ENV",
    "assert_under_root",
    "read_module",
    "resolve_root",
    "write_module",
    "write_module_if_changed",
]
