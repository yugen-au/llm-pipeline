"""Tests for :func:`make_resolver`.

The resolver hook is the bridge between cst_analysis (which sees
imports) and the per-kind registries (which know which (kind, name)
each artifact registers under). Tests here pin the lookup
behaviour against synthetic registry states.
"""
from __future__ import annotations

from llm_pipeline.discovery import init_empty_registries
from llm_pipeline.discovery.resolver import make_resolver
from llm_pipeline.artifacts import (
    ArtifactRegistration,
    ConstantSpec,
    EnumMemberSpec,
    EnumSpec,
    KIND_CONSTANT,
    KIND_ENUM,
)


class TestEmptyRegistries:
    def test_returns_none_for_any_lookup(self):
        regs = init_empty_registries()
        resolver = make_resolver(regs)
        assert resolver("any.module", "ANY_SYMBOL") is None
        assert resolver("", "") is None


class TestSinglePopulatedRegistry:
    def test_resolves_constant_by_full_path(self):
        regs = init_empty_registries()
        spec = ConstantSpec(
            kind=KIND_CONSTANT,
            name="max_retries",
            cls="pkg.constants.retries.MAX_RETRIES",
            source_path="/x.py",
            value_type="int",
            value=3,
        )
        regs[KIND_CONSTANT]["max_retries"] = ArtifactRegistration(
            spec=spec, obj=3,
        )
        resolver = make_resolver(regs)
        assert resolver("pkg.constants.retries", "MAX_RETRIES") == (
            KIND_CONSTANT, "max_retries",
        )

    def test_returns_none_for_unregistered(self):
        regs = init_empty_registries()
        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="x", cls="pkg.X",
            source_path="/x.py", value_type="int", value=1,
        )
        regs[KIND_CONSTANT]["x"] = ArtifactRegistration(spec=spec, obj=1)
        resolver = make_resolver(regs)
        assert resolver("pkg", "OTHER") is None
        assert resolver("other.pkg", "X") is None


class TestMultipleKindsResolved:
    def test_resolver_finds_correct_kind(self):
        regs = init_empty_registries()
        # Constant
        c_spec = ConstantSpec(
            kind=KIND_CONSTANT, name="max_retries",
            cls="pkg.constants.MAX_RETRIES",
            source_path="/c.py", value_type="int", value=3,
        )
        regs[KIND_CONSTANT]["max_retries"] = ArtifactRegistration(
            spec=c_spec, obj=3,
        )
        # Enum
        e_spec = EnumSpec(
            kind=KIND_ENUM, name="sentiment",
            cls="pkg.enums.Sentiment",
            source_path="/e.py", value_type="str",
            members=[EnumMemberSpec(name="POSITIVE", value="pos")],
        )
        regs[KIND_ENUM]["sentiment"] = ArtifactRegistration(
            spec=e_spec, obj=object(),
        )

        resolver = make_resolver(regs)
        assert resolver("pkg.constants", "MAX_RETRIES") == (
            KIND_CONSTANT, "max_retries",
        )
        assert resolver("pkg.enums", "Sentiment") == (
            KIND_ENUM, "sentiment",
        )

    def test_resolver_is_snapshot_at_call(self):
        # ``make_resolver`` builds the reverse-index at call time;
        # later mutations to ``regs`` are NOT reflected. This is
        # the documented contract — callers using two-pass
        # discovery call ``make_resolver`` again after pass 1.
        regs = init_empty_registries()
        resolver = make_resolver(regs)

        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="late",
            cls="pkg.LATE", source_path="/x.py",
            value_type="int", value=99,
        )
        regs[KIND_CONSTANT]["late"] = ArtifactRegistration(
            spec=spec, obj=99,
        )
        # The pre-mutation resolver doesn't see the new entry.
        assert resolver("pkg", "LATE") is None
        # Re-built resolver does.
        new_resolver = make_resolver(regs)
        assert new_resolver("pkg", "LATE") == (KIND_CONSTANT, "late")
