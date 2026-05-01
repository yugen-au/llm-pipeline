"""Lock down the routing contract between Fields classes and specs.

Two contracts under test:

1. **Constants ↔ spec fields sync**: every constant declared on a
   per-kind ``*Fields`` class must name an existing field on the
   matching spec, and that field must be ``ArtifactField``-typed.
   If someone renames a spec field without updating the constants
   class (or vice-versa), this test fires before any class with
   the broken constant is ever loaded.

2. **Strict ``attach_class_captures`` enforcement**: ``location.field``
   that's unknown or points at a non-ArtifactField target raises
   ``RuntimeError`` immediately rather than silently falling back
   to ``self.issues`` (which would lose the issue from any
   structurally-routed UI surface).

Together these prevent the silent-drift class of bug the typed-
fields-class design was built to catch.
"""
from __future__ import annotations

import pytest

from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation
from llm_pipeline.specs import (
    ExtractionFields,
    ExtractionSpec,
    KIND_EXTRACTION,
    KIND_REVIEW,
    KIND_STEP,
    PromptData,
    PromptDataFields,
    PromptVariableDefs,
    ReviewFields,
    ReviewSpec,
    StepFields,
    StepSpec,
)
from llm_pipeline.specs.base import _is_artifact_field_type


# ---------------------------------------------------------------------------
# Contract 1: every constant value names an ArtifactField-typed spec field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields_cls,spec_cls",
    [
        (StepFields, StepSpec),
        (ExtractionFields, ExtractionSpec),
        (ReviewFields, ReviewSpec),
        (PromptDataFields, PromptData),
    ],
    ids=["step", "extraction", "review", "prompt_data"],
)
class TestFieldsConstantsMatchSpec:
    """For every (FieldsCls, SpecCls) pair, every public string
    constant on FieldsCls names a field on SpecCls whose annotation
    declares an ``ArtifactField`` slot — i.e. a routable target."""

    def test_every_constant_is_a_spec_field(self, fields_cls, spec_cls):
        spec_fields = spec_cls.model_fields
        for attr_name, value in self._iter_constants(fields_cls):
            assert value in spec_fields, (
                f"{fields_cls.__name__}.{attr_name}={value!r} is not a "
                f"field on {spec_cls.__name__}. Either rename the "
                f"constant to match the spec, drop the constant, or "
                f"add the spec field."
            )

    def test_every_constant_targets_an_artifact_field(self, fields_cls, spec_cls):
        spec_fields = spec_cls.model_fields
        for attr_name, value in self._iter_constants(fields_cls):
            annotation = spec_fields[value].annotation
            assert _is_artifact_field_type(annotation), (
                f"{fields_cls.__name__}.{attr_name}={value!r} → "
                f"{spec_cls.__name__}.{value} is annotated as "
                f"{annotation!r}, which is not ArtifactField-typed. "
                f"Routing keys must point at ArtifactField "
                f"sub-components; primitives belong on top-level "
                f"with location.field=None."
            )

    @staticmethod
    def _iter_constants(fields_cls):
        for attr_name, value in vars(fields_cls).items():
            if attr_name.startswith("_"):
                continue
            if not isinstance(value, str):
                continue
            yield attr_name, value


# ---------------------------------------------------------------------------
# Contract 2: strict raises on bogus location.field values
# ---------------------------------------------------------------------------


def _bogus_capture_class(field_value: str | None) -> type:
    """Build a throwaway class whose ``_init_subclass_errors`` carries
    a single issue with the requested ``location.field``."""

    class _Holder:
        _init_subclass_errors = [
            ValidationIssue(
                severity="error", code="probe",
                message="probe",
                location=ValidationLocation(field=field_value),
            )
        ]

    return _Holder


class TestStrictAttachContract:
    """``attach_class_captures`` raises on broken routing keys
    rather than silently falling back to top-level ``spec.issues``."""

    def _empty_step_spec(self) -> StepSpec:
        return StepSpec(
            kind=KIND_STEP, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )

    def test_unknown_field_name_raises(self):
        """Field not in spec.model_fields → RuntimeError naming the
        offending issue code and the bad field."""
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class("inptus")  # typo of "inputs"
        with pytest.raises(RuntimeError) as exc_info:
            spec.attach_class_captures(bad_cls)
        msg = str(exc_info.value)
        assert "probe" in msg                  # issue code surfaces
        assert "inptus" in msg                  # bad field surfaces
        assert "no such field" in msg           # actionable hint

    def test_primitive_field_target_raises(self):
        """Field exists on spec but isn't ArtifactField-typed →
        RuntimeError. ``StepSpec.tool_names`` is ``list[str]``."""
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class("tool_names")
        with pytest.raises(RuntimeError) as exc_info:
            spec.attach_class_captures(bad_cls)
        msg = str(exc_info.value)
        assert "tool_names" in msg
        assert "not an ArtifactField" in msg

    def test_field_none_routes_to_top_level(self):
        """``location.field=None`` is the legitimate "top-level
        issue" sentinel — must NOT raise; lands on spec.issues."""
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(None)
        spec.attach_class_captures(bad_cls)
        codes = [i.code for i in spec.issues]
        assert codes == ["probe"]

    def test_artifact_field_typed_runtime_none_routes_top_level(self):
        """Field is typed for routing (``ArtifactField | None``) but
        the runtime value is None — graceful fallback to top-level.
        This is the common "missing INPUTS" case: capture says
        field='inputs', spec.inputs=None because the source class
        didn't set INPUTS, so there's no sub-component to attach
        to. Don't raise; land on spec.issues."""
        # spec.inputs is None by default — typed as JsonSchemaWithRefs | None.
        spec = self._empty_step_spec()
        assert spec.inputs is None
        bad_cls = _bogus_capture_class("inputs")
        spec.attach_class_captures(bad_cls)
        codes = [i.code for i in spec.issues]
        assert codes == ["probe"]


# ---------------------------------------------------------------------------
# Spot-check across the rest of the kinds (smoke — not exhaustive)
# ---------------------------------------------------------------------------


class TestStrictAttachAcrossKinds:
    """Confirm the strict contract is inherited cleanly by every
    per-kind ArtifactSpec subclass — not just StepSpec."""

    def test_extraction_spec_raises_on_unknown_field(self):
        spec = ExtractionSpec(
            kind=KIND_EXTRACTION, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )
        bad_cls = _bogus_capture_class("nope")
        with pytest.raises(RuntimeError, match="no such field"):
            spec.attach_class_captures(bad_cls)

    def test_review_spec_raises_on_primitive_target(self):
        spec = ReviewSpec(
            kind=KIND_REVIEW, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )
        # ReviewSpec.webhook_url is str | None — primitive.
        bad_cls = _bogus_capture_class("webhook_url")
        with pytest.raises(RuntimeError, match="not an ArtifactField"):
            spec.attach_class_captures(bad_cls)

    def test_prompt_data_routes_variables_field(self):
        prompt = PromptData(
            variables=PromptVariableDefs(json_schema={"type": "object"}),
            yaml_path="/tmp/x.yaml",
        )
        bad_cls = _bogus_capture_class(PromptDataFields.VARIABLES)
        prompt.attach_class_captures(bad_cls)
        # Should land on prompt.variables.issues (the routable target).
        assert [i.code for i in prompt.variables.issues] == ["probe"]
        assert prompt.issues == []
