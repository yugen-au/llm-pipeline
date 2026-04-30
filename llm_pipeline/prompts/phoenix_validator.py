"""Phoenix-aware build-time validator.

Runs at ``uv run llm-pipeline build`` (write mode) and on ``ui`` boot
(dry-run mode). Validates the alignment between code (LLMStepNode
subclasses + PromptVariables registry), the YAML on disk
(``llm-pipeline-prompts/{step_name}.yaml``), and Phoenix.

There is **no opt-out**. The opt-out for tests / CI / dev iteration is
simply not running the validator (don't call ``build``; the framework
itself never invokes this module at import time). Production /
pre-deploy is the only context that runs ``build``; if anything is
misaligned the deploy fails.

Strictness mirrors the node / pipeline validators we ship at
``__init_subclass__`` time:

- Code-side structural checks fire first (registry presence, YAML
  presence, message-shape, placeholder bijection, model recognised
  by pydantic-ai).
- Phoenix-side checks fire after (Phoenix prompt presence).
- Errors are accumulated across every step in every registered
  pipeline, then a single ``PhoenixValidationFailed`` is raised at the
  end. Devs see the whole picture, not the first failure.

Modes
-----

``build`` — production push: throws ``PhoenixValidationFailed`` on any
error. Used by the new ``llm-pipeline build`` subcommand. Phoenix
unreachable is fatal.

``dry-run`` — used by ``llm-pipeline ui`` boot: runs the same checks,
but never raises. Errors are surfaced via ``logger.warning``. UI
keeps booting either way. Phoenix unreachable is logged and skipped.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from llm_pipeline.prompts.models import (
    ModelStringError,
    Prompt,
)
from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PhoenixPromptClient,
    PromptNotFoundError,
)
from llm_pipeline.prompts.registration import iter_step_classes
from llm_pipeline.prompts.utils import extract_variables_from_content
from llm_pipeline.prompts.variables import get_prompt_variables

if TYPE_CHECKING:
    from llm_pipeline.graph.pipeline import Pipeline


__all__ = [
    # Public entry point
    "validate_phoenix_alignment",
    # Result type
    "PhoenixValidationReport",
    "StepValidationResult",
    # Errors
    "PhoenixValidationError",
    "PhoenixValidationFailed",
    "PromptVariablesMissingError",
    "PromptVariablesRegistryMismatchError",
    "PromptYamlMissingError",
    "PromptYamlInvalidError",
    "PromptNameMismatchError",
    "PromptModelMissingError",
    "ModelNotRecognisedError",
    "PromptMessagesShapeError",
    "PromptVariableDriftError",
    "PhoenixPromptMissingError",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PhoenixValidationError(Exception):
    """Base for every per-step validation failure.

    Carries the offending pipeline + step name on every subclass so
    callers can build human-readable error reports without retyping
    that context everywhere.
    """

    def __init__(
        self,
        message: str,
        *,
        pipeline_name: str,
        step_name: str,
    ) -> None:
        super().__init__(message)
        self.pipeline_name = pipeline_name
        self.step_name = step_name


class PromptVariablesMissingError(PhoenixValidationError):
    """No PromptVariables subclass registered for this step's name.

    Add ``llm_pipelines/variables/{step_name}.py`` declaring an
    ``XxxPrompt(PromptVariables)`` subclass with nested system / user
    classes.
    """


class PromptVariablesRegistryMismatchError(PhoenixValidationError):
    """The registered PromptVariables class doesn't match the step's
    cached ``prompt_variables_cls``.

    Indicates a duplicate registration or an out-of-sync discovery
    pass — usually a test that monkey-patched the registry.
    """


class PromptYamlMissingError(PhoenixValidationError):
    """No YAML file at ``{prompts_dir}/{step_name}.yaml``."""


class PromptYamlInvalidError(PhoenixValidationError):
    """The YAML file fails Pydantic validation against ``Prompt``."""


class PromptNameMismatchError(PhoenixValidationError):
    """The YAML file's ``name`` field doesn't match the filename."""


class PromptModelMissingError(PhoenixValidationError):
    """The YAML file has no ``model:`` field set."""


class ModelNotRecognisedError(PhoenixValidationError):
    """``pydantic_ai.models.infer_model`` rejected the YAML's model string."""


class PromptMessagesShapeError(PhoenixValidationError):
    """YAML messages don't carry exactly one system + one user message."""


class PromptVariableDriftError(PhoenixValidationError):
    """Template placeholders don't match the prompt's declared variables.

    Phoenix's variable model is flat (one ``variable_definitions`` blob
    per prompt, message-agnostic) so this check operates at the
    prompt level: the union of placeholders across the system + user
    messages must equal the union of ``model_fields`` + ``auto_vars``
    on the ``XxxPrompt`` subclass.
    """


class PhoenixPromptMissingError(PhoenixValidationError):
    """Phoenix has no prompt with this step's name."""


@dataclass
class PhoenixValidationFailed(Exception):
    """Aggregate error raised at the end of ``build``-mode validation.

    Carries every per-step ``PhoenixValidationError`` so devs see the
    whole picture in one run. ``build`` exits non-zero on this; the
    CLI surface formats it for terminal output.
    """

    errors: list[PhoenixValidationError]

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        lines = [f"Phoenix validation failed ({len(self.errors)} error(s)):"]
        for err in self.errors:
            lines.append(
                f"  - [{err.pipeline_name}/{err.step_name}] "
                f"{type(err).__name__}: {err}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class StepValidationResult:
    """Per-step outcome surfaced to callers (CLI, UI startup, tests)."""

    pipeline_name: str
    step_name: str
    errors: list[PhoenixValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class PhoenixValidationReport:
    """Aggregate outcome across every step in every registered pipeline."""

    steps: list[StepValidationResult] = field(default_factory=list)

    @property
    def errors(self) -> list[PhoenixValidationError]:
        out: list[PhoenixValidationError] = []
        for step in self.steps:
            out.extend(step.errors)
        return out

    @property
    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


Mode = Literal["build", "dry-run"]


def validate_phoenix_alignment(
    introspection_registry: dict[str, type["Pipeline"]],
    prompts_dir: Path,
    *,
    prompt_client: PhoenixPromptClient | None,
    mode: Mode = "build",
) -> PhoenixValidationReport:
    """Validate every Step's code↔YAML↔Phoenix alignment.

    Args:
        introspection_registry: ``pipeline_name -> Pipeline subclass``
            map (the same registry the runtime uses).
        prompts_dir: Directory holding ``{step_name}.yaml`` files.
        prompt_client: Phoenix client. If ``None`` and ``mode`` is
            ``build``, Phoenix is unreachable and we raise. In
            ``dry-run``, Phoenix-side checks are skipped (a single
            warning is logged).
        mode: ``build`` (raise on any error at the end) or
            ``dry-run`` (log warnings only).

    Returns:
        ``PhoenixValidationReport`` carrying per-step results.

    Raises:
        ``PhoenixValidationFailed`` in ``build`` mode if any error
        was recorded.
    """
    if mode not in ("build", "dry-run"):
        raise ValueError(
            f"validate_phoenix_alignment: mode must be "
            f"'build' or 'dry-run', got {mode!r}"
        )

    if prompt_client is None and mode == "build":
        raise RuntimeError(
            "Phoenix prompt client is required in build mode. "
            "Set PHOENIX_BASE_URL and PHOENIX_API_KEY before "
            "running `uv run llm-pipeline build`."
        )

    report = PhoenixValidationReport()
    seen: set[type] = set()

    for pipeline_name, pipeline_cls in introspection_registry.items():
        for step_cls in iter_step_classes(pipeline_cls):
            if step_cls in seen:
                continue
            seen.add(step_cls)
            result = _validate_one_step(
                pipeline_name=pipeline_name,
                step_cls=step_cls,
                prompts_dir=prompts_dir,
                prompt_client=prompt_client,
                skip_phoenix_checks=(prompt_client is None),
            )
            report.steps.append(result)

    if not report.ok:
        if mode == "build":
            raise PhoenixValidationFailed(errors=report.errors)
        # dry-run: warn loudly but keep going.
        for err in report.errors:
            logger.warning(
                "[%s/%s] %s: %s",
                err.pipeline_name, err.step_name, type(err).__name__, err,
            )
        logger.warning(
            "Phoenix validation found %d issue(s). Run "
            "`uv run llm-pipeline build` to push and verify.",
            len(report.errors),
        )

    return report


# ---------------------------------------------------------------------------
# Per-step validation
# ---------------------------------------------------------------------------


def _validate_one_step(
    *,
    pipeline_name: str,
    step_cls: type,
    prompts_dir: Path,
    prompt_client: PhoenixPromptClient | None,
    skip_phoenix_checks: bool,
) -> StepValidationResult:
    """Run every check for a single step. Errors collect; never raise."""
    name = step_cls.step_name()
    result = StepValidationResult(pipeline_name=pipeline_name, step_name=name)

    # 1. PromptVariables registry presence.
    registered = get_prompt_variables(name)
    if registered is None:
        result.errors.append(PromptVariablesMissingError(
            f"No PromptVariables subclass registered for step "
            f"{name!r}. Add llm_pipelines/variables/{name}.py declaring "
            f"the corresponding XxxPrompt(PromptVariables) class.",
            pipeline_name=pipeline_name, step_name=name,
        ))
        # Without a registered class we can't run the bijection / shape
        # checks meaningfully. Move to YAML / Phoenix-only checks.
        prompt_cls = None
    else:
        prompt_cls = registered

    # 2. Registered class agrees with the step's cached
    # prompt_variables_cls (the one resolved at __init_subclass__ from
    # prepare()'s return annotation). Mismatch indicates discovery
    # ran twice with different roots, or someone monkey-patched.
    cached = getattr(step_cls, "prompt_variables_cls", None)
    if (
        prompt_cls is not None
        and cached is not None
        and cached is not prompt_cls
    ):
        result.errors.append(PromptVariablesRegistryMismatchError(
            f"Registered PromptVariables for {name!r} is "
            f"{prompt_cls.__module__}.{prompt_cls.__qualname__}, but "
            f"{step_cls.__name__}.prompt_variables_cls is "
            f"{cached.__module__}.{cached.__qualname__}.",
            pipeline_name=pipeline_name, step_name=name,
        ))

    # 3-8: YAML-side checks.
    yaml_path = prompts_dir / f"{name}.yaml"
    yaml_prompt = _load_yaml(yaml_path, pipeline_name, name, result)

    # 9-10: placeholder bijection (only meaningful if both YAML and
    # PromptVariables loaded cleanly).
    if yaml_prompt is not None and prompt_cls is not None:
        _check_placeholder_bijection(
            yaml_prompt=yaml_prompt,
            prompt_cls=prompt_cls,
            pipeline_name=pipeline_name,
            step_name=name,
            result=result,
        )

    # 11: Phoenix prompt presence.
    if not skip_phoenix_checks and prompt_client is not None:
        try:
            prompt_client.get_latest(name)
        except PromptNotFoundError:
            result.errors.append(PhoenixPromptMissingError(
                f"Phoenix has no prompt named {name!r}. Run "
                f"`uv run llm-pipeline build` to push the YAML, or "
                f"create the prompt manually in Phoenix Playground.",
                pipeline_name=pipeline_name, step_name=name,
            ))
        except PhoenixError as exc:
            # Phoenix transport failure — surface it like a missing
            # prompt; treat as fatal in build mode (the validator
            # entry point already raises if mode == build and the
            # client is missing).
            result.errors.append(PhoenixPromptMissingError(
                f"Phoenix lookup failed for prompt {name!r}: {exc}",
                pipeline_name=pipeline_name, step_name=name,
            ))

    return result


# ---------------------------------------------------------------------------
# YAML-side check helpers
# ---------------------------------------------------------------------------


def _load_yaml(
    yaml_path: Path,
    pipeline_name: str,
    step_name: str,
    result: StepValidationResult,
) -> Prompt | None:
    """Load + structurally validate the YAML file. Records errors on miss."""
    if not yaml_path.is_file():
        result.errors.append(PromptYamlMissingError(
            f"No YAML file at {yaml_path}. Each Step needs a paired "
            f"YAML at {{prompts_dir}}/{{step_name}}.yaml carrying "
            f"messages + model.",
            pipeline_name=pipeline_name, step_name=step_name,
        ))
        return None

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        result.errors.append(PromptYamlInvalidError(
            f"Could not parse {yaml_path.name}: {exc}",
            pipeline_name=pipeline_name, step_name=step_name,
        ))
        return None

    if not isinstance(raw, dict):
        result.errors.append(PromptYamlInvalidError(
            f"{yaml_path.name} root must be a mapping; got "
            f"{type(raw).__name__}.",
            pipeline_name=pipeline_name, step_name=step_name,
        ))
        return None

    try:
        prompt = Prompt.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError or similar
        result.errors.append(PromptYamlInvalidError(
            f"{yaml_path.name} is not a valid Prompt: {exc}",
            pipeline_name=pipeline_name, step_name=step_name,
        ))
        return None

    # 5. YAML.name == filename stem (== step_name())
    if prompt.name != step_name:
        result.errors.append(PromptNameMismatchError(
            f"{yaml_path.name}: 'name' field is {prompt.name!r} but "
            f"the file (and the step it's bound to) is {step_name!r}. "
            f"Filename and content must agree.",
            pipeline_name=pipeline_name, step_name=step_name,
        ))

    # 6. Model field is set.
    if not prompt.model:
        result.errors.append(PromptModelMissingError(
            f"{yaml_path.name} must declare a top-level `model:` field "
            f"(pydantic-ai format, e.g. 'openai:gpt-4o-mini'). The "
            f"model is the codebase's expression of intent for which "
            f"LLM this step calls.",
            pipeline_name=pipeline_name, step_name=step_name,
        ))
    else:
        # 7. pydantic-ai recognises the model string.
        try:
            _check_model_recognised(prompt.model)
        except ModelStringError as exc:
            result.errors.append(ModelNotRecognisedError(
                f"{yaml_path.name}: model {prompt.model!r} is not in "
                f"pydantic-ai's expected 'provider:name' shape: {exc}",
                pipeline_name=pipeline_name, step_name=step_name,
            ))
        except _ModelInferenceError as exc:
            result.errors.append(ModelNotRecognisedError(
                f"{yaml_path.name}: pydantic-ai cannot construct a "
                f"model from {prompt.model!r}: {exc}",
                pipeline_name=pipeline_name, step_name=step_name,
            ))

    # 8. Exactly one system message and one user message.
    roles = [m.role for m in prompt.messages]
    if roles.count("system") != 1 or roles.count("user") != 1 or len(roles) != 2:
        result.errors.append(PromptMessagesShapeError(
            f"{yaml_path.name}: messages must contain exactly one "
            f"'system' and one 'user' message (no extras, no "
            f"duplicates); got roles {roles!r}.",
            pipeline_name=pipeline_name, step_name=step_name,
        ))

    return prompt


def _check_placeholder_bijection(
    *,
    yaml_prompt: Prompt,
    prompt_cls: type,
    pipeline_name: str,
    step_name: str,
    result: StepValidationResult,
) -> None:
    """Verify the prompt's placeholders match its declared variables.

    Phoenix's variable model is message-agnostic, so the check is
    prompt-level rather than per-message: every placeholder across
    both messages must be a known variable, and every declared
    variable must appear as a placeholder in at least one message.
    Variables come from two complementary sources on the
    ``XxxPrompt`` subclass:

    - ``model_fields``: prepare-supplied (Pydantic fields)
    - ``auto_vars``: framework-supplied (auto_generate expressions)

    Mutual exclusion between those two sources is enforced at
    ``__init_subclass__`` time, so a name is at most one of them.
    """
    sys_content = next(
        (m.content for m in yaml_prompt.messages if m.role == "system"), None,
    )
    user_content = next(
        (m.content for m in yaml_prompt.messages if m.role == "user"), None,
    )

    sys_placeholders = (
        set(extract_variables_from_content(sys_content))
        if sys_content else set()
    )
    user_placeholders = (
        set(extract_variables_from_content(user_content))
        if user_content else set()
    )
    all_placeholders = sys_placeholders | user_placeholders

    declared_fields = set(prompt_cls.model_fields.keys())
    declared_auto = set(getattr(prompt_cls, "auto_vars", {}).keys())
    declared = declared_fields | declared_auto

    missing_in_class = all_placeholders - declared
    missing_in_template = declared - all_placeholders

    if missing_in_class or missing_in_template:
        result.errors.append(PromptVariableDriftError(
            _format_drift(
                prompt_cls=prompt_cls,
                sys_placeholders=sys_placeholders,
                user_placeholders=user_placeholders,
                missing_in_template=missing_in_template,
                missing_in_class=missing_in_class,
            ),
            pipeline_name=pipeline_name, step_name=step_name,
        ))


def _format_drift(
    *,
    prompt_cls: type,
    sys_placeholders: set[str],
    user_placeholders: set[str],
    missing_in_template: set[str],
    missing_in_class: set[str],
) -> str:
    """Build a readable diff message for placeholder/variable drift."""
    parts: list[str] = [
        f"{prompt_cls.__qualname__} placeholders are not bijective with "
        f"its declared variables (model_fields ∪ auto_vars)."
    ]
    if missing_in_template:
        parts.append(
            f"Declared on {prompt_cls.__qualname__} but missing from "
            f"both messages: {sorted(missing_in_template)!r}."
        )
    if missing_in_class:
        # Try to attribute each unknown placeholder to its message
        # for a more useful error.
        unknown_in_system = sorted(missing_in_class & sys_placeholders)
        unknown_in_user = sorted(missing_in_class & user_placeholders)
        if unknown_in_system:
            parts.append(
                f"Used in the system message but not declared on "
                f"{prompt_cls.__qualname__}: {unknown_in_system!r}."
            )
        if unknown_in_user:
            parts.append(
                f"Used in the user message but not declared on "
                f"{prompt_cls.__qualname__}: {unknown_in_user!r}."
            )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Model recognition helper
# ---------------------------------------------------------------------------


class _ModelInferenceError(Exception):
    """Internal: pydantic-ai's infer_model rejected the string.

    Wrapped so callers don't depend on pydantic-ai's specific
    UserError type (which lives at ``pydantic_ai.exceptions.UserError``).
    """


def _check_model_recognised(pai_model: str) -> None:
    """Verify ``pai_model`` is a string pydantic-ai understands.

    Calls ``pydantic_ai.models.infer_model(pai_model)``. Raises
    :class:`ModelStringError` if the string isn't of the form
    ``provider:name`` and :class:`_ModelInferenceError` if pydantic-ai
    can't construct a model from it.
    """
    # Format check (same logic as pai_model_to_phoenix).
    if ":" not in pai_model:
        raise ModelStringError(
            f"Expected 'provider:name', got {pai_model!r}."
        )
    provider, _, name = pai_model.partition(":")
    if not provider or not name:
        raise ModelStringError(
            f"Empty provider or name in {pai_model!r}."
        )

    # Defer the actual pydantic-ai import — keeps the module cheap to
    # import in contexts that don't run validation (tests, type-checks).
    try:
        from pydantic_ai.models import infer_model
    except ImportError as exc:  # pragma: no cover - dev env always has pai
        raise _ModelInferenceError(
            f"pydantic-ai is not importable: {exc}"
        ) from exc

    try:
        infer_model(pai_model)
    except Exception as exc:
        # pydantic_ai raises UserError on unknown providers /
        # malformed names. We catch broadly so the validator stays
        # robust across pydantic-ai upgrades.
        raise _ModelInferenceError(str(exc)) from exc
