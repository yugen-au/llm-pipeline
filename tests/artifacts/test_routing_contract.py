"""Lock down the routing contract between Fields classes and specs.

Two contracts under test:

1. **FieldsBase class-load validation**: every :class:`FieldRef`
   constant on a per-kind ``*Fields`` class must address an
   ArtifactField slot reachable from ``SPEC_CLS``. Malformed
   declarations raise :class:`TypeError` at class-load time —
   structural mistakes get caught on import, not at routing time.

2. **Strict ``attach_class_captures`` enforcement**: paths that
   reference a non-existent attribute, a non-ArtifactField target,
   or use bracket access incompatibly with the slot's container
   shape raise :class:`RuntimeError` immediately. The walker is
   permissive only on **runtime gaps** — slot value ``None``, key
   missing in a runtime list/dict — which are real "spec wasn't
   populated" cases, not bugs.

Together these prevent the silent-drift class of bug the typed-
fields-class design was built to catch.
"""
from __future__ import annotations

import pytest

from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation
from llm_pipeline.artifacts import (
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
from llm_pipeline.artifacts.base.fields import FieldRef, FieldsBase


# ---------------------------------------------------------------------------
# Contract 1: FieldsBase validates FieldRef constants at class-load time
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
class TestFieldsClassesLoaded:
    """Every shipped Fields class loaded successfully — i.e. every
    one of its ``FieldRef`` constants validates against ``SPEC_CLS``
    at import time. If any drifted, this module would have failed to
    import (FieldsBase raises in ``__init_subclass__``)."""

    def test_spec_cls_pinned(self, fields_cls, spec_cls):
        assert fields_cls.SPEC_CLS is spec_cls

    def test_constants_are_field_refs(self, fields_cls, spec_cls):
        constants = list(self._iter_constants(fields_cls))
        assert constants, (
            f"{fields_cls.__name__} declares no FieldRef constants — "
            f"either it has no capture sites or the constants are "
            f"declared as bare strings (legacy form). Migrate to "
            f"FieldRef('...')."
        )

    @staticmethod
    def _iter_constants(fields_cls):
        for attr_name, value in vars(fields_cls).items():
            if attr_name.startswith("_"):
                continue
            if isinstance(value, FieldRef):
                yield attr_name, value


class TestFieldsBaseRejectsBadConstants:
    """Malformed FieldRef constants raise at class-load time."""

    def test_unknown_attribute_raises(self):
        with pytest.raises(TypeError, match="has no field"):
            class _BadStepFields(FieldsBase):  # noqa: F841
                SPEC_CLS = StepSpec
                INPTUS = FieldRef("inptus")  # typo

    def test_non_artifact_field_target_raises(self):
        # ``StepSpec.tools`` is ``list[ArtifactRef]`` — needs bracket
        # access; plain attr access on a list is rejected.
        with pytest.raises(TypeError, match="is a list"):
            class _BadStepFields(FieldsBase):  # noqa: F841
                SPEC_CLS = StepSpec
                TOOLS = FieldRef("tools")  # missing bracket

    def test_bracket_on_non_container_raises(self):
        with pytest.raises(TypeError, match="single ArtifactField"):
            class _BadStepFields(FieldsBase):  # noqa: F841
                SPEC_CLS = StepSpec
                INPUTS = FieldRef("inputs")["foo"]  # inputs isn't a list

    def test_intermediate_class_without_spec_cls_skipped(self):
        # A FieldsBase subclass that doesn't pin SPEC_CLS is treated
        # as an intermediate base — no validation runs (so no error
        # even though the FieldRef wouldn't be valid anywhere).
        class _Intermediate(FieldsBase):
            BOGUS = FieldRef("does.not.exist")  # never validated

        assert _Intermediate.BOGUS == FieldRef("does.not.exist")


# ---------------------------------------------------------------------------
# Contract 2: strict raises on bogus paths at routing time
# ---------------------------------------------------------------------------


def _bogus_capture_class(*, path: str | None = None, field: str | None = None) -> type:
    """Build a throwaway class whose ``_init_subclass_errors`` carries
    a single issue with the requested ``location.path`` / ``location.field``."""

    class _Holder:
        _init_subclass_errors = [
            ValidationIssue(
                severity="error", code="probe",
                message="probe",
                location=ValidationLocation(path=path, field=field),
            )
        ]

    return _Holder


class TestStrictAttachContract:
    """``attach_class_captures`` raises on broken routing paths
    rather than silently falling back to ``self.issues`` (which
    would lose the issue from any structurally-routed UI surface).
    """

    def _empty_step_spec(self) -> StepSpec:
        return StepSpec(
            kind=KIND_STEP, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )

    def test_unknown_attr_raises(self):
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(path="inptus")  # typo
        with pytest.raises(RuntimeError) as exc_info:
            spec.attach_class_captures(bad_cls)
        msg = str(exc_info.value)
        assert "probe" in msg          # issue code surfaces
        assert "inptus" in msg          # bad path surfaces
        assert "no field" in msg        # actionable hint

    def test_primitive_attr_raises(self):
        # ``StepSpec.cls`` (inherited) is str — primitive, not
        # ArtifactField-typed. Routing to it should raise.
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(path="cls")
        with pytest.raises(RuntimeError, match="not ArtifactField-typed"):
            spec.attach_class_captures(bad_cls)

    def test_list_without_bracket_raises(self):
        # ``StepSpec.tools`` is list[ArtifactRef] — bracket required.
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(path="tools")
        with pytest.raises(RuntimeError, match="must use bracketed"):
            spec.attach_class_captures(bad_cls)

    def test_bracket_on_plain_field_raises(self):
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(path="inputs[x]")
        with pytest.raises(RuntimeError, match="single ArtifactField"):
            spec.attach_class_captures(bad_cls)

    def test_path_none_routes_to_top_level(self):
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(path=None)
        spec.attach_class_captures(bad_cls)
        assert [i.code for i in spec.issues] == ["probe"]

    def test_legacy_field_kwarg_still_works(self):
        # Capture sites that haven't migrated to ``path=`` still set
        # ``field=`` for top-level routing. The walker treats it as
        # a single-segment path.
        spec = self._empty_step_spec()
        bad_cls = _bogus_capture_class(field="inputs")
        # ``inputs`` is None at runtime → permissive: lands on parent.
        spec.attach_class_captures(bad_cls)
        assert [i.code for i in spec.issues] == ["probe"]


class TestPermissiveOnRuntimeGaps:
    """The walker is permissive only on real "spec wasn't populated"
    runtime cases — the structural shape is correct, the runtime
    container just doesn't have the addressed element."""

    def test_artifact_field_typed_runtime_none_routes_top_level(self):
        # ``StepSpec.inputs`` is JsonSchemaWithRefs | None — the slot
        # is typed for routing but ``None`` because no INPUTS class
        # was declared. Issue lands on parent.
        spec = StepSpec(
            kind=KIND_STEP, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )
        assert spec.inputs is None
        bad_cls = _bogus_capture_class(path="inputs")
        spec.attach_class_captures(bad_cls)
        assert [i.code for i in spec.issues] == ["probe"]

    def test_missing_list_key_routes_to_parent(self):
        # ``tools[unknown]`` — structurally fine (bracket required,
        # tools is list[ArtifactRef]), but no element with that key.
        spec = StepSpec(
            kind=KIND_STEP, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )
        bad_cls = _bogus_capture_class(path="tools[unknown]")
        spec.attach_class_captures(bad_cls)
        assert [i.code for i in spec.issues] == ["probe"]


# ---------------------------------------------------------------------------
# Spot-check across the rest of the kinds (smoke — not exhaustive)
# ---------------------------------------------------------------------------


class TestStrictAttachAcrossKinds:
    """Confirm the strict contract is inherited cleanly by every
    per-kind ArtifactSpec subclass — not just StepSpec."""

    def test_extraction_spec_raises_on_unknown_attr(self):
        spec = ExtractionSpec(
            kind=KIND_EXTRACTION, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )
        bad_cls = _bogus_capture_class(path="nope")
        with pytest.raises(RuntimeError, match="no field"):
            spec.attach_class_captures(bad_cls)

    def test_review_spec_raises_on_primitive_target(self):
        spec = ReviewSpec(
            kind=KIND_REVIEW, name="probe", cls="m.Probe",
            source_path="/probe.py",
        )
        # ReviewSpec.webhook_url is str | None — primitive.
        bad_cls = _bogus_capture_class(path="webhook_url")
        with pytest.raises(RuntimeError, match="not ArtifactField-typed"):
            spec.attach_class_captures(bad_cls)

    def test_prompt_data_routes_variables_path(self):
        prompt = PromptData(
            variables=PromptVariableDefs(json_schema={"type": "object"}),
            yaml_path="/tmp/x.yaml",
        )
        bad_cls = _bogus_capture_class(path=str(PromptDataFields.VARIABLES))
        prompt.attach_class_captures(bad_cls)
        # Should land on prompt.variables.issues (the routable target).
        assert [i.code for i in prompt.variables.issues] == ["probe"]
        assert prompt.issues == []

    def test_subfield_passes_through_unchanged(self):
        # ``subfield`` is UI-only metadata — the router ignores it.
        # The issue still routes by ``path``; ``subfield`` rides along.
        prompt = PromptData(
            variables=PromptVariableDefs(json_schema={"type": "object"}),
            yaml_path="/tmp/x.yaml",
        )

        class _Holder:
            _init_subclass_errors = [
                ValidationIssue(
                    severity="error", code="missing_field_description",
                    message="probe",
                    location=ValidationLocation(
                        path=str(PromptDataFields.VARIABLES),
                        subfield="sentiment",
                    ),
                )
            ]

        prompt.attach_class_captures(_Holder)
        landed = prompt.variables.issues
        assert len(landed) == 1
        assert landed[0].location.subfield == "sentiment"
