"""
Unit tests for llm_pipeline/creator/sandbox.py.

No real Docker daemon required -- all container interaction is mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from llm_pipeline.creator.sandbox import (
    CodeSecurityValidator,
    SandboxResult,
    StepSandbox,
)


# ---------------------------------------------------------------------------
# TestCodeSecurityValidator
# ---------------------------------------------------------------------------


class TestCodeSecurityValidator:
    """Tests for CodeSecurityValidator.validate()."""

    def setup_method(self):
        self.validator = CodeSecurityValidator()

    def test_clean_code_no_issues(self):
        issues = self.validator.validate("x = 1")
        assert issues == []

    def test_blocked_module_os(self):
        issues = self.validator.validate("import os")
        assert len(issues) == 1
        assert "os" in issues[0]

    def test_blocked_module_subprocess(self):
        issues = self.validator.validate("import subprocess")
        assert len(issues) == 1
        assert "subprocess" in issues[0]

    def test_blocked_importfrom(self):
        issues = self.validator.validate("from os import path")
        assert len(issues) == 1
        assert "os" in issues[0]

    def test_blocked_builtin_eval(self):
        issues = self.validator.validate("eval('x')")
        assert len(issues) == 1
        assert "eval" in issues[0]

    def test_blocked_builtin_exec(self):
        issues = self.validator.validate("exec('x = 1')")
        assert len(issues) == 1
        assert "exec" in issues[0]

    def test_blocked_attribute_os_system(self):
        issues = self.validator.validate("os.system('ls')")
        assert len(issues) == 1
        assert "system" in issues[0]

    def test_empty_code_no_issues(self):
        issues = self.validator.validate("")
        assert issues == []

    def test_normal_llm_pipeline_import_allowed(self):
        issues = self.validator.validate("from llm_pipeline.step import LLMStep")
        assert issues == []

    def test_pydantic_import_allowed(self):
        issues = self.validator.validate("from pydantic import BaseModel")
        assert issues == []

    def test_multiple_issues_returned(self):
        code = "import os\nexec('x')"
        issues = self.validator.validate(code)
        assert len(issues) == 2


# ---------------------------------------------------------------------------
# TestSandboxResult
# ---------------------------------------------------------------------------


class TestSandboxResult:
    """Tests for SandboxResult pydantic model defaults and validation."""

    def test_default_values(self):
        result = SandboxResult()
        assert result.import_ok is False
        assert result.sandbox_skipped is True
        assert result.security_issues == []
        assert result.output == ""
        assert result.errors == []
        assert result.modules_found == []

    def test_pydantic_validation(self):
        result = SandboxResult(
            import_ok=True,
            security_issues=["issue1"],
            sandbox_skipped=False,
            output="some output",
            errors=["err"],
            modules_found=["my_module"],
        )
        assert result.import_ok is True
        assert result.security_issues == ["issue1"]
        assert result.sandbox_skipped is False
        assert result.output == "some output"
        assert result.errors == ["err"]
        assert result.modules_found == ["my_module"]


# ---------------------------------------------------------------------------
# TestStepSandbox_DockerUnavailable
# ---------------------------------------------------------------------------


class TestStepSandbox_DockerUnavailable:
    """Tests for StepSandbox when Docker is unavailable (_get_client returns None)."""

    def setup_method(self):
        self.sandbox = StepSandbox()

    def test_run_skips_container_when_no_docker(self):
        artifacts = {"step.py": "x = 1"}
        with patch.object(self.sandbox, "_get_client", return_value=None):
            result = self.sandbox.run(artifacts)
        assert result.sandbox_skipped is True

    def test_run_still_does_ast_scan_when_no_docker(self):
        artifacts = {"step.py": "import os"}
        with patch.object(self.sandbox, "_get_client", return_value=None):
            result = self.sandbox.run(artifacts)
        # AST scan must flag the blocked import even without Docker
        assert len(result.security_issues) > 0
        assert any("os" in issue for issue in result.security_issues)

    def test_validate_code_delegates_to_security_validator(self):
        issues = self.sandbox.validate_code("import os")
        assert len(issues) > 0
        assert any("os" in issue for issue in issues)


# ---------------------------------------------------------------------------
# TestStepSandbox_WithMockDocker
# ---------------------------------------------------------------------------


def _make_mock_container(
    logs_bytes: bytes = b"",
    stdout_bytes: bytes = b"",
    wait_side_effect=None,
):
    """Build a mock container with configurable behaviour."""
    container = MagicMock()

    if wait_side_effect is not None:
        container.wait.side_effect = wait_side_effect
    else:
        container.wait.return_value = {"StatusCode": 0}

    container.logs.side_effect = lambda stdout=True, stderr=True: (
        stdout_bytes if not stderr else logs_bytes
    )
    container.kill.return_value = None
    container.remove.return_value = None
    container.start.return_value = None
    return container


def _make_mock_client(container: MagicMock):
    """Build a mock docker client that returns the given container on create."""
    client = MagicMock()
    client.containers.create.return_value = container
    return client


class TestStepSandbox_WithMockDocker:
    """Tests for StepSandbox container execution path using mock docker client."""

    def setup_method(self):
        self.sandbox = StepSandbox()

    # -- helper: patch _get_client + docker imports inside run() ---------------

    def _run_with_mock_client(
        self,
        artifacts: dict,
        container: MagicMock,
        sample_data=None,
    ) -> SandboxResult:
        """Run sandbox with a fully-mocked docker client."""
        client = _make_mock_client(container)

        mock_mount = MagicMock()
        mock_docker = MagicMock()
        mock_docker.types.Mount = mock_mount
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            # patch the import inside run() for docker.types.Mount
            import sys
            # We also need requests.exceptions.ReadTimeout available
            import requests.exceptions
            return self.sandbox.run(artifacts, sample_data=sample_data)

    def test_run_creates_container_with_correct_params(self):
        payload = {"import_ok": True, "errors": [], "modules_found": ["step"]}
        stdout_bytes = json.dumps(payload).encode()
        logs_bytes = stdout_bytes
        container = _make_mock_container(logs_bytes=logs_bytes, stdout_bytes=stdout_bytes)
        client = _make_mock_client(container)

        mock_mount_cls = MagicMock()
        mock_docker = MagicMock()
        mock_docker.types.Mount = mock_mount_cls
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            self.sandbox.run({"step.py": "x = 1"})

        call_kwargs = client.containers.create.call_args
        assert call_kwargs is not None
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        assert kwargs.get("network_mode") == "none"
        assert kwargs.get("read_only") is True
        assert kwargs.get("mem_limit") == "512m"

    def test_run_parses_json_output(self):
        payload = {"import_ok": True, "errors": [], "modules_found": ["step"]}
        stdout_bytes = json.dumps(payload).encode()
        # logs() returns the same bytes for both combined and stdout-only calls
        container = MagicMock()
        container.wait.return_value = {"StatusCode": 0}
        container.logs.return_value = stdout_bytes
        container.start.return_value = None
        container.remove.return_value = None

        client = _make_mock_client(container)
        mock_docker = MagicMock()
        mock_docker.types.Mount = MagicMock()
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            result = self.sandbox.run({"step.py": "x = 1"})

        assert result.import_ok is True
        assert result.sandbox_skipped is False

    def test_run_handles_timeout(self):
        from requests.exceptions import ReadTimeout

        container = MagicMock()
        container.wait.side_effect = ReadTimeout("timed out")
        container.logs.return_value = b"some partial output"
        container.kill.return_value = None
        container.remove.return_value = None
        container.start.return_value = None

        client = _make_mock_client(container)
        mock_docker = MagicMock()
        mock_docker.types.Mount = MagicMock()
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            result = self.sandbox.run({"step.py": "x = 1"})

        assert result.import_ok is False
        assert result.sandbox_skipped is False
        assert any("timed out" in e.lower() or "timeout" in e.lower() for e in result.errors)

    def test_run_kills_container_on_timeout(self):
        from requests.exceptions import ReadTimeout

        container = MagicMock()
        container.wait.side_effect = ReadTimeout("timed out")
        container.logs.return_value = b""
        container.kill.return_value = None
        container.remove.return_value = None
        container.start.return_value = None

        client = _make_mock_client(container)
        mock_docker = MagicMock()
        mock_docker.types.Mount = MagicMock()
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            self.sandbox.run({"step.py": "x = 1"})

        container.kill.assert_called_once()

    def test_run_removes_container_on_success(self):
        payload = {"import_ok": True, "errors": [], "modules_found": ["step"]}
        stdout_bytes = json.dumps(payload).encode()
        container = MagicMock()
        container.wait.return_value = {"StatusCode": 0}
        container.logs.return_value = stdout_bytes
        container.start.return_value = None
        container.remove.return_value = None

        client = _make_mock_client(container)
        mock_docker = MagicMock()
        mock_docker.types.Mount = MagicMock()
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            self.sandbox.run({"step.py": "x = 1"})

        container.remove.assert_called_once_with(force=True)

    def test_run_handles_docker_exception(self):
        client = MagicMock()
        client.containers.create.side_effect = Exception("docker daemon error")

        mock_docker = MagicMock()
        mock_docker.types.Mount = MagicMock()
        mock_docker.errors.DockerException = Exception

        with (
            patch.object(self.sandbox, "_get_client", return_value=client),
            patch.object(self.sandbox, "_discover_framework_path", return_value=None),
            patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker.types}),
        ):
            result = self.sandbox.run({"step.py": "x = 1"})

        assert result.import_ok is False
        assert result.sandbox_skipped is False
        assert len(result.errors) > 0
        assert any("docker daemon error" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCodeValidationStepSandboxIntegration
# ---------------------------------------------------------------------------


def _make_pipeline_mock(context: dict) -> MagicMock:
    """Build a minimal pipeline mock that CodeValidationStep.process_instructions needs."""
    pipeline = MagicMock()
    pipeline.context = context
    pipeline.validated_input = MagicMock()
    pipeline.validated_input.include_extraction = False
    return pipeline


def _make_code_validation_step(pipeline: MagicMock) -> "CodeValidationStep":
    """Instantiate CodeValidationStep bypassing the normal LLMStep constructor."""
    from llm_pipeline.creator.steps import CodeValidationStep
    from llm_pipeline.creator.schemas import CodeValidationInstructions

    step = CodeValidationStep.__new__(CodeValidationStep)
    step.system_instruction_key = "code_validation"
    step.user_prompt_key = "code_validation"
    step.instructions = CodeValidationInstructions
    step.pipeline = pipeline
    return step


def _make_instructions(
    is_valid: bool = True,
    issues: list[str] | None = None,
) -> "CodeValidationInstructions":
    from llm_pipeline.creator.schemas import CodeValidationInstructions

    return CodeValidationInstructions(
        is_valid=is_valid,
        issues=issues or [],
        suggestions=[],
        naming_valid=True,
        imports_valid=True,
        type_annotations_valid=True,
    )


_MINIMAL_CONTEXT = {
    "step_name": "my_step",
    "step_code": "x = 1",
    "instructions_code": "y = 2",
    "extraction_code": None,
    "prompt_yaml": "prompts: {}",
    "system_prompt": "You are helpful.",
    "user_prompt_template": "Do {task}.",
    "instruction_fields": [],
}


class TestCodeValidationStepSandboxIntegration:
    """Integration tests: CodeValidationStep.process_instructions() sandbox wiring."""

    # -- sandbox-available path ------------------------------------------------

    def test_sandbox_available_sets_sandbox_valid_from_result(self):
        """When sandbox runs and import_ok=True, sandbox_valid=True in context."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        sandbox_result = SandboxResult(
            import_ok=True,
            sandbox_skipped=False,
            output="all good",
            errors=[],
            modules_found=["my_step_step"],
        )

        with (
            patch.object(steps_module, "_SANDBOX_AVAILABLE", True),
            patch("llm_pipeline.creator.steps.StepSandbox") as MockSandbox,
            patch("llm_pipeline.creator.steps.SampleDataGenerator") as MockSampleData,
        ):
            MockSandbox.return_value.run.return_value = sandbox_result
            MockSampleData.return_value.generate.return_value = None

            result = step.process_instructions([inst])

        assert result.sandbox_valid is True
        assert result.sandbox_skipped is False
        assert result.sandbox_output == "all good"

    def test_sandbox_available_sets_sandbox_skipped_when_docker_unavailable(self):
        """When sandbox returns sandbox_skipped=True, context reflects that."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        sandbox_result = SandboxResult(
            import_ok=True,
            sandbox_skipped=True,
            output="Docker unavailable; AST scan passed",
            errors=[],
            modules_found=[],
        )

        with (
            patch.object(steps_module, "_SANDBOX_AVAILABLE", True),
            patch("llm_pipeline.creator.steps.StepSandbox") as MockSandbox,
            patch("llm_pipeline.creator.steps.SampleDataGenerator") as MockSampleData,
        ):
            MockSandbox.return_value.run.return_value = sandbox_result
            MockSampleData.return_value.generate.return_value = None

            result = step.process_instructions([inst])

        assert result.sandbox_skipped is True
        assert result.sandbox_output == "Docker unavailable; AST scan passed"

    def test_sandbox_available_security_issues_added_to_context_issues(self):
        """security_issues from SandboxResult are appended into context issues."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True, issues=["llm issue"])

        sandbox_result = SandboxResult(
            import_ok=False,
            sandbox_skipped=True,
            security_issues=["Blocked module import: os (line 1)"],
            output="",
            errors=[],
            modules_found=[],
        )

        with (
            patch.object(steps_module, "_SANDBOX_AVAILABLE", True),
            patch("llm_pipeline.creator.steps.StepSandbox") as MockSandbox,
            patch("llm_pipeline.creator.steps.SampleDataGenerator") as MockSampleData,
        ):
            MockSandbox.return_value.run.return_value = sandbox_result
            MockSampleData.return_value.generate.return_value = None

            result = step.process_instructions([inst])

        assert "llm issue" in result.issues
        assert any("os" in issue for issue in result.issues)

    def test_sandbox_available_passes_artifacts_to_run(self):
        """StepSandbox.run() receives the correct artifact map."""
        import llm_pipeline.creator.steps as steps_module

        ctx = _MINIMAL_CONTEXT.copy()
        ctx["step_name"] = "calc_step"
        ctx["step_code"] = "result = 42"
        ctx["instructions_code"] = "answer = 42"

        pipeline = _make_pipeline_mock(ctx)
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        sandbox_result = SandboxResult(import_ok=True, sandbox_skipped=False)

        with (
            patch.object(steps_module, "_SANDBOX_AVAILABLE", True),
            patch("llm_pipeline.creator.steps.StepSandbox") as MockSandbox,
            patch("llm_pipeline.creator.steps.SampleDataGenerator") as MockSampleData,
        ):
            MockSandbox.return_value.run.return_value = sandbox_result
            MockSampleData.return_value.generate.return_value = None

            step.process_instructions([inst])

        call_kwargs = MockSandbox.return_value.run.call_args
        artifacts_arg = call_kwargs.kwargs.get("artifacts") or call_kwargs[1].get("artifacts") or call_kwargs[0][0]
        assert "calc_step_step.py" in artifacts_arg
        assert "calc_step_instructions.py" in artifacts_arg

    def test_sandbox_available_calls_sample_data_generator_with_fields(self):
        """SampleDataGenerator.generate() is called when instruction_fields present."""
        import llm_pipeline.creator.steps as steps_module

        ctx = _MINIMAL_CONTEXT.copy()
        ctx["instruction_fields"] = [
            {"name": "sentiment", "type_annotation": "str", "description": "x", "default": None, "is_required": True}
        ]

        pipeline = _make_pipeline_mock(ctx)
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        sandbox_result = SandboxResult(import_ok=True, sandbox_skipped=False)

        with (
            patch.object(steps_module, "_SANDBOX_AVAILABLE", True),
            patch("llm_pipeline.creator.steps.StepSandbox") as MockSandbox,
            patch("llm_pipeline.creator.steps.SampleDataGenerator") as MockSampleData,
        ):
            MockSandbox.return_value.run.return_value = sandbox_result
            MockSampleData.return_value.generate.return_value = {"sentiment": "positive"}

            step.process_instructions([inst])

        MockSampleData.return_value.generate.assert_called_once()

    def test_sandbox_available_is_valid_false_when_import_fails(self):
        """is_valid=False when sandbox import_ok=False and sandbox not skipped."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        sandbox_result = SandboxResult(
            import_ok=False,
            sandbox_skipped=False,
            output="ImportError: no module named x",
            errors=["ImportError"],
            modules_found=[],
        )

        with (
            patch.object(steps_module, "_SANDBOX_AVAILABLE", True),
            patch("llm_pipeline.creator.steps.StepSandbox") as MockSandbox,
            patch("llm_pipeline.creator.steps.SampleDataGenerator") as MockSampleData,
        ):
            MockSandbox.return_value.run.return_value = sandbox_result
            MockSampleData.return_value.generate.return_value = None

            result = step.process_instructions([inst])

        assert result.is_valid is False
        assert result.sandbox_valid is False

    # -- sandbox-unavailable path ----------------------------------------------

    def test_sandbox_unavailable_sets_sandbox_output_message(self):
        """When _SANDBOX_AVAILABLE=False, sandbox_output='sandbox module not available'."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        with patch.object(steps_module, "_SANDBOX_AVAILABLE", False):
            result = step.process_instructions([inst])

        assert result.sandbox_output == "sandbox module not available"

    def test_sandbox_unavailable_sandbox_skipped_true(self):
        """When _SANDBOX_AVAILABLE=False, sandbox_skipped remains True."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        with patch.object(steps_module, "_SANDBOX_AVAILABLE", False):
            result = step.process_instructions([inst])

        assert result.sandbox_skipped is True

    def test_sandbox_unavailable_is_valid_passes_when_syntax_and_llm_ok(self):
        """is_valid=True when sandbox skipped and syntax+llm review both pass."""
        import llm_pipeline.creator.steps as steps_module

        pipeline = _make_pipeline_mock(_MINIMAL_CONTEXT.copy())
        step = _make_code_validation_step(pipeline)
        inst = _make_instructions(is_valid=True)

        with patch.object(steps_module, "_SANDBOX_AVAILABLE", False):
            result = step.process_instructions([inst])

        assert result.is_valid is True
