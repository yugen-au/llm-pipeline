"""Tests for ``flatten_artifact_issues``.

Verifies the helper walks the typed sub-component fields
(:class:`CodeBodySpec`, :class:`JsonSchemaWithRefs`,
:class:`PromptData`) and accumulates issues from each into a
single flat list — used by the API list endpoint and any
"is this artifact broken at all?" query.
"""
from __future__ import annotations

from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation
from llm_pipeline.specs import (
    CodeBodySpec,
    ConstantSpec,
    JsonSchemaWithRefs,
    KIND_CONSTANT,
    KIND_STEP,
    PromptData,
    StepSpec,
    flatten_artifact_issues,
)


def _issue(code: str, severity: str = "error") -> ValidationIssue:
    return ValidationIssue(
        severity=severity, code=code, message=code,
        location=ValidationLocation(),
    )


class TestTopLevelIssuesOnly:
    def test_constant_with_top_level_issue(self):
        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="x", cls="m.X",
            source_path="/x.py", value_type="int", value=1,
            issues=[_issue("top_level")],
        )
        flat = flatten_artifact_issues(spec)
        assert [i.code for i in flat] == ["top_level"]

    def test_no_issues_returns_empty_list(self):
        spec = ConstantSpec(
            kind=KIND_CONSTANT, name="x", cls="m.X",
            source_path="/x.py", value_type="int", value=1,
        )
        assert flatten_artifact_issues(spec) == []


class TestNestedSubComponents:
    def test_step_with_issues_at_every_level(self):
        spec = StepSpec(
            kind=KIND_STEP, name="foo", cls="m.FooStep",
            source_path="/x.py",
            issues=[_issue("step_top")],
            inputs=JsonSchemaWithRefs(
                json_schema={"type": "object"},
                issues=[_issue("inputs_issue")],
            ),
            instructions=JsonSchemaWithRefs(
                json_schema={"type": "object"},
                issues=[_issue("instructions_issue")],
            ),
            prepare=CodeBodySpec(
                source="return []",
                issues=[_issue("prepare_issue")],
            ),
            run=CodeBodySpec(
                source="return None",
                issues=[_issue("run_issue")],
            ),
            prompt=PromptData(
                variables=JsonSchemaWithRefs(
                    json_schema={"type": "object"},
                    issues=[_issue("prompt_variables_issue")],
                ),
                yaml_path="prompts/foo.yaml",
                issues=[_issue("prompt_top")],
            ),
        )
        codes = sorted(i.code for i in flatten_artifact_issues(spec))
        # All seven captured: step top + inputs + instructions +
        # prepare + run + prompt top + prompt's nested variables.
        assert codes == sorted([
            "step_top",
            "inputs_issue",
            "instructions_issue",
            "prepare_issue",
            "run_issue",
            "prompt_top",
            "prompt_variables_issue",
        ])

    def test_top_level_issues_come_first(self):
        spec = StepSpec(
            kind=KIND_STEP, name="foo", cls="m.FooStep",
            source_path="/x.py",
            issues=[_issue("first"), _issue("second")],
            prepare=CodeBodySpec(
                source="...", issues=[_issue("prepare_issue")],
            ),
        )
        codes = [i.code for i in flatten_artifact_issues(spec)]
        # Top-level (in order) before sub-component.
        assert codes[:2] == ["first", "second"]
        assert "prepare_issue" in codes[2:]

    def test_step_with_no_sub_components_just_top_level(self):
        spec = StepSpec(
            kind=KIND_STEP, name="foo", cls="m.FooStep",
            source_path="/x.py",
            issues=[_issue("only_one")],
        )
        flat = flatten_artifact_issues(spec)
        assert [i.code for i in flat] == ["only_one"]


class TestSeverityIsPreserved:
    def test_warnings_and_errors_both_returned(self):
        spec = StepSpec(
            kind=KIND_STEP, name="foo", cls="m.FooStep",
            source_path="/x.py",
            issues=[_issue("e1", "error")],
            inputs=JsonSchemaWithRefs(
                json_schema={"type": "object"},
                issues=[_issue("w1", "warning")],
            ),
        )
        flat = flatten_artifact_issues(spec)
        sevs = sorted((i.code, i.severity) for i in flat)
        assert sevs == [("e1", "error"), ("w1", "warning")]
