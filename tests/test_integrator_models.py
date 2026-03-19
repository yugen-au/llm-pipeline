"""
Unit tests for GeneratedStep and IntegrationResult in llm_pipeline/creator/models.py.

Tests cover:
- GeneratedStep.from_draft() field extraction
- PascalCase class name derivation
- Optional extraction_code when key missing
- all_artifacts dict preservation
- IntegrationResult field structure
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_pipeline.creator.models import GeneratedStep, IntegrationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft(name: str, include_extraction: bool = True) -> MagicMock:
    """Build a minimal DraftStep mock with generated_code matching naming convention."""
    draft = MagicMock()
    draft.name = name
    gc = {
        f"{name}_step.py": f"class {name.title().replace('_', '')}Step: pass",
        f"{name}_instructions.py": f"class {name.title().replace('_', '')}Instructions: pass",
        f"{name}_prompts.py": f"ALL_PROMPTS = []",
    }
    if include_extraction:
        gc[f"{name}_extraction.py"] = f"class {name.title().replace('_', '')}Extraction: pass"
    draft.generated_code = gc
    return draft


# ---------------------------------------------------------------------------
# TestGeneratedStep
# ---------------------------------------------------------------------------


class TestGeneratedStep:
    """Tests for GeneratedStep.from_draft() factory."""

    def test_from_draft_extracts_step_code(self):
        """from_draft() sets step_code from '{name}_step.py' key."""
        draft = _make_draft("sentiment_analysis")
        result = GeneratedStep.from_draft(draft)
        assert result.step_code == draft.generated_code["sentiment_analysis_step.py"]

    def test_from_draft_extracts_instructions_code(self):
        """from_draft() sets instructions_code from '{name}_instructions.py' key."""
        draft = _make_draft("topic_extraction")
        result = GeneratedStep.from_draft(draft)
        assert result.instructions_code == draft.generated_code["topic_extraction_instructions.py"]

    def test_from_draft_extracts_prompts_code(self):
        """from_draft() sets prompts_code from '{name}_prompts.py' key."""
        draft = _make_draft("summary")
        result = GeneratedStep.from_draft(draft)
        assert result.prompts_code == draft.generated_code["summary_prompts.py"]

    def test_from_draft_extracts_extraction_code(self):
        """from_draft() sets extraction_code from '{name}_extraction.py' key when present."""
        draft = _make_draft("sentiment_analysis", include_extraction=True)
        result = GeneratedStep.from_draft(draft)
        assert result.extraction_code == draft.generated_code["sentiment_analysis_extraction.py"]

    def test_from_draft_extraction_code_none_when_missing(self):
        """from_draft() sets extraction_code=None when key absent from generated_code."""
        draft = _make_draft("simple_step", include_extraction=False)
        result = GeneratedStep.from_draft(draft)
        assert result.extraction_code is None

    def test_from_draft_derives_step_class_name(self):
        """from_draft() derives step_class_name as PascalCase + 'Step'."""
        draft = _make_draft("sentiment_analysis")
        result = GeneratedStep.from_draft(draft)
        assert result.step_class_name == "SentimentAnalysisStep"

    def test_from_draft_derives_instructions_class_name(self):
        """from_draft() derives instructions_class_name as PascalCase + 'Instructions'."""
        draft = _make_draft("sentiment_analysis")
        result = GeneratedStep.from_draft(draft)
        assert result.instructions_class_name == "SentimentAnalysisInstructions"

    def test_from_draft_single_word_step_name(self):
        """from_draft() handles single-word step names without underscores."""
        draft = _make_draft("summary")
        result = GeneratedStep.from_draft(draft)
        assert result.step_class_name == "SummaryStep"
        assert result.instructions_class_name == "SummaryInstructions"

    def test_from_draft_multi_segment_step_name(self):
        """from_draft() handles three-segment snake_case names."""
        draft = _make_draft("topic_extraction_v2")
        result = GeneratedStep.from_draft(draft)
        assert result.step_class_name == "TopicExtractionV2Step"
        assert result.instructions_class_name == "TopicExtractionV2Instructions"

    def test_from_draft_step_name_preserved(self):
        """from_draft() preserves original step_name unchanged."""
        draft = _make_draft("sentiment_analysis")
        result = GeneratedStep.from_draft(draft)
        assert result.step_name == "sentiment_analysis"

    def test_from_draft_all_artifacts_preserved(self):
        """from_draft() stores full generated_code dict in all_artifacts."""
        draft = _make_draft("sentiment_analysis", include_extraction=True)
        result = GeneratedStep.from_draft(draft)
        assert result.all_artifacts == draft.generated_code

    def test_from_draft_all_artifacts_is_copy(self):
        """all_artifacts is an independent copy, not a reference to draft.generated_code."""
        draft = _make_draft("sentiment_analysis")
        result = GeneratedStep.from_draft(draft)
        result.all_artifacts["mutated"] = "x"
        # original should not contain the mutated key if it is a copy
        assert "mutated" not in draft.generated_code

    def test_from_draft_all_artifacts_includes_extra_keys(self):
        """Extra keys in generated_code beyond standard names appear in all_artifacts."""
        draft = _make_draft("sentiment_analysis")
        draft.generated_code["extra_file.py"] = "# extra"
        result = GeneratedStep.from_draft(draft)
        assert "extra_file.py" in result.all_artifacts

    def test_from_draft_without_extraction_all_artifacts_has_three_files(self):
        """Without extraction, all_artifacts contains exactly the 3 standard files."""
        draft = _make_draft("summary", include_extraction=False)
        result = GeneratedStep.from_draft(draft)
        assert len(result.all_artifacts) == 3

    def test_from_draft_with_extraction_all_artifacts_has_four_files(self):
        """With extraction, all_artifacts contains exactly the 4 standard files."""
        draft = _make_draft("summary", include_extraction=True)
        result = GeneratedStep.from_draft(draft)
        assert len(result.all_artifacts) == 4

    def test_from_draft_raises_on_missing_step_file(self):
        """from_draft() raises KeyError if '{name}_step.py' key is absent."""
        draft = MagicMock()
        draft.name = "broken_step"
        draft.generated_code = {
            "broken_step_instructions.py": "x",
            "broken_step_prompts.py": "y",
        }
        with pytest.raises(KeyError):
            GeneratedStep.from_draft(draft)

    def test_from_draft_raises_on_missing_instructions_file(self):
        """from_draft() raises KeyError if '{name}_instructions.py' key is absent."""
        draft = MagicMock()
        draft.name = "broken_step"
        draft.generated_code = {
            "broken_step_step.py": "x",
            "broken_step_prompts.py": "y",
        }
        with pytest.raises(KeyError):
            GeneratedStep.from_draft(draft)

    def test_from_draft_raises_on_missing_prompts_file(self):
        """from_draft() raises KeyError if '{name}_prompts.py' key is absent."""
        draft = MagicMock()
        draft.name = "broken_step"
        draft.generated_code = {
            "broken_step_step.py": "x",
            "broken_step_instructions.py": "y",
        }
        with pytest.raises(KeyError):
            GeneratedStep.from_draft(draft)


# ---------------------------------------------------------------------------
# TestIntegrationResult
# ---------------------------------------------------------------------------


class TestIntegrationResult:
    """Tests for IntegrationResult Pydantic model fields and validation."""

    def test_default_construction(self):
        """IntegrationResult can be constructed with all required fields."""
        result = IntegrationResult(
            files_written=["/some/path/step.py"],
            prompts_registered=2,
            pipeline_file_updated=True,
            target_dir="/some/path",
        )
        assert result.files_written == ["/some/path/step.py"]
        assert result.prompts_registered == 2
        assert result.pipeline_file_updated is True
        assert result.target_dir == "/some/path"

    def test_empty_files_written(self):
        """IntegrationResult accepts empty files_written list."""
        result = IntegrationResult(
            files_written=[],
            prompts_registered=0,
            pipeline_file_updated=False,
            target_dir="/tmp",
        )
        assert result.files_written == []

    def test_pipeline_file_updated_false(self):
        """pipeline_file_updated=False when no pipeline file was modified."""
        result = IntegrationResult(
            files_written=[],
            prompts_registered=0,
            pipeline_file_updated=False,
            target_dir="/tmp",
        )
        assert result.pipeline_file_updated is False

    def test_multiple_files_written(self):
        """files_written list preserves multiple paths in order."""
        paths = ["/a/step.py", "/a/instructions.py", "/a/prompts.py"]
        result = IntegrationResult(
            files_written=paths,
            prompts_registered=4,
            pipeline_file_updated=True,
            target_dir="/a",
        )
        assert result.files_written == paths
