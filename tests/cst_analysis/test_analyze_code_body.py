"""Tests for ``analyze_code_body``.

Covers function-body name resolution, body-local position math,
qualname matching for methods vs module-level functions,
nested-function isolation, and error surfaces.
"""
from __future__ import annotations

import textwrap

import pytest

from llm_pipeline.cst_analysis import analyze_code_body
from llm_pipeline.cst_analysis.api import AnalysisError


# ---------------------------------------------------------------------------
# Resolver fakes
# ---------------------------------------------------------------------------


def _resolver(table: dict[tuple[str, str], tuple[str, str]]):
    """Build a resolver that returns ``table[(module, symbol)]`` or None."""
    def hook(module_path: str, symbol: str) -> tuple[str, str] | None:
        return table.get((module_path, symbol))
    return hook


# ---------------------------------------------------------------------------
# Module-level function
# ---------------------------------------------------------------------------


class TestModuleLevelFunction:
    def test_emits_ref_for_imported_constant(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES

            def runner():
                value = MAX_RETRIES
                return value
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=resolver,
        )
        assert len(spec.refs) == 1
        ref = spec.refs[0]
        assert ref.symbol == "MAX_RETRIES"
        assert ref.kind == "constant"
        assert ref.name == "max_retries"

    def test_body_source_excludes_signature(self):
        source = textwrap.dedent("""
            def runner():
                value = 1
                return value
        """).lstrip()
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=_resolver({}),
        )
        # Body should be the indented lines after ``def runner():``,
        # NOT including the def line itself.
        assert "def runner" not in spec.source
        assert "value = 1" in spec.source
        assert "return value" in spec.source

    def test_line_offset_is_zero_indexed_file_line_of_body_start(self):
        # Body starts on line 1 (0-indexed) — the second line of the file
        # since the def is on line 0.
        source = "def runner():\n    value = 1\n"
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=_resolver({}),
        )
        assert spec.line_offset_in_file == 1

    def test_unresolved_imports_dont_emit(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES, OTHER

            def runner():
                a = MAX_RETRIES
                b = OTHER
                return a, b
        """)
        # Resolver only knows MAX_RETRIES — OTHER goes unresolved.
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=resolver,
        )
        symbols = [r.symbol for r in spec.refs]
        assert "MAX_RETRIES" in symbols
        assert "OTHER" not in symbols

    def test_local_variables_dont_emit(self):
        source = textwrap.dedent("""
            def runner():
                x = 1
                return x
        """)
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=_resolver({}),
        )
        assert spec.refs == []


# ---------------------------------------------------------------------------
# Methods (qualname matching)
# ---------------------------------------------------------------------------


class TestMethodQualname:
    def test_method_qualname_matches(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES

            class FooStep:
                def prepare(self, inputs):
                    return [MAX_RETRIES]

                def run(self, ctx):
                    return None
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        spec = analyze_code_body(
            source=source,
            function_qualname="FooStep.prepare",
            resolver=resolver,
        )
        assert len(spec.refs) == 1

    def test_only_target_method_body_processed(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES

            class FooStep:
                def prepare(self, inputs):
                    return [1]

                def run(self, ctx):
                    return MAX_RETRIES  # in run, NOT prepare
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        # Targeting prepare — refs from run() should NOT appear.
        spec = analyze_code_body(
            source=source,
            function_qualname="FooStep.prepare",
            resolver=resolver,
        )
        assert spec.refs == []

    def test_nested_class_qualname(self):
        source = textwrap.dedent("""
            from pkg.constants import X

            class Outer:
                class Inner:
                    def go(self):
                        return X
        """)
        resolver = _resolver({("pkg.constants", "X"): ("constant", "x")})
        spec = analyze_code_body(
            source=source,
            function_qualname="Outer.Inner.go",
            resolver=resolver,
        )
        assert len(spec.refs) == 1
        assert spec.refs[0].name == "x"


# ---------------------------------------------------------------------------
# Imports — aliased + import-as
# ---------------------------------------------------------------------------


class TestImportShapes:
    def test_aliased_import(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES as MR

            def runner():
                return MR
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=resolver,
        )
        assert len(spec.refs) == 1
        # The local-scope name is what's used in source; resolver
        # keys off the *original* symbol on the imported module.
        assert spec.refs[0].symbol == "MR"
        assert spec.refs[0].name == "max_retries"

    def test_attribute_access_resolves_via_leftmost_name(self):
        # ``Sentiment.POSITIVE`` should resolve via ``Sentiment``,
        # not ``POSITIVE`` (which isn't separately imported).
        source = textwrap.dedent("""
            from pkg.enums import Sentiment

            def runner():
                return Sentiment.POSITIVE
        """)
        resolver = _resolver({("pkg.enums", "Sentiment"): ("enum", "sentiment")})
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=resolver,
        )
        assert len(spec.refs) == 1
        assert spec.refs[0].symbol == "Sentiment"
        assert spec.refs[0].kind == "enum"

    def test_relative_import_skipped(self):
        # Relative imports (``from . import x``) skipped by the
        # resolver — Phase B doesn't have package context.
        source = textwrap.dedent("""
            from . import x

            def runner():
                return x
        """)
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=_resolver({}),
        )
        # Even with no resolver hits, no crash.
        assert spec.refs == []


# ---------------------------------------------------------------------------
# Position output
# ---------------------------------------------------------------------------


class TestPositionOutput:
    def test_body_local_line_zero_for_first_body_line(self):
        source = textwrap.dedent("""
            from pkg.constants import X

            def runner():
                v = X
                return v
        """).lstrip()
        # File:
        # line 0: from pkg.constants import X
        # line 1: (blank)
        # line 2: def runner():
        # line 3:     v = X
        # line 4:     return v
        resolver = _resolver({("pkg.constants", "X"): ("constant", "x")})
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=resolver,
        )
        assert spec.line_offset_in_file == 3  # body starts at file line 3
        assert len(spec.refs) == 1
        # Body line 0 is ``    v = X``. ``X`` is at col 8.
        assert spec.refs[0].line == 0
        assert spec.refs[0].col_start == 8
        assert spec.refs[0].col_end == 9

    def test_multiple_refs_in_same_body(self):
        source = textwrap.dedent("""
            from pkg.constants import A, B

            def runner():
                a = A
                b = B
                return a + b
        """).lstrip()
        resolver = _resolver({
            ("pkg.constants", "A"): ("constant", "a"),
            ("pkg.constants", "B"): ("constant", "b"),
        })
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=resolver,
        )
        symbols = [r.symbol for r in spec.refs]
        assert "A" in symbols
        assert "B" in symbols
        # Distinct lines.
        lines = {r.symbol: r.line for r in spec.refs}
        assert lines["A"] != lines["B"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_function_raises(self):
        with pytest.raises(AnalysisError, match="not found"):
            analyze_code_body(
                source="def other(): pass\n",
                function_qualname="missing",
                resolver=_resolver({}),
            )

    def test_parse_error_raises(self):
        with pytest.raises(AnalysisError, match="failed to parse"):
            analyze_code_body(
                source="def broken(:\n",
                function_qualname="broken",
                resolver=_resolver({}),
            )

    def test_empty_function_returns_empty_refs(self):
        source = "def runner():\n    pass\n"
        spec = analyze_code_body(
            source=source,
            function_qualname="runner",
            resolver=_resolver({}),
        )
        assert spec.refs == []
        assert "pass" in spec.source
