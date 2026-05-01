"""Offline alignment validator (code ↔ YAML ↔ pydantic-ai).

Runs at ``uv run llm-pipeline build``. Validates the alignment
between code (LLMStepNode subclasses + PromptVariables registry) and
the YAML on disk (``llm-pipeline-prompts/{step_name}.yaml``). All
checks are offline — no Phoenix interaction. Phoenix-side state
(prompt presence, etc.) is reconciled by ``llm-pipeline pull`` /
``push`` independently; this validator's job is to catch
misalignments in the user's source-of-truth files before they hit
Phoenix.

Strictness mirrors the node / pipeline validators we ship at
``__init_subclass__`` time. Errors are accumulated across every step
in every registered pipeline, then a single
``PhoenixValidationFailed`` is raised at the end. Devs see the whole
picture, not the first failure.

The file is named ``phoenix_validator`` because the alignment it
verifies is what Phoenix expects (placeholder ↔ variable_definitions,
pydantic-ai-compatible model strings). It does not, however, talk to
Phoenix.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from llm_pipeline.prompts.models import (
    ModelStringError,
    Prompt,
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
    "AutoGenerateExpressionError",
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


class AutoGenerateExpressionError(PhoenixValidationError):
    """An ``auto_vars`` expression failed build-time validation.

    The check runs in four tiers; this error fires on the first one
    that fails:

    1. ``build_auto_generate_factory(expr)`` raises — the expression
       didn't parse, or the function name isn't recognised.
    2. The named object doesn't resolve in
       ``_AUTO_GENERATE_REGISTRY`` (or the discovery base path).
    3. The factory raises at invoke — e.g. ``enum_names(X)`` where
       ``X`` is registered but isn't an ``enum.Enum`` subclass.
    4. The factory's output is empty (e.g. an empty enum) or
       contains literal ``{`` / ``}`` that would corrupt subsequent
       ``str.format`` substitution.
    """


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


def validate_phoenix_alignment(
    introspection_registry: dict[str, type["Pipeline"]],
    prompts_dir: Path,
) -> PhoenixValidationReport:
    """Validate every Step's code↔YAML alignment.

    All checks are offline. ``PhoenixValidationFailed`` is raised at
    the end if any per-step error was recorded. Callers (UI startup
    in dev mode, etc.) that want non-fatal behavior should catch
    that exception themselves.

    Args:
        introspection_registry: ``pipeline_name -> Pipeline subclass``
            map (the same registry the runtime uses).
        prompts_dir: Directory holding ``{step_name}.yaml`` files.

    Returns:
        ``PhoenixValidationReport`` carrying per-step results when
        all checks pass.

    Raises:
        ``PhoenixValidationFailed`` if any error was recorded.
    """
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
            )
            report.steps.append(result)

    if not report.ok:
        raise PhoenixValidationFailed(errors=report.errors)

    return report


# ---------------------------------------------------------------------------
# Per-step validation
# ---------------------------------------------------------------------------


def _validate_one_step(
    *,
    pipeline_name: str,
    step_cls: type,
    prompts_dir: Path,
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
        # checks meaningfully. Move to YAML-only checks.
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

    # 10b: auto_vars expressions resolve + invoke + produce safe output.
    if prompt_cls is not None:
        _check_auto_vars_expressions(
            prompt_cls=prompt_cls,
            pipeline_name=pipeline_name,
            step_name=name,
            result=result,
        )

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
# auto_vars expression validation
# ---------------------------------------------------------------------------


def _check_auto_vars_expressions(
    *,
    prompt_cls: type,
    pipeline_name: str,
    step_name: str,
    result: StepValidationResult,
) -> None:
    """Validate every ``auto_vars`` expression on ``prompt_cls``.

    Four-tier check, fails fast at the first failing tier:

    1. ``build_auto_generate_factory(expr)`` — parse + recognise the
       function name (``enum_values`` / ``enum_names`` / ``enum_value``
       / ``constant``).
    2. The factory's ``_resolve_object`` finds the named target in
       the auto_generate registry (or via discovery base path).
    3. The factory invokes successfully — catches type mismatches
       (e.g. ``enum_names(X)`` where ``X`` is a constant, not an Enum).
    4. The factory's output is a non-empty string AND doesn't contain
       literal ``{`` / ``}`` that would corrupt the next
       ``str.format`` pass during template rendering.

    Records each failure as a separate
    :class:`AutoGenerateExpressionError` so a prompt with several
    bad entries surfaces all of them in one run.
    """
    from llm_pipeline.prompts.variables import build_auto_generate_factory

    auto_vars: dict[str, str] = getattr(prompt_cls, "auto_vars", {})
    for placeholder, expr in auto_vars.items():
        # Tiers 1+2: parse + resolution.
        try:
            factory = build_auto_generate_factory(expr)
        except Exception as exc:  # noqa: BLE001 — parser raises ValueError; resolver may raise others
            result.errors.append(AutoGenerateExpressionError(
                f"{prompt_cls.__qualname__}.auto_vars[{placeholder!r}] "
                f"= {expr!r}: failed to build factory: {exc}",
                pipeline_name=pipeline_name, step_name=step_name,
            ))
            continue

        # Tier 3: invoke. The factory may resolve its target lazily,
        # so name-resolution failures (Enum not registered, etc.)
        # surface here too.
        try:
            output = factory()
        except Exception as exc:  # noqa: BLE001
            result.errors.append(AutoGenerateExpressionError(
                f"{prompt_cls.__qualname__}.auto_vars[{placeholder!r}] "
                f"= {expr!r}: factory invocation failed: {exc}",
                pipeline_name=pipeline_name, step_name=step_name,
            ))
            continue

        # Tier 4a: output type + emptiness.
        if not isinstance(output, str):
            result.errors.append(AutoGenerateExpressionError(
                f"{prompt_cls.__qualname__}.auto_vars[{placeholder!r}] "
                f"= {expr!r}: factory must produce a string; got "
                f"{type(output).__name__}.",
                pipeline_name=pipeline_name, step_name=step_name,
            ))
            continue
        if not output:
            result.errors.append(AutoGenerateExpressionError(
                f"{prompt_cls.__qualname__}.auto_vars[{placeholder!r}] "
                f"= {expr!r}: factory produced an empty string. "
                f"This usually means the registered enum has no "
                f"members or the constant is empty.",
                pipeline_name=pipeline_name, step_name=step_name,
            ))
            continue

        # Tier 4b: format-safety.
        if "{" in output or "}" in output:
            result.errors.append(AutoGenerateExpressionError(
                f"{prompt_cls.__qualname__}.auto_vars[{placeholder!r}] "
                f"= {expr!r}: factory output contains literal '{{' or "
                f"'}}' ({output!r}) — this would corrupt template "
                f"rendering. The auto_generate value must be safe to "
                f"substitute via str.format.",
                pipeline_name=pipeline_name, step_name=step_name,
            ))


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
