"""Tests for the ``Variant`` model + ``apply_instruction_delta``.

Consolidates coverage previously split across the legacy
``test_eval_variants.py`` and ``test_apply_instruction_delta.py``
modules. Just the load-bearing behaviours: typed Variant fields,
baseline detection, and the security-sensitive surface of
``apply_instruction_delta`` (whitelist enforcement, JSON-only
defaults, no eval/exec/importlib).
"""
from __future__ import annotations

from typing import ClassVar

import pytest

from llm_pipeline.evals.variants import (
    Variant,
    apply_instruction_delta,
    get_type_whitelist,
    merge_variable_definitions,
)
from llm_pipeline.graph.instructions import LLMResultMixin


# ---------------------------------------------------------------------------
# Variant model
# ---------------------------------------------------------------------------


class TestVariant:
    def test_baseline_default_values(self):
        v = Variant()
        assert v.model is None
        assert v.prompt_overrides == {}
        assert v.instructions_delta == []
        assert v.is_baseline() is True

    def test_is_baseline_false_when_model_set(self):
        v = Variant(model="gpt-5")
        assert v.is_baseline() is False

    def test_is_baseline_false_when_overrides_set(self):
        v = Variant(prompt_overrides={"step": "X: {x}"})
        assert v.is_baseline() is False

    def test_is_baseline_false_when_delta_set(self):
        v = Variant(instructions_delta=[{"op": "modify", "field": "x", "default": 1}])
        assert v.is_baseline() is False

    def test_model_dump_round_trip(self):
        v = Variant(
            model="m",
            prompt_overrides={"a": "x"},
            instructions_delta=[
                {"op": "add", "field": "y", "type_str": "str", "default": "z"},
            ],
        )
        round_tripped = Variant.model_validate(v.model_dump())
        assert round_tripped == v


# ---------------------------------------------------------------------------
# apply_instruction_delta
# ---------------------------------------------------------------------------


class _Base(LLMResultMixin):
    label: str = ""

    example: ClassVar[dict] = {"label": "x", "confidence_score": 0.9}


class TestApplyDelta:
    def test_empty_delta_returns_base_unchanged(self):
        assert apply_instruction_delta(_Base, []) is _Base
        assert apply_instruction_delta(_Base, None) is _Base

    def test_add_field(self):
        cls = apply_instruction_delta(
            _Base,
            [{"op": "add", "field": "score", "type_str": "float", "default": 0.5}],
        )
        instance = cls(label="x", score=0.7)
        assert instance.score == 0.7

    def test_add_requires_default(self):
        with pytest.raises(ValueError, match="requires a default"):
            apply_instruction_delta(
                _Base,
                [{"op": "add", "field": "score", "type_str": "float"}],
            )

    def test_add_requires_type_str(self):
        with pytest.raises(ValueError, match="requires type_str"):
            apply_instruction_delta(
                _Base,
                [{"op": "add", "field": "score", "default": 0.0}],
            )

    def test_modify_existing_field_default(self):
        cls = apply_instruction_delta(
            _Base,
            [{"op": "modify", "field": "label", "default": "new_default"}],
        )
        instance = cls()
        assert instance.label == "new_default"

    def test_unknown_op_rejected(self):
        with pytest.raises(ValueError, match="op must be one of"):
            apply_instruction_delta(
                _Base,
                [{"op": "remove", "field": "label"}],
            )

    def test_unknown_type_rejected(self):
        with pytest.raises(ValueError, match="not in whitelist"):
            apply_instruction_delta(
                _Base,
                [{"op": "add", "field": "x", "type_str": "set", "default": []}],
            )

    def test_invalid_field_name_rejected(self):
        with pytest.raises(ValueError, match="not a valid identifier"):
            apply_instruction_delta(
                _Base,
                [{"op": "add", "field": "Bad-Name", "type_str": "str", "default": ""}],
            )

    def test_dunder_field_rejected(self):
        with pytest.raises(ValueError):
            apply_instruction_delta(
                _Base,
                [{"op": "add", "field": "__class__", "type_str": "str", "default": ""}],
            )

    def test_non_json_default_rejected(self):
        with pytest.raises(ValueError):
            apply_instruction_delta(
                _Base,
                [{"op": "add", "field": "x", "type_str": "str", "default": object()}],
            )


# ---------------------------------------------------------------------------
# Type whitelist + variable merge
# ---------------------------------------------------------------------------


class TestTypeWhitelist:
    def test_includes_scalars(self):
        wl = get_type_whitelist()
        assert "str" in wl
        assert "int" in wl
        assert "Optional[str]" in wl

    def test_excludes_dangerous_types(self):
        wl = get_type_whitelist()
        for forbidden in ("set", "type", "object", "Any", "tuple"):
            assert forbidden not in wl


class TestMergeVariableDefinitions:
    def test_both_none(self):
        assert merge_variable_definitions(None, None) == []

    def test_variant_wins_on_conflict(self):
        prod = [{"name": "x", "value": "prod"}]
        variant = [{"name": "x", "value": "variant"}]
        merged = merge_variable_definitions(prod, variant)
        assert merged == [{"name": "x", "value": "variant"}]

    def test_union_by_name(self):
        prod = [{"name": "a"}, {"name": "b"}]
        variant = [{"name": "c"}]
        merged = merge_variable_definitions(prod, variant)
        names = sorted(item["name"] for item in merged)
        assert names == ["a", "b", "c"]
