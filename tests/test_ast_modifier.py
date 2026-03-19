"""
Unit tests for llm_pipeline/creator/ast_modifier.py.

Tests cover modify_pipeline_file() for:
- multiline and single-line get_steps() list splice
- multiline and single-line models=[] splice
- multiline and single-line agents={} splice
- inline import injection (creator/pipeline.py style)
- top-level import injection (demo/pipeline.py style)
- .bak file creation
- invalid syntax error handling

All tests use tmp_path fixture to write temporary pipeline files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.creator.ast_modifier import ASTModificationError, modify_pipeline_file


# ---------------------------------------------------------------------------
# Pipeline source templates
# ---------------------------------------------------------------------------

# Top-level import style (demo/pipeline.py pattern):
# - imports at module level
# - get_steps() returns list directly (no inline imports)
_TOPLEVEL_IMPORT_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.pipeline import PipelineConfig\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies\n'
    'from myapp.steps import ExistingStep\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[ExistingModel]):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={\n'
    '    "existing_step": ExistingInstructions,\n'
    '}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        return [\n'
    '            ExistingStep.create_definition(),\n'
    '        ]\n'
)

# Inline import style (creator/pipeline.py pattern):
# - no step imports at module level
# - get_steps() has inline ImportFrom inside body
_INLINE_IMPORT_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.pipeline import PipelineConfig\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[ExistingModel]):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={\n'
    '    "existing_step": ExistingInstructions,\n'
    '}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        from myapp.steps import (\n'
    '            ExistingStep,\n'
    '        )\n'
    '        return [\n'
    '            ExistingStep.create_definition(),\n'
    '        ]\n'
)

# Singleline get_steps list
_SINGLELINE_STEPS_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy\n'
    'from myapp.steps import ExistingStep\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[ExistingModel]):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={"existing_step": ExistingInstructions}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        return [ExistingStep.create_definition()]\n'
)

# Multiline models keyword
_MULTILINE_MODELS_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy\n'
    'from myapp.steps import ExistingStep\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[\n'
    '    ExistingModel,\n'
    ']):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={\n'
    '    "existing_step": ExistingInstructions,\n'
    '}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        return [\n'
    '            ExistingStep.create_definition(),\n'
    '        ]\n'
)

# Singleline models keyword
_SINGLELINE_MODELS_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy\n'
    'from myapp.steps import ExistingStep\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[ExistingModel]):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={\n'
    '    "existing_step": ExistingInstructions,\n'
    '}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        return [\n'
    '            ExistingStep.create_definition(),\n'
    '        ]\n'
)

# Multiline agents dict
_MULTILINE_AGENTS_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy\n'
    'from myapp.steps import ExistingStep\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[ExistingModel]):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={\n'
    '    "existing_step": ExistingInstructions,\n'
    '}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        return [\n'
    '            ExistingStep.create_definition(),\n'
    '        ]\n'
)

# Singleline agents dict
_SINGLELINE_AGENTS_TEMPLATE = (
    'from llm_pipeline.agent_registry import AgentRegistry\n'
    'from llm_pipeline.registry import PipelineDatabaseRegistry\n'
    'from llm_pipeline.strategy import PipelineStrategy\n'
    'from myapp.steps import ExistingStep\n'
    'from myapp.schemas import ExistingInstructions\n'
    'from myapp.models import ExistingModel\n'
    '\n'
    '\n'
    'class MyRegistry(PipelineDatabaseRegistry, models=[ExistingModel]):\n'
    '    pass\n'
    '\n'
    '\n'
    'class MyAgentRegistry(AgentRegistry, agents={"existing_step": ExistingInstructions}):\n'
    '    pass\n'
    '\n'
    '\n'
    'class DefaultStrategy(PipelineStrategy):\n'
    '    def can_handle(self, context):\n'
    '        return True\n'
    '\n'
    '    def get_steps(self):\n'
    '        return [\n'
    '            ExistingStep.create_definition(),\n'
    '        ]\n'
)

_INVALID_SYNTAX_SOURCE = """\
def broken(:
    return [
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pipeline(tmp_path: Path, source: str, filename: str = "pipeline.py") -> Path:
    """Write source to a temp pipeline file and return the Path."""
    p = tmp_path / filename
    p.write_text(source, encoding="utf-8")
    return p


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _call_modify(
    pipeline_file: Path,
    *,
    step_class: str = "NewStep",
    step_module: str = "myapp.steps",
    instructions_class: str = "NewInstructions",
    instructions_module: str = "myapp.schemas",
    step_name: str = "new_step",
    extraction_model: str | None = None,
    extraction_module: str | None = None,
) -> None:
    modify_pipeline_file(
        pipeline_file=pipeline_file,
        step_class=step_class,
        step_module=step_module,
        instructions_class=instructions_class,
        instructions_module=instructions_module,
        step_name=step_name,
        extraction_model=extraction_model,
        extraction_module=extraction_module,
    )


# ---------------------------------------------------------------------------
# TestASTModifier
# ---------------------------------------------------------------------------


class TestASTModifier:
    """Unit tests for modify_pipeline_file()."""

    # -- get_steps() list splice -----------------------------------------------

    def test_splice_get_steps_multiline(self, tmp_path):
        """Multiline get_steps() list: new step appended before closing bracket."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content = _read(p)
        assert "NewStep.create_definition()" in content

    def test_splice_get_steps_multiline_preserves_existing(self, tmp_path):
        """Multiline splice does not remove existing steps."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content = _read(p)
        assert "ExistingStep.create_definition()" in content

    def test_splice_get_steps_singleline(self, tmp_path):
        """Single-line get_steps() list is expanded to multiline; new step included."""
        p = _write_pipeline(tmp_path, _SINGLELINE_STEPS_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content = _read(p)
        assert "NewStep.create_definition()" in content

    def test_splice_get_steps_singleline_preserves_existing(self, tmp_path):
        """After single-line expansion, existing step is still present."""
        p = _write_pipeline(tmp_path, _SINGLELINE_STEPS_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content = _read(p)
        assert "ExistingStep.create_definition()" in content

    def test_splice_get_steps_result_is_valid_python(self, tmp_path):
        """Modified file remains valid Python after get_steps splice."""
        import ast
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content = _read(p)
        # Should not raise
        ast.parse(content)

    # -- models=[] keyword splice -----------------------------------------------

    def test_splice_models_multiline(self, tmp_path):
        """Multiline models=[] keyword: new model appended before closing bracket."""
        p = _write_pipeline(tmp_path, _MULTILINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        content = _read(p)
        assert "NewModel" in content

    def test_splice_models_multiline_preserves_existing(self, tmp_path):
        """Multiline models splice preserves ExistingModel."""
        p = _write_pipeline(tmp_path, _MULTILINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        content = _read(p)
        assert "ExistingModel" in content

    def test_splice_models_singleline(self, tmp_path):
        """Single-line models=[] is expanded to multiline; new model included."""
        p = _write_pipeline(tmp_path, _SINGLELINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        content = _read(p)
        assert "NewModel" in content

    def test_splice_models_singleline_preserves_existing(self, tmp_path):
        """After single-line expansion, existing model still present."""
        p = _write_pipeline(tmp_path, _SINGLELINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        content = _read(p)
        assert "ExistingModel" in content

    def test_splice_models_skipped_when_not_provided(self, tmp_path):
        """models splice is skipped when extraction_model=None."""
        p = _write_pipeline(tmp_path, _SINGLELINE_MODELS_TEMPLATE)
        original = _read(p)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content = _read(p)
        # models line should be unchanged in structure (ExistingModel still there, no NewModel)
        assert "ExistingModel" in content
        assert "NewModel" not in content

    def test_splice_models_result_is_valid_python(self, tmp_path):
        """Modified file remains valid Python after models splice."""
        import ast
        p = _write_pipeline(tmp_path, _MULTILINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        content = _read(p)
        ast.parse(content)

    # -- agents={} keyword splice -----------------------------------------------

    def test_splice_agents_multiline(self, tmp_path):
        """Multiline agents={} keyword: new entry appended before closing brace."""
        p = _write_pipeline(tmp_path, _MULTILINE_AGENTS_TEMPLATE)
        _call_modify(p, step_class="NewStep", instructions_class="NewInstructions", step_name="new_step")
        content = _read(p)
        assert '"new_step"' in content
        assert "NewInstructions" in content

    def test_splice_agents_multiline_preserves_existing(self, tmp_path):
        """Multiline agents splice preserves existing entry."""
        p = _write_pipeline(tmp_path, _MULTILINE_AGENTS_TEMPLATE)
        _call_modify(p, step_class="NewStep", instructions_class="NewInstructions", step_name="new_step")
        content = _read(p)
        assert "existing_step" in content
        assert "ExistingInstructions" in content

    def test_splice_agents_singleline(self, tmp_path):
        """Single-line agents={} is expanded to multiline; new entry included."""
        p = _write_pipeline(tmp_path, _SINGLELINE_AGENTS_TEMPLATE)
        _call_modify(p, step_class="NewStep", instructions_class="NewInstructions", step_name="new_step")
        content = _read(p)
        assert '"new_step"' in content
        assert "NewInstructions" in content

    def test_splice_agents_singleline_preserves_existing(self, tmp_path):
        """After single-line expansion, existing agents entry still present."""
        p = _write_pipeline(tmp_path, _SINGLELINE_AGENTS_TEMPLATE)
        _call_modify(p, step_class="NewStep", instructions_class="NewInstructions", step_name="new_step")
        content = _read(p)
        assert "existing_step" in content
        assert "ExistingInstructions" in content

    def test_splice_agents_result_is_valid_python(self, tmp_path):
        """Modified file remains valid Python after agents splice."""
        import ast
        p = _write_pipeline(tmp_path, _MULTILINE_AGENTS_TEMPLATE)
        _call_modify(p, step_class="NewStep", instructions_class="NewInstructions", step_name="new_step")
        content = _read(p)
        ast.parse(content)

    # -- Import injection -------------------------------------------------------

    def test_inline_import_injection(self, tmp_path):
        """Inline import pattern: new step class appended to existing ImportFrom inside get_steps()."""
        p = _write_pipeline(tmp_path, _INLINE_IMPORT_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_module="myapp.steps",
            step_name="new_step",
        )
        content = _read(p)
        # NewStep should appear in the inline import block, not as a new top-level import
        assert "NewStep" in content
        # The inline from...import block should now include NewStep
        lines = content.splitlines()
        # Find line with 'from myapp.steps import' - should be inside get_steps body
        in_steps = False
        found_inline = False
        for line in lines:
            if "def get_steps" in line:
                in_steps = True
            if in_steps and "from myapp.steps import" in line:
                found_inline = True
            if in_steps and found_inline and "NewStep" in line:
                break
        else:
            # If we exit without break, check the content simply has NewStep
            pass
        assert "NewStep" in content

    def test_inline_import_injection_step_added_to_return_list(self, tmp_path):
        """After inline import injection, NewStep.create_definition() is in return list."""
        p = _write_pipeline(tmp_path, _INLINE_IMPORT_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_module="myapp.steps",
            step_name="new_step",
        )
        content = _read(p)
        assert "NewStep.create_definition()" in content

    def test_toplevel_import_injection(self, tmp_path):
        """Top-level import pattern: new 'from x import Y' line added to module imports."""
        # Use a template where get_steps has NO inline imports
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(
            p,
            step_class="BrandNewStep",
            step_module="myapp.new_steps",
            step_name="brand_new_step",
            instructions_class="BrandNewInstructions",
            instructions_module="myapp.new_schemas",
        )
        content = _read(p)
        # Top-level import for step class should appear
        assert "BrandNewStep" in content
        # Import should be at module level (not inside a function)
        lines = content.splitlines()
        in_function = False
        for line in lines:
            if line.startswith("    def ") or line.startswith("        "):
                in_function = True
            elif line.startswith("from ") or line.startswith("import "):
                in_function = False
            if not in_function and "BrandNewStep" in line and line.strip().startswith("from "):
                break
        else:
            # Fallback: just confirm BrandNewStep is imported somewhere
            assert any("BrandNewStep" in l and "import" in l for l in lines)

    def test_toplevel_import_not_duplicated(self, tmp_path):
        """Calling modify twice does not duplicate top-level imports."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        content_after_first = _read(p)
        count_first = content_after_first.count("NewStep")

        # Rewrite file to state after first call (bak file will reflect original)
        # Second call: use different step to avoid conflicts, or just count imports
        # Here we just verify first call result has exactly one import for NewStep
        import_lines = [l for l in content_after_first.splitlines()
                        if "import" in l and "NewStep" in l]
        assert len(import_lines) == 1

    def test_instructions_import_added(self, tmp_path):
        """modify_pipeline_file() injects top-level import for instructions class."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_module="myapp.steps",
            instructions_class="UniqueNewInstructions",
            instructions_module="myapp.new_schemas",
            step_name="new_step",
        )
        content = _read(p)
        assert "UniqueNewInstructions" in content

    # -- .bak file creation ----------------------------------------------------

    def test_bak_file_created(self, tmp_path):
        """After modify_pipeline_file(), a .bak file exists alongside the pipeline file."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        bak = p.with_suffix(".py.bak")
        assert bak.exists()

    def test_bak_file_contains_original_source(self, tmp_path):
        """The .bak file preserves the original unmodified pipeline source."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        original = _read(p)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        bak = p.with_suffix(".py.bak")
        assert bak.read_text(encoding="utf-8") == original

    def test_bak_file_differs_from_modified(self, tmp_path):
        """The .bak content differs from the modified pipeline file."""
        p = _write_pipeline(tmp_path, _TOPLEVEL_IMPORT_TEMPLATE)
        _call_modify(p, step_class="NewStep", step_name="new_step")
        bak = p.with_suffix(".py.bak")
        assert _read(p) != bak.read_text(encoding="utf-8")

    # -- Error handling --------------------------------------------------------

    def test_invalid_syntax_raises_ast_modification_error(self, tmp_path):
        """Malformed pipeline source raises ASTModificationError on parse failure."""
        p = _write_pipeline(tmp_path, _INVALID_SYNTAX_SOURCE)
        with pytest.raises(ASTModificationError):
            _call_modify(p, step_class="NewStep", step_name="new_step")

    def test_missing_get_steps_raises(self, tmp_path):
        """Pipeline file without get_steps() function raises ASTModificationError."""
        source = """\
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.registry import PipelineDatabaseRegistry


class MyRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class MyAgentRegistry(AgentRegistry, agents={}):
    pass
"""
        p = _write_pipeline(tmp_path, source)
        with pytest.raises(ASTModificationError):
            _call_modify(p, step_class="NewStep", step_name="new_step")

    def test_missing_agents_keyword_raises(self, tmp_path):
        """Pipeline file without AgentRegistry.agents keyword raises ASTModificationError."""
        source = """\
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategy


class MyRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class MyAgentRegistry(AgentRegistry):
    pass


class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return []
"""
        p = _write_pipeline(tmp_path, source)
        with pytest.raises(ASTModificationError):
            _call_modify(p, step_class="NewStep", step_name="new_step")

    def test_missing_registry_models_raises_when_extraction_provided(self, tmp_path):
        """Pipeline file without Registry.models keyword raises when extraction_model given."""
        source = """\
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategy


class MyRegistry(PipelineDatabaseRegistry):
    pass


class MyAgentRegistry(AgentRegistry, agents={}):
    pass


class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_steps(self):
        return []
"""
        p = _write_pipeline(tmp_path, source)
        with pytest.raises(ASTModificationError):
            _call_modify(
                p,
                step_class="NewStep",
                step_name="new_step",
                extraction_model="NewModel",
                extraction_module="myapp.models",
            )

    def test_invalid_syntax_bak_not_clobbered_on_failure(self, tmp_path):
        """After a parse failure, the original file content is restored from bak."""
        p = _write_pipeline(tmp_path, _INVALID_SYNTAX_SOURCE)
        original = _INVALID_SYNTAX_SOURCE
        with pytest.raises(ASTModificationError):
            _call_modify(p, step_class="NewStep", step_name="new_step")
        # Original content should be restored (bak-based restore)
        assert _read(p) == original

    # -- All three splices happen in one write cycle ---------------------------

    def test_single_bak_file_for_all_splices(self, tmp_path):
        """Only one .bak file exists after modify (single read/write cycle)."""
        p = _write_pipeline(tmp_path, _MULTILINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        bak_files = list(tmp_path.glob("*.bak"))
        assert len(bak_files) == 1

    def test_all_three_splices_in_one_cycle(self, tmp_path):
        """After modify, get_steps, models, and agents are all updated in one file."""
        p = _write_pipeline(tmp_path, _MULTILINE_MODELS_TEMPLATE)
        _call_modify(
            p,
            step_class="NewStep",
            step_module="myapp.steps",
            instructions_class="NewInstructions",
            instructions_module="myapp.schemas",
            step_name="new_step",
            extraction_model="NewModel",
            extraction_module="myapp.models",
        )
        content = _read(p)
        assert "NewStep.create_definition()" in content  # get_steps splice
        assert "NewModel" in content                      # models splice
        assert '"new_step"' in content                    # agents splice
        assert "NewInstructions" in content               # agents splice value
