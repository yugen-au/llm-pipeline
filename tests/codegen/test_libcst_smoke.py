"""Smoke tests verifying the libcst patterns the codegen package will use.

These tests document and lock in the libcst APIs we lean on:

- Lossless parse/render round-trip (the property that makes libcst worth
  using over stdlib ``ast``)
- Constructing a fresh ``Module`` from scratch — the PromptVariables
  generator pattern (imports + ClassDef with nested classes + ClassVar
  dict)
- ``parse_statement`` / ``parse_expression`` as ergonomic shortcuts when
  embedding snippets into a manually-built tree
- ``CSTTransformer`` for modifying existing files (insert into a list,
  add a field to a class) while preserving comments and formatting

The tests use libcst directly (no codegen helpers yet) — they verify
the raw library behaves the way our codegen module will assume.
"""
from __future__ import annotations

import libcst as cst


# ---------------------------------------------------------------------------
# Round-trip: parse → render → identical source
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_simple_class_round_trips_byte_for_byte(self):
        source = (
            "class Foo:\n"
            "    x: str = 'hi'\n"
            "    y: int = 0\n"
        )
        assert cst.parse_module(source).code == source

    def test_class_with_comments_round_trips(self):
        source = (
            "# Module docstring comment\n"
            "class Foo:\n"
            "    # Field-level comment\n"
            "    x: str = 'hi'\n"
            "\n"
            "    # Method-level comment\n"
            "    def bar(self):\n"
            "        return self.x\n"
        )
        assert cst.parse_module(source).code == source

    def test_decorators_and_complex_typing_round_trips(self):
        source = (
            "from typing import ClassVar\n"
            "from pydantic import BaseModel, Field\n"
            "\n"
            "\n"
            "class Foo(BaseModel):\n"
            "    text: str = Field(description='hello')\n"
            "    nums: list[int] = Field(default_factory=list)\n"
            "    auto_vars: ClassVar[dict[str, str]] = {'a': 'b'}\n"
        )
        assert cst.parse_module(source).code == source


# ---------------------------------------------------------------------------
# Building a fresh Module from scratch
# ---------------------------------------------------------------------------


class TestModuleConstruction:
    def test_build_empty_module_renders_correctly(self):
        module = cst.Module(body=[])
        # Empty module renders as just the trailing newline
        assert module.code == "\n"

    def test_build_module_with_parsed_statements(self):
        """The pragmatic pattern: parse_statement for each line, assemble."""
        body = [
            cst.parse_statement("from typing import ClassVar"),
            cst.parse_statement("from pydantic import BaseModel, Field"),
            cst.parse_statement(
                "class Foo(BaseModel):\n"
                "    text: str = Field(description='hello')\n"
            ),
        ]
        module = cst.Module(body=body)
        rendered = module.code
        assert "from typing import ClassVar" in rendered
        assert "class Foo(BaseModel):" in rendered
        assert "Field(description='hello')" in rendered
        # And the rendered result re-parses cleanly
        cst.parse_module(rendered)

    def test_build_module_via_node_constructors(self):
        """Lower-level: node-by-node ClassDef, AnnAssign etc."""
        # class Foo:
        #     x: str = 'hi'
        cls_def = cst.ClassDef(
            name=cst.Name("Foo"),
            body=cst.IndentedBlock(body=[
                cst.SimpleStatementLine(body=[
                    cst.AnnAssign(
                        target=cst.Name("x"),
                        annotation=cst.Annotation(annotation=cst.Name("str")),
                        value=cst.SimpleString("'hi'"),
                    ),
                ]),
            ]),
        )
        module = cst.Module(body=[cls_def])
        rendered = module.code
        assert "class Foo:" in rendered
        assert "x: str = 'hi'" in rendered
        cst.parse_module(rendered)  # re-parses cleanly


# ---------------------------------------------------------------------------
# parse_statement / parse_expression shortcuts
# ---------------------------------------------------------------------------


class TestParseShortcuts:
    def test_parse_expression_for_field_call(self):
        """We'll use this to build Field(description='...') expressions."""
        expr = cst.parse_expression("Field(description='Allowed sentiments')")
        assert isinstance(expr, cst.Call)

    def test_parse_statement_for_field_assignment(self):
        """Build a `name: type = value` line via parse_statement."""
        stmt = cst.parse_statement("text: str = Field(description='Input text')")
        # parse_statement returns SimpleStatementLine for one-liners
        assert isinstance(stmt, cst.SimpleStatementLine)
        # Body is a sequence of small statements; first is the AnnAssign
        assert isinstance(stmt.body[0], cst.AnnAssign)

    def test_parse_statement_for_class_var_dict(self):
        """The auto_vars ClassVar dict pattern."""
        stmt = cst.parse_statement(
            "auto_vars: ClassVar[dict[str, str]] = {'sentiment_options': 'enum_names(Sentiment)'}"
        )
        assert isinstance(stmt, cst.SimpleStatementLine)
        assert isinstance(stmt.body[0], cst.AnnAssign)

    def test_parse_statement_for_compound_class_def(self):
        """Compound statements come back as their own type, not wrapped."""
        cls_stmt = cst.parse_statement(
            "class Foo(BaseModel):\n"
            "    pass\n"
        )
        assert isinstance(cls_stmt, cst.ClassDef)


# ---------------------------------------------------------------------------
# Modify an existing file via CSTTransformer
# ---------------------------------------------------------------------------


class TestCSTTransformer:
    def test_add_field_to_class_preserves_comments(self):
        """Insert a new field into an existing class body; comments stay."""
        source = (
            "from pydantic import BaseModel, Field\n"
            "\n"
            "\n"
            "class Inputs(BaseModel):\n"
            "    # important field\n"
            "    text: str = Field(description='input text')\n"
        )

        class AddField(cst.CSTTransformer):
            def leave_ClassDef(self, original_node, updated_node):
                if original_node.name.value != "Inputs":
                    return updated_node
                new_field = cst.parse_statement(
                    "sentiment: str = Field(description='detected sentiment')"
                )
                # ClassDef.body is an IndentedBlock; its body is the
                # sequence of statements we want to extend.
                new_body = list(updated_node.body.body) + [new_field]
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=new_body),
                )

        tree = cst.parse_module(source)
        modified = tree.visit(AddField())
        rendered = modified.code

        # The new field is present
        assert "sentiment: str = Field(description='detected sentiment')" in rendered
        # The old comment is preserved
        assert "# important field" in rendered
        # The original field is still there
        assert "text: str = Field(description='input text')" in rendered
        # Re-parses cleanly
        cst.parse_module(rendered)

    def test_insert_into_existing_list_literal(self):
        """Insert an entry into a class-level list (the ``nodes`` pattern)."""
        source = (
            "from llm_pipeline.graph import Step\n"
            "\n"
            "\n"
            "class TextAnalyzerPipeline:\n"
            "    nodes = [\n"
            "        Step(SentimentStep),\n"
            "    ]\n"
        )

        class InsertIntoNodes(cst.CSTTransformer):
            def leave_Assign(self, original_node, updated_node):
                # Only target the `nodes = [...]` assignment
                if not (
                    len(original_node.targets) == 1
                    and isinstance(original_node.targets[0].target, cst.Name)
                    and original_node.targets[0].target.value == "nodes"
                ):
                    return updated_node
                if not isinstance(updated_node.value, cst.List):
                    return updated_node
                new_entry = cst.Element(
                    value=cst.parse_expression("Step(SummaryStep)"),
                )
                new_elements = list(updated_node.value.elements) + [new_entry]
                return updated_node.with_changes(
                    value=updated_node.value.with_changes(elements=new_elements),
                )

        tree = cst.parse_module(source)
        modified = tree.visit(InsertIntoNodes())
        rendered = modified.code
        assert "Step(SentimentStep)" in rendered
        assert "Step(SummaryStep)" in rendered
        cst.parse_module(rendered)

    def test_replace_class_body_keeps_decorators_and_comments(self):
        """Regenerating a class from scratch but preserving its surroundings."""
        source = (
            "# Top-of-file comment\n"
            "from pydantic import BaseModel\n"
            "\n"
            "\n"
            "@some_decorator\n"
            "class Generated(BaseModel):\n"
            "    old_field: str = ''\n"
        )

        class ReplaceBody(cst.CSTTransformer):
            def leave_ClassDef(self, original_node, updated_node):
                if original_node.name.value != "Generated":
                    return updated_node
                new_body = cst.IndentedBlock(body=[
                    cst.parse_statement("brand_new: int = 0"),
                ])
                return updated_node.with_changes(body=new_body)

        tree = cst.parse_module(source)
        modified = tree.visit(ReplaceBody())
        rendered = modified.code

        # Body replaced
        assert "brand_new: int = 0" in rendered
        assert "old_field" not in rendered
        # Surroundings preserved
        assert "# Top-of-file comment" in rendered
        assert "@some_decorator" in rendered
        cst.parse_module(rendered)


# ---------------------------------------------------------------------------
# Generator pattern end-to-end: build a PromptVariables-shaped module
# ---------------------------------------------------------------------------


class TestPromptVariablesGeneratorPattern:
    """End-to-end smoke for the build-time generator we're going to write.

    Mimics the structure of ``llm_pipelines/variables/{name}.py``
    (flat shape — fields declared directly on the class):

        from typing import ClassVar
        from pydantic import Field
        from llm_pipeline.prompts.variables import PromptVariables


        class TopicExtractionPrompt(PromptVariables):
            text: str = Field(description="Input text")
            sentiment: str = Field(description="Detected sentiment")

            auto_vars: ClassVar[dict[str, str]] = {
                "sentiment_options": "enum_names(Sentiment)",
            }
    """

    def _build_field_stmt(
        self, name: str, annotation: str, description: str,
    ) -> cst.SimpleStatementLine:
        """Build ``{name}: {annotation} = Field(description={...})`` line."""
        return cst.parse_statement(
            f"{name}: {annotation} = "
            f"Field(description={description!r})"
        )

    def _build_classvar_dict(self, auto_vars: dict[str, str]) -> cst.SimpleStatementLine:
        """Build ``auto_vars: ClassVar[dict[str, str]] = {...}``."""
        if not auto_vars:
            literal = "{}"
        else:
            entries = ", ".join(
                f"{k!r}: {v!r}" for k, v in auto_vars.items()
            )
            literal = "{" + entries + "}"
        return cst.parse_statement(
            f"auto_vars: ClassVar[dict[str, str]] = {literal}"
        )

    def test_build_full_prompt_variables_module(self):
        # Fields declared directly on the prompt class; one auto_var.
        field_stmts = [
            self._build_field_stmt("text", "str", "Input text"),
            self._build_field_stmt("sentiment", "str", "Detected sentiment"),
        ]
        auto_vars_stmt = self._build_classvar_dict({
            "sentiment_options": "enum_names(Sentiment)",
        })

        outer_class = cst.ClassDef(
            name=cst.Name("TopicExtractionPrompt"),
            bases=[cst.Arg(value=cst.Name("PromptVariables"))],
            body=cst.IndentedBlock(body=[*field_stmts, auto_vars_stmt]),
        )

        module = cst.Module(body=[
            cst.parse_statement("from typing import ClassVar"),
            cst.parse_statement("from pydantic import Field"),
            cst.parse_statement(
                "from llm_pipeline.prompts.variables import PromptVariables"
            ),
            outer_class,
        ])
        rendered = module.code

        # Sanity: every part is in the rendered output
        assert "class TopicExtractionPrompt(PromptVariables):" in rendered
        assert "text: str = Field(description='Input text')" in rendered
        assert "sentiment: str = Field(description='Detected sentiment')" in rendered
        assert "auto_vars: ClassVar[dict[str, str]]" in rendered
        assert "'sentiment_options': 'enum_names(Sentiment)'" in rendered

        # Re-parses cleanly
        cst.parse_module(rendered)

        # Most strict check: the rendered code is valid Python and
        # importable as a module fragment. We compile() it to verify.
        compile(rendered, "<generated>", "exec")
