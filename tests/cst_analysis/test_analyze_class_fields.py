"""Tests for ``analyze_class_fields``.

Covers Pydantic-style field declarations:
- Type annotations (``$ref`` JSON Pointer entries)
- Direct default expressions (``/default``)
- ``Field(default=X, le=Y, ...)`` kwarg expressions (each kwarg
  mapped via ``PYDANTIC_KWARG_TO_JSON_SCHEMA``)
- Positional first arg of ``Field(...)`` -> ``/default``
- Composite expressions (refs aggregate at the enclosing pointer)
- Error surfaces.
"""
from __future__ import annotations

import textwrap

import pytest

from llm_pipeline.cst_analysis import analyze_class_fields
from llm_pipeline.cst_analysis.api import AnalysisError


def _resolver(table: dict[tuple[str, str], tuple[str, str]]):
    def hook(module_path: str, symbol: str) -> tuple[str, str] | None:
        return table.get((module_path, symbol))
    return hook


# ---------------------------------------------------------------------------
# Direct defaults
# ---------------------------------------------------------------------------


class TestDirectDefaults:
    def test_simple_default_expression(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES
            from pydantic import BaseModel

            class FooSchema(BaseModel):
                retries: int = MAX_RETRIES
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert "/properties/retries/default" in result
        refs = result["/properties/retries/default"]
        assert len(refs) == 1
        assert refs[0].name == "max_retries"

    def test_no_default_no_default_pointer(self):
        source = textwrap.dedent("""
            from pydantic import BaseModel

            class FooSchema(BaseModel):
                retries: int
        """)
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=_resolver({}),
        )
        # No default expression to walk.
        assert "/properties/retries/default" not in result


# ---------------------------------------------------------------------------
# Field() kwargs
# ---------------------------------------------------------------------------


class TestFieldKwargs:
    def test_default_kwarg_maps_to_default_pointer(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                retries: int = Field(default=MAX_RETRIES)
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert "/properties/retries/default" in result

    def test_le_maps_to_maximum(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                retries: int = Field(default=1, le=MAX_RETRIES)
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert "/properties/retries/maximum" in result
        refs = result["/properties/retries/maximum"]
        assert any(r.name == "max_retries" for r in refs)

    def test_multiple_kwargs_emit_separately(self):
        source = textwrap.dedent("""
            from pkg.constants import MIN_R, MAX_R
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                retries: int = Field(default=1, ge=MIN_R, le=MAX_R)
        """)
        resolver = _resolver({
            ("pkg.constants", "MIN_R"): ("constant", "min_r"),
            ("pkg.constants", "MAX_R"): ("constant", "max_r"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert "/properties/retries/minimum" in result
        assert "/properties/retries/maximum" in result
        assert result["/properties/retries/minimum"][0].name == "min_r"
        assert result["/properties/retries/maximum"][0].name == "max_r"

    def test_positional_first_arg_treated_as_default(self):
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                retries: int = Field(MAX_RETRIES, le=10)
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert "/properties/retries/default" in result
        assert result["/properties/retries/default"][0].name == "max_retries"

    def test_unmapped_kwarg_skipped(self):
        # A kwarg not in PYDANTIC_KWARG_TO_JSON_SCHEMA produces
        # no entry — forward-compatible with future Pydantic
        # additions, but means we silently miss those refs.
        source = textwrap.dedent("""
            from pkg.constants import X
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                retries: int = Field(default=1, alias=X)
        """)
        resolver = _resolver({("pkg.constants", "X"): ("constant", "x")})
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        # ``alias`` not in the kwarg map.
        assert all("alias" not in pointer for pointer in result.keys())


# ---------------------------------------------------------------------------
# Type annotations -> $ref
# ---------------------------------------------------------------------------


class TestTypeRefs:
    def test_enum_type_emits_ref(self):
        source = textwrap.dedent("""
            from pkg.enums import Sentiment
            from pydantic import BaseModel

            class FooSchema(BaseModel):
                sentiment: Sentiment
        """)
        resolver = _resolver({
            ("pkg.enums", "Sentiment"): ("enum", "sentiment"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert "/properties/sentiment/$ref" in result
        refs = result["/properties/sentiment/$ref"]
        assert refs[0].name == "sentiment"
        assert refs[0].kind == "enum"

    def test_unresolved_type_no_ref(self):
        source = textwrap.dedent("""
            from pydantic import BaseModel

            class FooSchema(BaseModel):
                raw: int
                name: str
        """)
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=_resolver({}),
        )
        assert result == {}


# ---------------------------------------------------------------------------
# Composite expressions
# ---------------------------------------------------------------------------


class TestCompositeExpressions:
    def test_arithmetic_expression_aggregates_refs_at_pointer(self):
        # ``MAX_RETRIES * 2`` in ``le=`` -> a single ref at /maximum.
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                retries: int = Field(default=1, le=MAX_RETRIES * 2)
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        refs = result["/properties/retries/maximum"]
        assert len(refs) == 1
        assert refs[0].name == "max_retries"

    def test_repeated_use_dedupes_within_pointer(self):
        # Same symbol referenced twice in one expression -> single
        # ref entry under that pointer.
        source = textwrap.dedent("""
            from pkg.constants import X
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                value: int = Field(default=1, le=X + X)
        """)
        resolver = _resolver({("pkg.constants", "X"): ("constant", "x")})
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        assert len(result["/properties/value/maximum"]) == 1

    def test_two_distinct_symbols_emit_two_refs(self):
        source = textwrap.dedent("""
            from pkg.constants import A, B
            from pydantic import BaseModel, Field

            class FooSchema(BaseModel):
                v: int = Field(default=A + B)
        """)
        resolver = _resolver({
            ("pkg.constants", "A"): ("constant", "a"),
            ("pkg.constants", "B"): ("constant", "b"),
        })
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        refs = result["/properties/v/default"]
        names = sorted(r.name for r in refs)
        assert names == ["a", "b"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_class_raises(self):
        with pytest.raises(AnalysisError, match="not found"):
            analyze_class_fields(
                source="class Other: pass\n",
                class_qualname="FooSchema",
                resolver=_resolver({}),
            )

    def test_parse_error_raises(self):
        with pytest.raises(AnalysisError, match="failed to parse"):
            analyze_class_fields(
                source="class Broken(:\n",
                class_qualname="Broken",
                resolver=_resolver({}),
            )

    def test_empty_class_returns_empty_dict(self):
        source = textwrap.dedent("""
            from pydantic import BaseModel

            class FooSchema(BaseModel):
                pass
        """)
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=_resolver({}),
        )
        assert result == {}


# ---------------------------------------------------------------------------
# Position fields are sentinel
# ---------------------------------------------------------------------------


class TestSentinelPositions:
    def test_emitted_refs_have_sentinel_positions(self):
        # JSON-Pointer-keyed refs leave line/col at the
        # "not applicable" sentinel.
        source = textwrap.dedent("""
            from pkg.constants import X
            from pydantic import BaseModel

            class FooSchema(BaseModel):
                v: int = X
        """)
        resolver = _resolver({("pkg.constants", "X"): ("constant", "x")})
        result = analyze_class_fields(
            source=source,
            class_qualname="FooSchema",
            resolver=resolver,
        )
        ref = result["/properties/v/default"][0]
        assert ref.line == -1
        assert ref.col_start == 0
        assert ref.col_end == 0
