"""
Tests for llm_pipeline/creator/sample_data.py: SampleDataGenerator.
"""
from __future__ import annotations

import json

import pytest

from llm_pipeline.creator.models import FieldDefinition
from llm_pipeline.creator.sample_data import SampleDataGenerator


def _field(
    name: str,
    type_annotation: str,
    description: str = "test field",
    default: str | None = None,
    is_required: bool = True,
) -> FieldDefinition:
    return FieldDefinition(
        name=name,
        type_annotation=type_annotation,
        description=description,
        default=default,
        is_required=is_required,
    )


class TestSampleDataGenerator:
    def setup_method(self):
        self.gen = SampleDataGenerator()

    def test_str_field_generates_test_name(self):
        fields = [_field("sentiment", "str")]
        result = self.gen.generate(fields)
        assert result == {"sentiment": "test_sentiment"}

    def test_int_field_generates_1(self):
        fields = [_field("count", "int")]
        result = self.gen.generate(fields)
        assert result["count"] == 1

    def test_float_field_generates_1_0(self):
        fields = [_field("score", "float")]
        result = self.gen.generate(fields)
        assert result["score"] == 1.0

    def test_bool_field_generates_true(self):
        fields = [_field("is_active", "bool")]
        result = self.gen.generate(fields)
        assert result["is_active"] is True

    def test_list_str_field(self):
        fields = [_field("tags", "list[str]")]
        result = self.gen.generate(fields)
        assert result["tags"] == ["test_item"]

    def test_dict_field(self):
        fields = [_field("metadata", "dict[str, str]")]
        result = self.gen.generate(fields)
        assert result["metadata"] == {"key": "value"}

    def test_optional_not_required_returns_none(self):
        fields = [_field("note", "str | None", is_required=False)]
        result = self.gen.generate(fields)
        assert result["note"] is None

    def test_field_with_default_uses_default_string(self):
        # default='""' should parse to empty string
        fields = [_field("label", "str", default='""')]
        result = self.gen.generate(fields)
        assert result["label"] == ""

    def test_field_with_default_uses_default_int(self):
        # default='42' should parse to integer 42
        fields = [_field("retries", "int", default="42")]
        result = self.gen.generate(fields)
        assert result["retries"] == 42

    def test_empty_fields_returns_empty_dict(self):
        result = self.gen.generate([])
        assert result == {}

    def test_generate_json_returns_valid_json_string(self):
        fields = [
            _field("sentiment", "str"),
            _field("count", "int"),
        ]
        json_str = self.gen.generate_json(fields)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert parsed["sentiment"] == "test_sentiment"
        assert parsed["count"] == 1

    def test_unknown_type_annotation_returns_string_fallback(self):
        # Unrecognized annotation should not raise; should return a string
        fields = [_field("custom", "MyCustomType")]
        result = self.gen.generate(fields)
        assert isinstance(result["custom"], str)
