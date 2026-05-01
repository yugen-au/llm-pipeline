"""``PromptVariables`` base class + registry, plus ``auto_generate`` evaluator.

``PromptVariables`` is a Pydantic ``BaseModel``. Subclasses declare
each prompt variable as a Pydantic field with
``Field(description="...")``. Variables are *message-agnostic* — a
placeholder ``{x}`` in either the system or user message renders to
the same value at request time, matching Phoenix's flat
``variable_definitions`` data model.

Subclasses live in ``llm_pipelines/variables/{prompt_name}.py`` and are
auto-discovered into ``PROMPT_VARIABLES_REGISTRY`` by snake_case class
name (sans the ``Prompt`` suffix). The registry keys map 1:1 to step
``step_name()`` and Phoenix prompt names.

A ``auto_vars: ClassVar[dict[str, str]]`` declares placeholders the
framework fills at render time from auto_generate expressions
(``enum_values(X)``, ``enum_names(X)``, ``enum_value(X, MEMBER)``,
``constant(value)``). Those placeholders are NOT constructor args —
LLM-authors cannot override them by accident — so override-prevention
is structural. ``__init_subclass__`` enforces mutual exclusion: a
name MUST be either a Pydantic field (prepare-supplied) OR an
``auto_vars`` entry (framework-supplied), never both.
"""
from __future__ import annotations

import importlib
import logging
import re
from typing import Any, Callable, ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PromptVariables base class + registry
# ---------------------------------------------------------------------------


class PromptVariables(BaseModel):
    """Container for one prompt's variables — declared as Pydantic fields.

    Subclass and declare each variable as a Pydantic field. Every field
    must use ``Field(description="...")``; this is enforced at
    class-definition time.

    The class name (with the ``Prompt`` suffix stripped, snake-cased)
    maps 1:1 to the Phoenix prompt name and the owning ``LLMStepNode``
    subclass's ``step_name()``.

    Instances hold validated variable values; the framework reads
    ``instance.model_dump()`` to render *both* the system and user
    Phoenix message templates with the same variable namespace.

    Example::

        class TopicExtractionPrompt(PromptVariables):
            text: str = Field(description="Input text")
            sentiment: str = Field(description="Detected sentiment")

            auto_vars: ClassVar[dict[str, str]] = {
                "sentiment_options": "enum_names(Sentiment)",
            }

        TopicExtractionPrompt(text="hi", sentiment="POSITIVE")

    The ``auto_vars`` ClassVar is a class-level constant (Pydantic
    respects ``ClassVar`` and excludes it from ``model_fields``).
    Its keys are placeholders filled by the framework at render time
    from auto_generate expressions; LLM-authors cannot pass them as
    constructor args.
    """

    auto_vars: ClassVar[dict[str, str]] = {}

    # Validation issues captured at __pydantic_init_subclass__ time.
    # Empty when the class's contract is satisfied; populated otherwise.
    # The class object always constructs successfully — runtime
    # consumers (and ``derive_issues`` over the spec) consult this list
    # to decide whether the class is usable.
    _init_subclass_errors: ClassVar[list[Any]] = []

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        # Pydantic's hook (instead of __init_subclass__) — guaranteed
        # to run AFTER Pydantic has finalized model_fields, so the
        # field-iteration below sees the complete picture.
        super().__pydantic_init_subclass__(**kwargs)

        from llm_pipeline.graph.spec import (
            ValidationIssue,
            ValidationLocation,
        )

        errors: list[ValidationIssue] = []

        # 1. Every field must use Field(description=...).
        for field_name, field_info in cls.model_fields.items():
            if not field_info.description:
                errors.append(ValidationIssue(
                    severity="error", code="missing_field_description",
                    message=(
                        f"{cls.__name__}.{field_name} must use "
                        f"Field(description='...')."
                    ),
                    location=ValidationLocation(
                        node=cls.__name__, field=field_name,
                    ),
                    suggestion=(
                        f"Replace the field definition with "
                        f"`{field_name}: <type> = Field(description='...')`."
                    ),
                ))

        # 2. auto_vars shape: dict[str, str] with non-empty keys/values.
        auto_vars = cls.__dict__.get("auto_vars", {})
        if auto_vars and not isinstance(auto_vars, dict):
            errors.append(ValidationIssue(
                severity="error", code="auto_vars_not_dict",
                message=(
                    f"{cls.__name__}.auto_vars must be a dict[str, str] "
                    f"of placeholder -> auto_generate expression; got "
                    f"{type(auto_vars).__name__}."
                ),
                location=ValidationLocation(
                    node=cls.__name__, field="auto_vars",
                ),
            ))
            auto_vars = {}  # treat as empty for the remaining checks
        for placeholder, expr in auto_vars.items():
            if not isinstance(placeholder, str) or not placeholder:
                errors.append(ValidationIssue(
                    severity="error", code="auto_vars_bad_placeholder",
                    message=(
                        f"{cls.__name__}.auto_vars: placeholder names "
                        f"must be non-empty strings; got {placeholder!r}."
                    ),
                    location=ValidationLocation(
                        node=cls.__name__, field="auto_vars",
                    ),
                ))
            if not isinstance(expr, str) or not expr:
                errors.append(ValidationIssue(
                    severity="error", code="auto_vars_bad_expression",
                    message=(
                        f"{cls.__name__}.auto_vars[{placeholder!r}] "
                        f"must be a non-empty auto_generate expression "
                        f"string; got {expr!r}."
                    ),
                    location=ValidationLocation(
                        node=cls.__name__, field="auto_vars",
                    ),
                ))

        # 3. Mutual exclusion: no name in both fields and auto_vars.
        overlap = set(cls.model_fields.keys()) & set(auto_vars.keys())
        if overlap:
            errors.append(ValidationIssue(
                severity="error", code="auto_vars_field_overlap",
                message=(
                    f"{cls.__name__}: placeholder name(s) "
                    f"{sorted(overlap)!r} appear in BOTH model_fields "
                    f"and auto_vars. A placeholder is either "
                    f"prepare-supplied (a Pydantic field) or framework-"
                    f"supplied (an auto_vars entry), never both."
                ),
                location=ValidationLocation(
                    node=cls.__name__, field="auto_vars",
                ),
                suggestion=(
                    f"Remove the overlapping name(s) from one side."
                ),
            ))

        cls._init_subclass_errors = errors


# Module-global registry. Keyed by snake_case class name with ``Prompt``
# suffix stripped — i.e. the same string returned by
# ``LLMStepNode.step_name()``.
_PROMPT_VARIABLES_REGISTRY: dict[str, type[PromptVariables]] = {}


def register_prompt_variables(name: str, cls: type[PromptVariables]) -> None:
    """Register a ``PromptVariables`` subclass under a snake_case key.

    Raises ``ValueError`` if ``name`` is already registered with a
    different class. Re-registering the *same* class is a no-op
    (allows convention discovery to run multiple times safely).
    """
    existing = _PROMPT_VARIABLES_REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Duplicate PromptVariables registration for {name!r}: "
            f"existing={existing!r}, new={cls!r}"
        )
    _PROMPT_VARIABLES_REGISTRY[name] = cls


def get_prompt_variables(name: str) -> type[PromptVariables] | None:
    """Look up a registered ``PromptVariables`` subclass by snake_case name."""
    return _PROMPT_VARIABLES_REGISTRY.get(name)


def get_all_prompt_variables() -> dict[str, type[PromptVariables]]:
    """Return a copy of the full registry. For introspection / tests."""
    return dict(_PROMPT_VARIABLES_REGISTRY)


def clear_prompt_variables_registry() -> None:
    """Clear the registry. For test teardown."""
    _PROMPT_VARIABLES_REGISTRY.clear()


# ---------------------------------------------------------------------------
# auto_generate registry
# ---------------------------------------------------------------------------


_AUTO_GENERATE_REGISTRY: dict[str, object] = {}
_AUTO_GENERATE_BASE_PATH: str | None = None

_EXPR_PATTERN = re.compile(
    r"^(enum_values|enum_names|enum_value|constant)\((.+)\)$"
)


def register_auto_generate(name: str, obj: object) -> None:
    """Register a Python object (enum, constant) for auto_generate expressions."""
    _AUTO_GENERATE_REGISTRY[name] = obj


def set_auto_generate_base_path(base_path: str | None) -> None:
    """Set the base module path for convention-based object resolution."""
    global _AUTO_GENERATE_BASE_PATH
    _AUTO_GENERATE_BASE_PATH = base_path


def clear_auto_generate_registry() -> None:
    """Clear auto_generate registry and base path. For test teardown."""
    global _AUTO_GENERATE_BASE_PATH
    _AUTO_GENERATE_REGISTRY.clear()
    _AUTO_GENERATE_BASE_PATH = None


def _parse_auto_generate(expr: str) -> tuple[str, list[str]]:
    """Parse ``func_name(arg1, arg2)`` -> ``(func_name, [arg1, arg2])``."""
    m = _EXPR_PATTERN.match(expr.strip())
    if not m:
        raise ValueError(f"Unrecognized auto_generate expression: {expr!r}")
    return m.group(1), [a.strip() for a in m.group(2).split(",")]


def _resolve_object(name: str, import_path: str | None, expr_type: str) -> object:
    """Resolve a named object via registry -> import_path -> convention."""
    if name in _AUTO_GENERATE_REGISTRY:
        return _AUTO_GENERATE_REGISTRY[name]

    if import_path:
        module_path, _, attr = import_path.rpartition(".")
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    if _AUTO_GENERATE_BASE_PATH:
        submodule = "enums" if expr_type.startswith("enum") else "constants"
        full_path = f"{_AUTO_GENERATE_BASE_PATH}.{submodule}"
        try:
            mod = importlib.import_module(full_path)
            return getattr(mod, name)
        except (ImportError, AttributeError):
            pass

    raise ValueError(
        f"Cannot resolve {name!r} for auto_generate. Register via "
        f"register_auto_generate(), provide import_path, or set "
        f"base_path via set_auto_generate_base_path()."
    )


def build_auto_generate_factory(
    expr: str, import_path: str | None = None,
) -> Callable[[], str]:
    """Build a callable that resolves an ``auto_generate`` expression at call time."""
    func_name, args = _parse_auto_generate(expr)

    if func_name == "enum_values":
        name = args[0]

        def factory(_name=name, _import_path=import_path, _fn=func_name) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(str(e.value) for e in obj)

        return factory

    if func_name == "enum_names":
        name = args[0]

        def factory(_name=name, _import_path=import_path, _fn=func_name) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(e.name for e in obj)

        return factory

    if func_name == "enum_value":
        if len(args) != 2:
            raise ValueError(
                f"enum_value requires 2 args (EnumName, MEMBER), got {len(args)}"
            )
        name, member = args[0], args[1]

        def factory(
            _name=name, _member=member, _import_path=import_path, _fn=func_name,
        ) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return str(obj[_member].value)

        return factory

    if func_name == "constant":
        value = args[0]

        def factory(_value=value) -> str:
            return _value

        return factory

    raise ValueError(f"Unknown auto_generate function: {func_name}")


__all__ = [
    # PromptVariables
    "PromptVariables",
    "register_prompt_variables",
    "get_prompt_variables",
    "get_all_prompt_variables",
    "clear_prompt_variables_registry",
    # auto_generate (existing)
    "register_auto_generate",
    "set_auto_generate_base_path",
    "clear_auto_generate_registry",
    "build_auto_generate_factory",
]
