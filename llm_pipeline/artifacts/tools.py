"""``ToolSpec`` — :class:`AgentTool` subclasses.

Each ``tools/foo.py`` declares an :class:`llm_pipeline.agent_tool.AgentTool`
subclass with nested ``Inputs`` (StepInputs) and ``Args`` (BaseModel)
classes plus a ``run`` classmethod. Steps bind tools via
``DEFAULT_TOOLS``; the walker registers each tool in
``registries[KIND_TOOL]``.
"""
from __future__ import annotations

from typing import Any, Literal

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.kinds import KIND_TOOL
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.renderers import (
    render_code_body,
    render_pydantic_class,
)
from llm_pipeline.artifacts.base.template import ArtifactTemplate
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)
from llm_pipeline.artifacts.base.writer import Writer


__all__ = [
    "MANIFEST",
    "ToolBuilder",
    "ToolSpec",
    "ToolWriter",
    "ToolsWalker",
]


class ToolSpec(ArtifactSpec):
    """An ``AgentTool`` subclass declared in ``llm_pipelines/tools/``."""

    kind: Literal[KIND_TOOL] = KIND_TOOL  # type: ignore[assignment]

    # Pydantic Inputs class shape — pipeline-side data the tool needs.
    inputs: JsonSchemaWithRefs | None = None

    # Pydantic Args class shape — what the LLM passes per call. Drives
    # the tool schema sent to the model.
    args: JsonSchemaWithRefs | None = None

    # Body of ``run(cls, inputs, args, ctx)``.
    body: CodeBodySpec | None = None


class ToolBuilder(SpecBuilder):
    """Build a :class:`ToolSpec` from an :class:`AgentTool` subclass.

    Reads ``cls.INPUTS`` / ``cls.ARGS`` / ``cls.run`` directly. Missing
    attrs produce ``None``-valued spec fields; the per-class capture
    model surfaces the contract violation.
    """

    SPEC_CLS = ToolSpec

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        args_cls = getattr(cls, "ARGS", None)
        return {
            "inputs": self.json_schema(inputs_cls),
            "args": self.json_schema(args_cls),
            "body": self.code_body("run"),
        }


class ToolsWalker(Walker):
    """Register :class:`AgentTool` subclasses from ``tools/``.

    Each subclass declares ``INPUTS`` / ``ARGS`` ClassVars (paired
    StepInputs / BaseModel classes) plus a ``run`` classmethod.
    Class-level contract violations live on ``cls._init_subclass_errors``
    and flow into ``ToolSpec`` via :meth:`ArtifactSpec.attach_class_captures`.
    """

    BUILDER = ToolBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.agent_tool import AgentTool

        return _is_locally_defined_class(value, mod, AgentTool)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Tool")


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


_TOOL_TEMPLATE = ArtifactTemplate(template="""\
from pydantic import BaseModel

from llm_pipeline.agent_tool import AgentTool
from llm_pipeline.inputs import StepInputs


{{ inputs_class }}


{{ args_class }}


class {{ tool_class_name }}(AgentTool):
    INPUTS = {{ inputs_class_name }}
    ARGS = {{ args_class_name }}

{{ run_method }}
""")


class ToolWriter(Writer):
    """Render / edit a :class:`ToolSpec` to/from source.

    A tool file holds three classes — paired ``Inputs`` /
    ``Args`` / the ``AgentTool`` subclass. ``write()`` renders all
    three; ``edit()`` swaps them independently:

    - Inputs class via :func:`replace_class`
    - Args class via :func:`replace_class`
    - ``run`` method body via :func:`replace_method_body`
    """

    SPEC_CLS = ToolSpec

    def write(self) -> str:
        return _TOOL_TEMPLATE.render(
            tool_class_name=self._tool_class_name(),
            inputs_class_name=self._inputs_class_name(),
            args_class_name=self._args_class_name(),
            inputs_class=self._render_inputs_class(),
            args_class=self._render_args_class(),
            run_method=self._render_run_method(indent="    "),
        )

    def edit(self, original: str) -> str:
        import libcst as cst

        from llm_pipeline.codegen import (
            replace_class,
            replace_method_body,
        )

        source = original

        # Inputs / Args / Tool classes — independent replace_class calls.
        for class_name, new_source in (
            (self._inputs_class_name(), self._render_inputs_class()),
            (self._args_class_name(), self._render_args_class()),
        ):
            if not new_source:
                continue
            try:
                module = cst.parse_module(source)
                module = replace_class(
                    module=module,
                    class_name=class_name,
                    new_class_source=new_source,
                )
                source = module.code
            except Exception:
                # Class missing in source — skip rather than break;
                # paired classes can have been hand-renamed.
                continue

        # run() body via line-level splice.
        if self.spec.body is not None:
            try:
                source = replace_method_body(
                    source=source,
                    class_name=self._tool_class_name(),
                    method_name="run",
                    new_body=self.spec.body.source,
                )
            except Exception:
                pass

        return source

    # -- name derivation ------------------------------------------------

    def _tool_class_name(self) -> str:
        return self.spec.cls.rsplit(".", 1)[-1]

    def _prefix(self) -> str:
        name = self._tool_class_name()
        return name[: -len("Tool")] if name.endswith("Tool") else name

    def _inputs_class_name(self) -> str:
        return f"{self._prefix()}Inputs"

    def _args_class_name(self) -> str:
        return f"{self._prefix()}Args"

    # -- per-section renderers -----------------------------------------

    def _render_inputs_class(self) -> str:
        if self.spec.inputs is None:
            return f"class {self._inputs_class_name()}(StepInputs):\n    pass"
        return render_pydantic_class(
            name=self._inputs_class_name(),
            schema=self.spec.inputs,
            base="StepInputs",
        )

    def _render_args_class(self) -> str:
        if self.spec.args is None:
            return f"class {self._args_class_name()}(BaseModel):\n    pass"
        return render_pydantic_class(
            name=self._args_class_name(),
            schema=self.spec.args,
            base="BaseModel",
        )

    def _render_run_method(self, *, indent: str) -> str:
        if self.spec.body is None:
            return f"{indent}@classmethod\n{indent}def run(cls, inputs, args, ctx):\n{indent}    raise NotImplementedError"
        return (
            f"{indent}@classmethod\n"
            + render_code_body(
                self.spec.body,
                signature=f"{indent}def run(cls, inputs, args, ctx):",
                indent=indent + "    ",
            )
        )


MANIFEST = ArtifactManifest(
    subfolder="tools",
    level=3,
    spec_cls=ToolSpec,
    walker=ToolsWalker(),
)
