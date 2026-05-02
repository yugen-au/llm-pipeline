"""Tests for the per-kind discovery walkers.

Two test styles:

- **Synthetic-module tests** — construct a ``types.ModuleType`` in
  memory, set ``__file__`` to a temp path with the corresponding
  source, then call the walker. Used for walkers whose registration
  shape doesn't depend heavily on cst_analysis output (constants,
  enums, the kind-detection logic).

- **End-to-end tmp_path tests** — write a real ``.py`` file to
  ``tmp_path``, load it via :func:`load_convention_module`, then
  call the walker. Used to verify the cst_analysis-aware path
  populates ``SymbolRef``s correctly.
"""
from __future__ import annotations

import textwrap
from enum import Enum
from pathlib import Path
from types import ModuleType

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, SQLModel

from llm_pipeline.discovery import init_empty_registries
from llm_pipeline.discovery.loading import load_convention_module
from llm_pipeline.discovery.resolver import make_resolver
from llm_pipeline.discovery.walkers import (
    ConstantsWalker,
    EnumsWalker,
    ExtractionsWalker,
    PipelinesWalker,
    ReviewsWalker,
    SchemasWalker,
    StepsWalker,
    TablesWalker,
    ToolsWalker,
)
from llm_pipeline.graph import (
    ExtractionNode,
    LLMResultMixin,
    LLMStepNode,
    ReviewNode,
    StepInputs,
)
from llm_pipeline.prompts import PromptVariables
from llm_pipeline.specs.kinds import (
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_PIPELINE,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TABLE,
    KIND_TOOL,
)


def _null_resolver(module_path: str, imported_symbol: str) -> tuple[str, str] | None:
    return None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestWalkConstants:
    def test_registers_constant_subclasses(self, tmp_path: Path):
        source = textwrap.dedent("""
            from llm_pipeline.constants import Constant

            class MAX_RETRIES(Constant):
                value = 3

            class DEFAULT_LABEL(Constant):
                value = "unknown"

            class FALLBACK_FLOATS(Constant):
                value = [0.1, 0.5]

            class _PRIVATE(Constant):
                value = "skip me"
        """)
        path = tmp_path / "consts.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_consts")

        regs = init_empty_registries()
        ConstantsWalker().walk([mod], regs, _null_resolver)

        assert "max_retries" in regs[KIND_CONSTANT]
        assert "default_label" in regs[KIND_CONSTANT]
        assert "fallback_floats" in regs[KIND_CONSTANT]
        # Underscore-prefixed names are skipped at the iteration
        # level (regardless of whether they're Constant subclasses).
        assert "private" not in regs[KIND_CONSTANT]

        max_retries = regs[KIND_CONSTANT]["max_retries"]
        assert max_retries.spec.value == 3
        assert max_retries.spec.value_type == "int"
        # ``obj`` is the Constant subclass; the value lives on its
        # ``value`` ClassVar.
        assert max_retries.obj.value == 3


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestWalkEnums:
    def test_registers_local_enum(self, tmp_path: Path):
        source = textwrap.dedent("""
            from enum import Enum

            class Sentiment(Enum):
                POSITIVE = "pos"
                NEGATIVE = "neg"
        """)
        path = tmp_path / "enums.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_enums")

        regs = init_empty_registries()
        EnumsWalker().walk([mod], regs, _null_resolver)

        assert "sentiment" in regs[KIND_ENUM]
        spec = regs[KIND_ENUM]["sentiment"].spec
        assert spec.value_type == "str"
        member_names = [m.name for m in spec.members]
        assert member_names == ["POSITIVE", "NEGATIVE"]

    def test_skips_imported_enum(self, tmp_path: Path):
        # Enum imported from elsewhere — the locally-defined check
        # filters it out so we don't double-register.
        defining_source = textwrap.dedent("""
            from enum import Enum

            class Sentiment(Enum):
                P = "p"
        """)
        importing_source = textwrap.dedent("""
            from _test_enum_defining_module import Sentiment
        """)
        defining = tmp_path / "defining.py"
        defining.write_text(defining_source)
        importing = tmp_path / "importing.py"
        importing.write_text(importing_source)

        # Load defining first under the synthetic name, then importing.
        load_convention_module(defining, "_test_enum_defining_module")
        importing_mod = load_convention_module(importing, "_test_enum_importing")

        regs = init_empty_registries()
        EnumsWalker().walk([importing_mod], regs, _null_resolver)
        # ``Sentiment`` is imported, not defined here, so it's skipped.
        assert regs[KIND_ENUM] == {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestWalkSchemas:
    def test_registers_basemodel(self, tmp_path: Path):
        source = textwrap.dedent("""
            from pydantic import BaseModel

            class Address(BaseModel):
                street: str
                zipcode: int = 1000
        """)
        path = tmp_path / "schemas.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_schemas_basic")

        regs = init_empty_registries()
        SchemasWalker().walk([mod], regs, _null_resolver)

        assert "address" in regs[KIND_SCHEMA]
        spec = regs[KIND_SCHEMA]["address"].spec
        assert "properties" in spec.definition.json_schema

    def test_registers_sqlmodel_with_table_under_schemas(self, tmp_path: Path):
        # Folder-source-of-truth: a SQLModel-with-table=True class
        # *living in schemas/* still gets KIND_SCHEMA, not KIND_TABLE.
        # Users who put DB tables in schemas/ get caught by the
        # folder layout being the classification source.
        source = textwrap.dedent("""
            from sqlmodel import SQLModel, Field

            class StrayTable(SQLModel, table=True):
                __tablename__ = "stray_test_walker"
                __table_args__ = {"extend_existing": True}
                id: int = Field(default=None, primary_key=True)
                name: str
        """)
        path = tmp_path / "schemas_w_table.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_schemas_w_table")

        regs = init_empty_registries()
        SchemasWalker().walk([mod], regs, _null_resolver)
        # walk_schemas registers it as a schema (folder is source of truth).
        assert "stray_table" in regs[KIND_SCHEMA]
        # walk_tables wouldn't have run on this folder.


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class TestWalkTables:
    def test_registers_sqlmodel_with_table(self, tmp_path: Path):
        source = textwrap.dedent("""
            from sqlmodel import SQLModel, Field

            class TopicRow(SQLModel, table=True):
                __tablename__ = "test_walker_topics"
                __table_args__ = {"extend_existing": True}
                id: int = Field(default=None, primary_key=True)
                name: str
                relevance: float
        """)
        path = tmp_path / "tables.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_tables_basic")

        regs = init_empty_registries()
        TablesWalker().walk([mod], regs, _null_resolver)

        assert "topic_row" in regs[KIND_TABLE]
        spec = regs[KIND_TABLE]["topic_row"].spec
        assert spec.table_name == "test_walker_topics"
        assert "properties" in spec.definition.json_schema

    def test_skips_pure_basemodel_in_tables_folder(self, tmp_path: Path):
        # Defensive: the ``__table__`` check rejects non-table
        # classes even if they slip into ``tables/`` by mistake.
        source = textwrap.dedent("""
            from pydantic import BaseModel

            class NotATable(BaseModel):
                x: int
        """)
        path = tmp_path / "tables_nontable.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_tables_nontable")

        regs = init_empty_registries()
        TablesWalker().walk([mod], regs, _null_resolver)
        assert regs[KIND_TABLE] == {}


# ---------------------------------------------------------------------------
# Two-pass cross-artifact resolution
# ---------------------------------------------------------------------------


class TestTwoPassResolution:
    def test_pass_1_no_refs_pass_2_full_refs(self, tmp_path: Path):
        # A constants module + a schemas module that references the
        # constant in a Field default. Pass 1: refs empty. Pass 2:
        # refs populated.
        consts_path = tmp_path / "consts_2pass.py"
        consts_path.write_text(textwrap.dedent("""
            from llm_pipeline.constants import Constant

            class MAX_RETRIES(Constant):
                value = 3
        """))
        consts_mod = load_convention_module(
            consts_path, "consts_pkg_2pass.constants",
        )

        schemas_path = tmp_path / "schemas_2pass.py"
        schemas_path.write_text(textwrap.dedent("""
            from consts_pkg_2pass.constants import MAX_RETRIES
            from pydantic import BaseModel

            class Foo(BaseModel):
                retries: int = MAX_RETRIES.value
        """))
        schemas_mod = load_convention_module(
            schemas_path, "schemas_pkg_2pass.schemas",
        )

        regs = init_empty_registries()

        # Pass 1
        ConstantsWalker().walk([consts_mod], regs, _null_resolver)
        SchemasWalker().walk([schemas_mod], regs, _null_resolver)
        # No refs yet — resolver returned None for every lookup.
        foo_spec = regs[KIND_SCHEMA]["foo"].spec
        assert foo_spec.definition.refs == {}

        # Pass 2 — rebuild with full resolver.
        full_resolver = make_resolver(regs)
        SchemasWalker().walk([schemas_mod], regs, full_resolver)
        foo_spec = regs[KIND_SCHEMA]["foo"].spec
        assert "/properties/retries/default" in foo_spec.definition.refs
        ref = foo_spec.definition.refs["/properties/retries/default"][0]
        assert ref.kind == KIND_CONSTANT
        assert ref.name == "max_retries"


# ---------------------------------------------------------------------------
# Steps / Extractions / Reviews — end-to-end with bodies + cls registration
# ---------------------------------------------------------------------------


def _step_module(tmp_path: Path) -> ModuleType:
    source = textwrap.dedent('''
        from typing import ClassVar
        from pydantic import Field

        from llm_pipeline.graph import LLMResultMixin, LLMStepNode, StepInputs
        from llm_pipeline.prompts import PromptVariables


        class FooInputs(StepInputs):
            text: str


        class FooInstructions(LLMResultMixin):
            label: str = ""


        class FooPrompt(PromptVariables):
            text: str = Field(description="text")


        class FooStep(LLMStepNode):
            INPUTS = FooInputs
            INSTRUCTIONS = FooInstructions
            DEFAULT_TOOLS: list = []

            def prepare(self, inputs: FooInputs) -> list[FooPrompt]:
                return [FooPrompt(text=inputs.text)]

            async def run(self, ctx):
                return None
    ''')
    path = tmp_path / "step.py"
    path.write_text(source)
    return load_convention_module(path, "_test_walkers_step_module")


class TestWalkSteps:
    def test_registers_step_with_bodies(self, tmp_path: Path):
        mod = _step_module(tmp_path)

        regs = init_empty_registries()
        StepsWalker().walk([mod], regs, _null_resolver)

        assert "foo" in regs[KIND_STEP]
        spec = regs[KIND_STEP]["foo"].spec
        assert spec.inputs is not None
        assert spec.instructions is not None
        # prepare body should be present (locatable in source).
        assert spec.prepare is not None
        assert "FooPrompt" in spec.prepare.source


# ---------------------------------------------------------------------------
# No-op walkers
# ---------------------------------------------------------------------------


class TestWalkTools:
    def test_registers_agent_tool_subclasses(self, tmp_path: Path):
        source = textwrap.dedent("""
            from pydantic import BaseModel

            from llm_pipeline.agent_tool import AgentTool
            from llm_pipeline.inputs import StepInputs

            class FetchDocsTool(AgentTool):
                \"\"\"Look up framework docs.\"\"\"

                class Inputs(StepInputs):
                    library_id: str

                class Args(BaseModel):
                    query: str
                    limit: int = 5

                @classmethod
                def run(cls, inputs, args, ctx):
                    return ""
        """)
        path = tmp_path / "tools.py"
        path.write_text(source)
        mod = load_convention_module(path, "_test_tools")

        regs = init_empty_registries()
        ToolsWalker().walk([mod], regs, _null_resolver)

        assert "fetch_docs" in regs[KIND_TOOL]
        spec = regs[KIND_TOOL]["fetch_docs"].spec
        assert spec.kind == KIND_TOOL
        assert spec.name == "fetch_docs"
        assert spec.inputs is not None
        assert spec.args is not None
        # Args schema has the LLM-call parameters.
        assert "query" in spec.args.json_schema["properties"]


class TestNoOpWalkers:
    def test_walk_pipelines_does_nothing(self):
        # Pipeline registration stays in legacy
        # ``app.state.pipeline_registry`` for now — the existing
        # graph PipelineSpec doesn't subclass ArtifactSpec yet.
        regs = init_empty_registries()
        PipelinesWalker().walk([], regs, _null_resolver)
        assert regs[KIND_PIPELINE] == {}
