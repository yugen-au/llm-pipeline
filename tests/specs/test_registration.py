"""Tests for ``ArtifactRegistration``."""
from __future__ import annotations

from llm_pipeline.specs import (
    ArtifactRegistration,
    ConstantSpec,
    KIND_CONSTANT,
)


class TestArtifactRegistration:
    def test_pairs_spec_and_obj(self):
        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="max_retries", cls="m.MAX_RETRIES",
            source_path="/x.py", value_type="int", value=3,
        )
        reg = ArtifactRegistration(spec=spec, obj=3)
        assert reg.spec is spec
        assert reg.obj == 3

    def test_kind_and_name_proxy_to_spec(self):
        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="x", cls="m.X",
            source_path="/x.py", value_type="int", value=1,
        )
        reg = ArtifactRegistration(spec=spec, obj=1)
        assert reg.kind == KIND_CONSTANT
        assert reg.name == "x"

    def test_obj_can_be_class_or_value(self):
        # Class artifacts: obj is the class itself.
        class Dummy:
            pass

        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="dummy", cls="m.Dummy",
            source_path="/x.py", value_type="type", value=None,
        )
        reg_with_cls = ArtifactRegistration(spec=spec, obj=Dummy)
        assert reg_with_cls.obj is Dummy

        # Value artifacts: obj is the raw value (str / int / dict / etc.).
        reg_with_value = ArtifactRegistration(spec=spec, obj=42)
        assert reg_with_value.obj == 42

    def test_frozen(self):
        import dataclasses
        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="x", cls="m.X",
            source_path="/x.py", value_type="int", value=1,
        )
        reg = ArtifactRegistration(spec=spec, obj=1)
        # Cannot reassign fields on a frozen dataclass.
        try:
            reg.spec = spec  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("frozen=True is not enforced")
