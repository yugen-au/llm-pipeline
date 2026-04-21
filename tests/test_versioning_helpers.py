"""Unit tests for llm_pipeline.utils.versioning helpers."""
import pytest

from llm_pipeline.utils.versioning import compare_versions


class TestCompareVersions:
    """Tests for compare_versions — covers _bump_minor edge cases from PLAN Step 1."""

    def test_less_than(self):
        assert compare_versions("1.0", "1.1") == -1

    def test_greater_than(self):
        assert compare_versions("1.1", "1.0") == 1

    def test_equal(self):
        assert compare_versions("1.0", "1.0") == 0

    def test_numeric_not_lexicographic(self):
        # "1.10" > "1.9" numerically, but lexicographic would say otherwise
        assert compare_versions("1.10", "1.9") == 1

    def test_major_dominates(self):
        assert compare_versions("2.0", "1.99") == 1

    def test_unequal_depth_greater(self):
        assert compare_versions("1.0.1", "1.0") == 1

    def test_unequal_depth_equal(self):
        # Trailing zeros are equivalent
        assert compare_versions("1.0.0", "1.0") == 0

    def test_single_segment(self):
        assert compare_versions("2", "1") == 1
        assert compare_versions("1", "2") == -1
        assert compare_versions("1", "1") == 0

    def test_three_segments(self):
        assert compare_versions("1.2.3", "1.2.4") == -1
        assert compare_versions("1.2.4", "1.2.3") == 1
        assert compare_versions("1.2.3", "1.2.3") == 0

    def test_zero_padded_depth(self):
        # "1.0.0.0" == "1"
        assert compare_versions("1.0.0.0", "1") == 0

    def test_large_minor(self):
        assert compare_versions("1.100", "1.99") == 1
