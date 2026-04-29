"""
Base class for LLM pipeline configuration and orchestration.

DESIGN PHILOSOPHY:
- Pipeline owns context (metadata and step results), data (input + transformations), and db_instances
- Steps receive pipeline reference and can access/modify all three
- Clear separation: context for results, data for transformations, db_instances for persistence
- Automatic state tracking for audit trail and caching
"""
import hashlib
import json
import logging
import uuid
from abc import ABC
from datetime import datetime, timezone
from types import MappingProxyType
from typing import (
    Any,
    ClassVar,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    TYPE_CHECKING,
)

from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session

from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.consensus import instructions_match, ConsensusResult
from llm_pipeline.naming import to_snake_case
from llm_pipeline.wiring import AdapterContext, Bind

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from pydantic_ai import InstrumentationSettings
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.consensus import ConsensusStrategy
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.prompts.variables import VariableResolver

TModel = TypeVar("TModel", bound=SQLModel)


def _append_review_to_prompt(user_prompt: str, review_ctx: dict) -> str:
    """Append human review feedback to the rendered user prompt.

    Automatically injected when _review_context is in pipeline context.
    Cleared after the step runs so it doesn't leak to subsequent steps.
    """
    decision = review_ctx.get("decision", "")
    notes = review_ctx.get("notes", "")
    original = review_ctx.get("original_output", "")

    if not notes:
        return user_prompt

    if decision == "minor_revision":
        appendix = (
            "\n\n---\n"
            "Your previous output requires minor revision.\n\n"
            f"Reviewer feedback:\n{notes}\n\n"
            f"Previous output:\n{original}\n\n"
            "Please consider this feedback and make a revision to the previous output accordingly."
        )
    elif decision == "major_revision":
        appendix = (
            "\n\n---\n"
            "A previous attempt at this step was rejected. "
            f"The reviewer left the following feedback:\n{notes}"
        )
    elif decision == "approved":
        appendix = (
            "\n\n---\n"
            "A reviewer approved the previous step and left these notes for context:\n"
            f"{notes}"
        )
    else:
        return user_prompt

    return user_prompt + appendix




class StepKeyDict(dict):
    """Dictionary that accepts both string keys and Step class keys."""

    @staticmethod
    def _normalize_key(key):
        if isinstance(key, type) and key.__name__.endswith("Step"):
            return to_snake_case(key.__name__, strip_suffix="Step")
        return key

    def __getitem__(self, key):
        return super().__getitem__(self._normalize_key(key))

    def __setitem__(self, key, value):
        return super().__setitem__(self._normalize_key(key), value)

    def __contains__(self, key):
        return super().__contains__(self._normalize_key(key))

    def get(self, key, default=None):
        return super().get(self._normalize_key(key), default)

    def pop(self, key, *args):
        return super().pop(self._normalize_key(key), *args)


def _extract_raw_response(run_result: Any) -> str | None:
    """Extract raw LLM response text from a pydantic-ai RunResult.

    Finds the last ModelResponse in run_result.new_messages() and serializes
    its parts: ToolCallPart.args as JSON, TextPart.content as-is.
    Returns None if no ModelResponse found.
    """
    from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart

    try:
        messages = run_result.new_messages()
    except Exception:
        return None

    # Find last ModelResponse
    model_response = None
    for msg in messages:
        if isinstance(msg, ModelResponse):
            model_response = msg

    if model_response is None:
        return None

    parts_text: list[str] = []
    for part in model_response.parts:
        if isinstance(part, ToolCallPart):
            try:
                parts_text.append(json.dumps(part.args))
            except (TypeError, ValueError):
                parts_text.append(str(part.args))
        elif isinstance(part, TextPart):
            parts_text.append(part.content)

    return "\n".join(parts_text) if parts_text else None


class PipelineConfig(ABC):
    """
    Base class for defining LLM pipeline configurations.

    Manages step results, context, data, extractions, strategies, and registry.

    Subclasses must provide registry and strategies:

        class MyPipeline(PipelineConfig,
                        registry=MyRegistry,
                        strategies=MyStrategies):
            pass

    Constructor accepts dependency injection for decoupling:
        - model: pydantic-ai model string (e.g. 'google-gla:gemini-2.0-flash-lite')
        - engine: SQLAlchemy engine (auto-SQLite if omitted)
        - session: Existing session (overrides engine)
        - variable_resolver: Optional VariableResolver for prompt variables
    """

    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
    INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None

    def __init_subclass__(cls, registry=None, strategies=None, **kwargs):
        super().__init_subclass__(**kwargs)

        if registry is not None or strategies is not None:
            if not cls.__name__.endswith("Pipeline"):
                raise ValueError(
                    f"Pipeline class '{cls.__name__}' must end with 'Pipeline' suffix."
                )
            pipeline_name_prefix = cls.__name__[:-8]

            if registry is not None:
                expected = f"{pipeline_name_prefix}Registry"
                if registry.__name__ != expected:
                    raise ValueError(
                        f"Registry for {cls.__name__} must be named '{expected}', "
                        f"got '{registry.__name__}'"
                    )

            if strategies is not None:
                expected = f"{pipeline_name_prefix}Strategies"
                if strategies.__name__ != expected:
                    raise ValueError(
                        f"Strategies for {cls.__name__} must be named '{expected}', "
                        f"got '{strategies.__name__}'"
                    )

        if registry is not None:
            cls.REGISTRY = registry
        if strategies is not None:
            cls.STRATEGIES = strategies

        if cls.INPUT_DATA is not None and not (
            isinstance(cls.INPUT_DATA, type) and issubclass(cls.INPUT_DATA, PipelineInputData)
        ):
            raise TypeError(
                f"{cls.__name__}.INPUT_DATA must be a PipelineInputData subclass, "
                f"got {cls.INPUT_DATA!r}"
            )

    def __init__(
        self,
        model: str,
        strategies: Optional[List["PipelineStrategy"]] = None,
        session: Optional[Session] = None,
        engine: Optional[Engine] = None,
        variable_resolver: Optional["VariableResolver"] = None,
        run_id: Optional[str] = None,
        instrumentation_settings: Any | None = None,
    ):
        """
        Initialize pipeline.

        Args:
            model: pydantic-ai model string (e.g. 'google-gla:gemini-2.0-flash-lite').
            strategies: Optional list of PipelineStrategy instances.
            session: Optional database session. Overrides engine if provided.
            engine: Optional SQLAlchemy engine. Auto-SQLite if both session and engine are None.
            variable_resolver: Optional VariableResolver for prompt variable classes.
            instrumentation_settings: Optional pydantic-ai InstrumentationSettings for per-agent OTel instrumentation.
        """
        from llm_pipeline.db import init_pipeline_db, get_session as db_get_session
        from llm_pipeline.session import ReadOnlySession

        self._model = model
        if variable_resolver is None:
            from llm_pipeline.prompts.variables import RegistryVariableResolver
            variable_resolver = RegistryVariableResolver()
        self._variable_resolver = variable_resolver
        self._instrumentation_settings = instrumentation_settings

        # Validate REGISTRY and STRATEGIES
        if self.REGISTRY is None:
            raise ValueError(
                f"{self.__class__.__name__} must specify registry parameter when defining the class."
            )
        if self.STRATEGIES is None and strategies is None:
            raise ValueError(
                f"{self.__class__.__name__} must specify strategies parameter when defining the class."
            )

        if strategies is None:
            strategies = self.STRATEGIES.create_instances()
        self._strategies = strategies

        # Private storage
        self._instructions = StepKeyDict()
        self._context: Dict[str, Any] = {}

        # Public storage
        self.data = StepKeyDict()
        self.extractions: Dict[Type[SQLModel], List[SQLModel]] = {}

        # Validated input (populated by execute() when INPUT_DATA declared)
        self._validated_input = None

        # Execution tracking
        self._step_order: Dict[Type, int] = {}
        self._model_extraction_step: Dict[Type[SQLModel], Type] = {}
        self._step_data_transformations: Dict[Type, Type] = {}
        self._executed_steps: set = set()
        self._current_step: Optional[Type] = None
        self._current_extraction: Optional[Type] = None

        # Step-level dependency graph (step_class -> set of step classes
        # it depends on). Aggregates two sources: extraction FK chains
        # (a step extracting WidgetReview FKs into Widget => depends on
        # whichever step extracts Widget) and FromOutput references in
        # step / extraction / tool inputs_spec. Built once at __init__
        # time and used to validate ordering.
        self._step_deps: Dict[Type, Set[Type]] = {}
        # Edge provenance for diagnostic messages: (dependent, dep) ->
        # list of human-readable reasons.
        self._step_dep_reasons: Dict[Tuple[Type, Type], List[str]] = {}

        self._build_execution_order()
        self._build_step_dependency_graph()
        self._validate_step_dependency_graph()

        self.run_id = run_id or str(uuid.uuid4())

        # Bootstrap OTEL + pydantic-ai instrumentation. Spans ship
        # off-host only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set;
        # otherwise the framework runs in-process (live UI works,
        # nothing leaves the host). Idempotent across multiple
        # pipeline instantiations in the same process.
        from llm_pipeline import observability as _obs_mod
        _obs_mod.configure()
        self._observer = _obs_mod.PipelineObserver(
            run_id=self.run_id, pipeline_name=self.pipeline_name,
        )

        # Session setup: explicit session > engine > auto-SQLite
        if session is not None:
            self._owns_session = False
            self._real_session = session
        else:
            if engine is None:
                engine = init_pipeline_db()
            else:
                init_pipeline_db(engine)
            self._owns_session = True
            self._real_session = Session(engine)

        self.session = ReadOnlySession(self._real_session)

    def _build_runtime_ctx(
        self,
        step_name: str | None = None,
        tool_name: str | None = None,
    ) -> "PipelineContext":
        """Build a PipelineContext from current pipeline state."""
        from llm_pipeline.runtime import PipelineContext as _Ctx

        return _Ctx(
            session=self._real_session,
            logger=logger,
            run_id=self.run_id,
            step_name=step_name,
            tool_name=tool_name,
        )


    @property
    def instructions(self) -> MappingProxyType:
        """Read-only access to LLM step instructions."""
        return MappingProxyType(self._instructions)

    @property
    def context(self) -> Dict[str, Any]:
        """Read-write access to derived context values."""
        return self._context

    @property
    def validated_input(self) -> Any:
        """Validated input data from execute(input_data=...). Returns PipelineInputData instance if INPUT_DATA declared, raw dict otherwise, None if not provided."""
        return self._validated_input

    @property
    def pipeline_name(self) -> str:
        """Auto-derived pipeline name from class name (CamelCase -> snake_case, remove Pipeline)."""
        class_name = self.__class__.__name__
        if not class_name.endswith("Pipeline"):
            raise ValueError(
                f"Pipeline class '{class_name}' must end with 'Pipeline' suffix."
            )
        return to_snake_case(class_name, strip_suffix="Pipeline")

    def _build_execution_order(self) -> None:
        all_steps = []
        for strategy in self._strategies:
            for bind in strategy.get_bindings():
                step_def = self._compile_bind_to_step_def(bind)
                step_class = step_def.step_class
                if step_class not in [s.step_class for s in all_steps]:
                    all_steps.append(step_def)

        for position, step_def in enumerate(all_steps):
            step_class = step_def.step_class
            self._step_order[step_class] = position
            for ext_bind in step_def.extraction_binds:
                model = ext_bind.extraction.MODEL
                self._model_extraction_step[model] = step_class
            if step_def.transformation:
                self._step_data_transformations[step_class] = step_class

    def _compile_bind_to_step_def(self, bind: Bind):
        """Compile a declarative Bind into an internal StepDefinition.

        Uses the step's decorator-generated ``create_definition`` to fill in
        prompt keys, agent, model, review, evaluators. Splices in the Bind's
        inputs SourcesSpec and nested extraction Binds.

        ``consensus_strategy`` resolution order: ``Bind.consensus_strategy``
        overrides ``step.CONSENSUS_STRATEGY`` (decorator default). Either
        can be None; None everywhere means no consensus.
        """
        resolved_consensus = (
            bind.consensus_strategy
            if bind.consensus_strategy is not None
            else getattr(bind.step, "CONSENSUS_STRATEGY", None)
        )
        # Tool binds: strategy-level overrides step defaults.
        # If the Bind has explicit tools, use those; otherwise fall back
        # to the step's DEFAULT_TOOLS (converted to tool Binds with no
        # adapter — tool inputs resolved from step inputs at runtime).
        if bind.tools:
            tool_binds = list(bind.tools)
        else:
            default_tools = getattr(bind.step, "DEFAULT_TOOLS", [])
            tool_binds = []
            for t in default_tools:
                # Default tool binds: empty .sources() so adapter resolves
                # with no external wiring (all fields from resources or defaults)
                tool_inputs_cls = t.Inputs
                if tool_inputs_cls.model_fields:
                    non_resource = {
                        k for k in tool_inputs_cls.model_fields
                        if k not in tool_inputs_cls._resource_specs
                    }
                    if non_resource:
                        # Tool has non-resource fields; strategy must bind them.
                        # Skip for now — strategy-level binds handle this case.
                        continue
                    # All fields are resources — empty sources is valid
                    tool_binds.append(
                        Bind(tool=t, inputs=tool_inputs_cls.sources())
                    )
                else:
                    # No fields at all — provide a trivial SourcesSpec
                    tool_binds.append(
                        Bind(tool=t, inputs=tool_inputs_cls.sources())
                    )

        create_kwargs = {
            "inputs_spec": bind.inputs,
            "extraction_binds": list(bind.extractions),
            "tool_binds": tool_binds,
        }
        if resolved_consensus is not None:
            create_kwargs["consensus_strategy"] = resolved_consensus
        return bind.step.create_definition(**create_kwargs)

    def _get_foreign_key_dependencies(self, model: Type[SQLModel]) -> List[Type[SQLModel]]:
        dependencies = []
        if not hasattr(model, "__table__"):
            return dependencies
        for column in model.__table__.columns:
            if column.foreign_keys:
                for fk in column.foreign_keys:
                    target_table_name = fk.column.table.name
                    for potential_model in self.REGISTRY.MODELS:
                        if (
                            hasattr(potential_model, "__tablename__")
                            and potential_model.__tablename__ == target_table_name
                        ):
                            dependencies.append(potential_model)
                            break
        return dependencies

    # ------------------------------------------------------------------
    # Step dependency graph
    #
    # A unified graph of step-class -> set of step classes it depends on.
    # Aggregates two sources of edges:
    #
    #   1. Extraction FK edges. A step extracting Model M, where M has an
    #      FK column targeting Model T, depends on whichever step extracts
    #      T (looked up via ``_model_extraction_step``).
    #
    #   2. FromOutput edges. A step / extraction / tool whose
    #      ``inputs_spec`` contains a ``FromOutput(OtherStep)`` source
    #      depends on ``OtherStep``.
    #
    # Both edge kinds collapse into the same step-level dependency. The
    # validator (``_validate_step_dependency_graph``) asserts the union
    # graph is acyclic, contains no references to absent steps, and that
    # the user's positional binding order is a valid topological sort.
    #
    # This subsumes the older split between FK validation and registry-
    # order validation: same coverage, single graph, single error path.
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_from_output_step_classes(
        spec: "SourcesSpec | None",
    ) -> Iterator[Type]:
        """Yield every ``FromOutput.step_cls`` referenced by a SourcesSpec.

        Recurses into ``Computed`` sources (which themselves wrap
        zero-or-more child sources). ``FromInput`` and ``FromPipeline``
        produce no step-level dependencies and are skipped.
        """
        from llm_pipeline.wiring import (
            Computed,
            FromOutput,
            SourcesSpec,
        )

        if spec is None:
            return
        if not isinstance(spec, SourcesSpec):
            return

        def _walk(source: Any) -> Iterator[Type]:
            if isinstance(source, FromOutput):
                yield source.step_cls
            elif isinstance(source, Computed):
                for child in source.sources:
                    yield from _walk(child)

        for src in spec.field_sources.values():
            yield from _walk(src)

    def _build_step_dependency_graph(self) -> None:
        """Populate ``_step_deps`` and ``_step_dep_reasons`` from all
        sources of step-level dependencies declared in the pipeline.

        Runs after ``_build_execution_order`` (which populates
        ``_step_order`` and ``_model_extraction_step``).
        """
        from llm_pipeline.wiring import Bind

        def _record(
            dependent: Type, dep: Type, reason: str,
        ) -> None:
            if dep is dependent:
                return
            self._step_deps.setdefault(dependent, set()).add(dep)
            self._step_dep_reasons.setdefault(
                (dependent, dep), [],
            ).append(reason)

        # Walk every binding once, in registration order.
        for strategy in self._strategies:
            for bind in strategy.get_bindings():
                step_def = self._compile_bind_to_step_def(bind)
                step_class = step_def.step_class

                # 1a. Step-level inputs_spec FromOutput edges
                for dep in self._iter_from_output_step_classes(step_def.inputs_spec):
                    _record(
                        step_class, dep,
                        f"FromOutput({dep.__name__}) in {step_class.__name__}.inputs",
                    )

                # 1b. Extraction-level inputs_spec FromOutput edges
                for ext_bind in step_def.extraction_binds:
                    if not isinstance(ext_bind, Bind):
                        continue
                    ext_name = (
                        ext_bind.extraction.__name__
                        if ext_bind.extraction is not None
                        else "<extraction>"
                    )
                    for dep in self._iter_from_output_step_classes(ext_bind.inputs):
                        _record(
                            step_class, dep,
                            f"FromOutput({dep.__name__}) in "
                            f"{step_class.__name__}.extractions[{ext_name}].inputs",
                        )

                # 1c. Tool-level inputs_spec FromOutput edges
                for tool_bind in step_def.tool_binds:
                    if not isinstance(tool_bind, Bind):
                        continue
                    tool_name = (
                        tool_bind.tool.__name__
                        if tool_bind.tool is not None
                        else "<tool>"
                    )
                    for dep in self._iter_from_output_step_classes(tool_bind.inputs):
                        _record(
                            step_class, dep,
                            f"FromOutput({dep.__name__}) in "
                            f"{step_class.__name__}.tools[{tool_name}].inputs",
                        )

                # 2. Extraction FK edges. For each extracted model on
                # this step, follow its FK columns; each FK target's
                # extracting step (if any) is a dependency.
                for ext_bind in step_def.extraction_binds:
                    if not isinstance(ext_bind, Bind) or ext_bind.extraction is None:
                        continue
                    ext_model = getattr(ext_bind.extraction, "MODEL", None)
                    if ext_model is None:
                        continue
                    for fk_target in self._get_foreign_key_dependencies(ext_model):
                        dep_step = self._model_extraction_step.get(fk_target)
                        if dep_step is None:
                            continue
                        _record(
                            step_class, dep_step,
                            f"FK on {ext_model.__name__} -> "
                            f"{fk_target.__name__} (extracted by "
                            f"{dep_step.__name__})",
                        )

    def _validate_step_dependency_graph(self) -> None:
        """Assert the step dependency graph is well-formed.

        Three checks:

        1. Every referenced step class is present in the pipeline (no
           dangling ``FromOutput`` targets).
        2. The graph is acyclic (no ``A -> B -> A`` chains).
        3. The user's positional binding order is a valid topological
           sort: every dependency appears at a lower position than
           the step that depends on it.
        """
        # 1. Referenced step classes are present.
        for dependent, deps in self._step_deps.items():
            for dep in deps:
                if dep not in self._step_order:
                    reasons = self._step_dep_reasons.get((dependent, dep), [])
                    reason_text = (
                        f" (declared via {reasons[0]})" if reasons else ""
                    )
                    raise ValueError(
                        f"Step '{dependent.__name__}' depends on "
                        f"'{dep.__name__}', but '{dep.__name__}' is not "
                        f"present in any strategy's bindings"
                        f"{reason_text}."
                    )

        # 2. Acyclic (DFS with recursion stack).
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[Type, int] = {s: WHITE for s in self._step_order}
        stack_path: List[Type] = []

        def _dfs(node: Type) -> None:
            color[node] = GRAY
            stack_path.append(node)
            for dep in self._step_deps.get(node, ()):
                if color.get(dep) == GRAY:
                    cycle_start = stack_path.index(dep)
                    cycle = stack_path[cycle_start:] + [dep]
                    cycle_repr = " -> ".join(c.__name__ for c in cycle)
                    raise ValueError(
                        f"Step dependency cycle: {cycle_repr}. "
                        f"Cannot determine execution order."
                    )
                if color.get(dep) == WHITE:
                    _dfs(dep)
            stack_path.pop()
            color[node] = BLACK

        for node in self._step_order:
            if color[node] == WHITE:
                _dfs(node)

        # 3. Positional order respects every edge.
        for dependent, deps in self._step_deps.items():
            dependent_pos = self._step_order[dependent]
            for dep in deps:
                dep_pos = self._step_order[dep]
                if dep_pos > dependent_pos:
                    reasons = self._step_dep_reasons.get((dependent, dep), [])
                    reason_text = (
                        "\n  Reasons: " + "; ".join(reasons)
                        if reasons else ""
                    )
                    raise ValueError(
                        f"Step '{dependent.__name__}' at position "
                        f"{dependent_pos} depends on '{dep.__name__}' "
                        f"at position {dep_pos}. Reorder so "
                        f"'{dep.__name__}' precedes "
                        f"'{dependent.__name__}'.{reason_text}"
                    )

    def _validate_step_access(
        self, step_class: Type, resource_type: str, model_class: Type[SQLModel] = None
    ) -> None:
        if step_class in self._executed_steps:
            return
        if step_class == self._current_step and model_class is not None:
            if model_class in self.extractions:
                return
            current_extraction_name = (
                self._current_extraction.__name__ if self._current_extraction else "Unknown"
            )
            raise ValueError(
                f"Extraction ordering error within {step_class.__name__}:\n"
                f"  {current_extraction_name} attempts to access '{model_class.__name__}' "
                f"before it's extracted."
            )
        if self._current_step is None:
            raise ValueError(
                f"Cannot access {resource_type} from {step_class.__name__} - not executed yet."
            )
        current_position = self._step_order[self._current_step]
        target_position = self._step_order[step_class]
        accessor = self._current_step.__name__
        if self._current_extraction:
            accessor = f"{self._current_extraction.__name__} (in {self._current_step.__name__})"
        raise ValueError(
            f"Step execution order error:\n"
            f"  {accessor} (step {current_position}) attempts to access "
            f"{resource_type} from {step_class.__name__} (step {target_position}).\n"
            f"Steps can only access {resource_type} from previously executed steps."
        )

    def sanitize(self, data: Any) -> str:
        """Override for custom sanitization. Default: str(data)."""
        if isinstance(data, str):
            return data
        return str(data)

    def get_raw_data(self) -> Any:
        return self.data.get("raw")

    def get_current_data(self) -> Any:
        if not self.data:
            return None
        for k in reversed(list(self.data.keys())):
            if k not in ("raw", "sanitized"):
                return self.data[k]
        return self.data.get("raw")

    def get_sanitized_data(self) -> Any:
        return self.data.get("sanitized")

    def get_data(self, key: str = "current") -> Any:
        if key == "current":
            return self.get_current_data()
        elif key == "raw":
            return self.get_raw_data()
        elif key == "sanitized":
            return self.get_sanitized_data()
        if isinstance(key, type) and key in self._step_order:
            self._validate_step_access(key, "data")
        return self.data.get(key)

    def get_instructions(self, key) -> Any:
        if isinstance(key, type) and key in self._step_order:
            self._validate_step_access(key, "instructions")
        return self._instructions.get(key)

    def set_data(self, data: Any, step_name: str) -> None:
        self.data[step_name] = data
        self.data["sanitized"] = self.sanitize(data)

    def execute_from_step(
        self,
        resume_step_index: int,
        review_notes: Optional[str] = None,
        review_decision: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> "PipelineConfig":
        """Resume pipeline execution from a specific step index.

        Hydrates context and instructions from persisted PipelineStepState
        rows, then continues the normal step loop from resume_step_index.
        """
        from sqlmodel import select
        from llm_pipeline.state import PipelineStepState

        # Reconstruct state from persisted step states
        states = self._real_session.exec(
            select(PipelineStepState)
            .where(PipelineStepState.run_id == self.run_id)
            .order_by(PipelineStepState.step_number)
        ).all()

        # For minor revision, capture original output before hydrating
        original_output = ""
        for state in states:
            if state.step_number <= resume_step_index:
                if state.context_snapshot:
                    self._context.update(state.context_snapshot)
                if state.result_data:
                    self._instructions[state.step_name] = state.result_data
            # Grab the reviewed step's output for minor revision prompt
            if state.step_number == resume_step_index + 1 and state.result_data:
                import json as _json
                original_output = _json.dumps(state.result_data, default=str, indent=2) if state.result_data else ""

        # Set review context for prompt injection (cleared after step runs)
        if review_notes and review_decision:
            self._context["_review_context"] = {
                "decision": review_decision,
                "notes": review_notes,
                "original_output": original_output,
            }

        # Set resume point and delegate to execute()
        self._resume_from_step = resume_step_index
        return self.execute(
            data=None,
            initial_context=dict(self._context),
            input_data=input_data,
            use_cache=False,
        )

    def execute(
        self,
        data: Any = None,
        initial_context: Optional[Dict[str, Any]] = None,
        input_data: Optional[Dict[str, Any]] = None,
        use_cache: bool = False,
    ) -> "PipelineConfig":
        """Execute pipeline steps with optional caching and per-step consensus."""
        if initial_context is None:
            initial_context = {}

        from llm_pipeline.agent_builders import build_step_agent, StepDeps
        from llm_pipeline.prompts.service import PromptService
        from llm_pipeline.state import PipelineRun
        from llm_pipeline.validators import not_found_validator, array_length_validator
        from pydantic_ai import UnexpectedModelBehavior

        if not self._strategies:
            raise ValueError("No strategies registered in pipeline")

        # Create prompt service from pipeline session
        prompt_service = PromptService(self._real_session)

        # Validate input_data against INPUT_DATA schema if declared
        cls = self.__class__
        self._validated_input = None
        if cls.INPUT_DATA is not None:
            if input_data is None or not input_data:
                raise ValueError(
                    f"Pipeline '{self.pipeline_name}' requires input_data "
                    f"matching {cls.INPUT_DATA.__name__} schema but none provided"
                )
            try:
                self._validated_input = cls.INPUT_DATA.model_validate(input_data)
            except ValidationError as e:
                raise ValueError(
                    f"Pipeline '{self.pipeline_name}' input_data validation failed: {e}"
                ) from e
        elif input_data is not None:
            self._validated_input = input_data

        self._context = initial_context.copy()
        self.data = {"raw": data, "sanitized": self.sanitize(data)}
        self.extractions = {}

        # AdapterContext accumulates step outputs as the loop runs. It is
        # passed to each step's inputs adapter (before prepare_calls) and
        # to each extraction's inputs adapter (during extract_data).
        adapter_ctx = AdapterContext(
            input=self._validated_input,
            outputs={},
            pipeline=self,
        )

        start_time = datetime.now(timezone.utc)
        current_step_name: str | None = None

        from sqlmodel import select as _sel
        existing_run = self._real_session.exec(
            _sel(PipelineRun).where(PipelineRun.run_id == self.run_id)
        ).first()
        if existing_run:
            existing_run.status = "running"
            existing_run.started_at = start_time
            pipeline_run = existing_run
        else:
            pipeline_run = PipelineRun(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
                status="running",
                started_at=start_time,
            )
            self._real_session.add(pipeline_run)
        self._real_session.flush()

        # Open the Langfuse root trace span around the entire execute() body.
        # Manual __enter__/__exit__ instead of `with` so the existing
        # try/except (~540 lines) doesn't need re-indentation. The
        # observer's pipeline_run is no-op when Langfuse is unconfigured;
        # __enter__ + __exit__ are then trivial. Step and extraction spans
        # opened later auto-nest via OTEL context propagation.
        _observer_input = (
            self._validated_input.model_dump()
            if self._validated_input is not None
            and hasattr(self._validated_input, "model_dump")
            else self._validated_input
        )

        # Resume case: re-attach to the original run's root span via
        # the persisted OTEL trace_id / span_id so resumed step spans
        # nest under the original trace tree (one trace per run).
        _resume_from = getattr(self, '_resume_from_step', 0)
        _is_resume = _resume_from > 0
        _parent_trace_id = pipeline_run.trace_id if _is_resume else None
        _parent_span_id = pipeline_run.span_id if _is_resume else None

        _root_cm = self._observer.pipeline_run(
            input_data=_observer_input,
            tags=[self.pipeline_name],
            parent_trace_id=_parent_trace_id,
            parent_span_id=_parent_span_id,
        )
        _root_cm.__enter__()

        # First-execution path: capture the OTEL trace_id + root span_id
        # NOW that the root span is open, so a future resume can re-
        # attach. No-op when Langfuse is unconfigured (current span is
        # invalid).
        if not _is_resume and pipeline_run.trace_id is None:
            try:
                from opentelemetry import trace as _otel_trace
                _cur = _otel_trace.get_current_span()
                _ctx = _cur.get_span_context() if _cur else None
                if _ctx is not None and _ctx.is_valid:
                    pipeline_run.trace_id = format(_ctx.trace_id, "032x")
                    pipeline_run.span_id = format(_ctx.span_id, "016x")
                    self._real_session.add(pipeline_run)
                    self._real_session.flush()
            except Exception:
                logger.debug(
                    "Failed to capture OTEL root span IDs for run_id=%s",
                    self.run_id, exc_info=True,
                )

        # Resume case: emit a backdated span for the just-completed
        # review so the trace shows the wait window with decision/notes,
        # not an unexplained gap. Must happen after _root_cm.__enter__()
        # so OTEL context is attached.
        if _is_resume:
            self._emit_review_span_for_resume()

        # Tracks the open observer step span (if any) so the outer
        # except handler can close it on exception. Initialized before
        # the try so it's always defined even if max_steps computation
        # raises immediately.
        _step_cm = None

        try:
            max_steps = max(len(s.get_bindings()) for s in self._strategies)

            for step_index in range(max_steps):
                # Skip steps before resume point (already executed) but
                # rehydrate adapter_ctx.outputs so downstream
                # FromOutput(...) sources can resolve. Without this,
                # resume crashes the first time a later step reads a
                # prior step's output.
                if step_index < _resume_from:
                    self._rehydrate_resumed_step_output(
                        step_index, adapter_ctx,
                    )
                    continue

                step_num = step_index + 1
                selected_strategy = None
                step_def = None

                for strategy in self._strategies:
                    if strategy.can_handle(self.context):
                        bindings = strategy.get_bindings()
                        if step_index < len(bindings):
                            selected_strategy = strategy
                            step_def = self._compile_bind_to_step_def(
                                bindings[step_index]
                            )
                            break

                if not step_def:
                    break

                self._current_strategy = selected_strategy
                step = step_def.create_step(pipeline=self)
                step_class = type(step)
                self._current_step = step_class
                current_step_name = step.step_name

                # Open the observer's step span. Manual __enter__/__exit__
                # so the existing per-iteration body (~450 lines) doesn't
                # need re-indentation. ``_step_cm`` is tracked locally so
                # the outer except can close it on exception. Pydantic-ai
                # LLM-call generations spawned inside auto-nest under
                # this span via OTEL context propagation.
                _step_cm = self._observer.step(
                    step_name=step.step_name,
                    step_number=step_num,
                    instructions_class=(
                        step.instructions.__name__
                        if step.instructions is not None else None
                    ),
                )
                _step_cm.__enter__()

                # Resolve the step's inputs adapter now that the step instance
                # exists and is bound to this pipeline. Populated before the
                # first prepare_calls() read.
                if step_def.inputs_spec is not None:
                    step.inputs = step_def.inputs_spec.resolve(adapter_ctx)
                    # Second pass: build any resource-typed fields from the
                    # now-populated non-resource fields.
                    from llm_pipeline.resources import resolve_resources
                    resolve_resources(
                        step.inputs,
                        self._build_runtime_ctx(step_name=step.step_name),
                    )

                if step.should_skip():
                    logger.info(f"\nSTEP {step_num}: {step.step_name} SKIPPED")
                    self._observer.step_skipped(
                        reason="should_skip returned True",
                    )
                    self._executed_steps.add(step_class)
                    _step_cm.__exit__(None, None, None)
                    _step_cm = None
                    continue

                logger.info(f"\nSTEP {step_num}: {step.step_name}...")
                if selected_strategy:
                    logger.info(f"  -> Strategy: {selected_strategy.display_name}")
                    logger.info(
                        f"  -> Prompts: system={step.system_instruction_key}, "
                        f"user={step.user_prompt_key}"
                    )

                current_data = self.get_current_data()
                sanitized_data = self.get_sanitized_data()
                if current_data is not None:
                    try:
                        logger.info(f"  -> Data preview:\n{current_data.to_string()}")
                        logger.info(f"  -> Sanitized preview:\n{sanitized_data}")
                    except AttributeError:
                        pass  # Not a DataFrame

                step_start = datetime.now(timezone.utc)
                input_hash = self._hash_step_inputs(step, step_num)

                cached_state = None
                if use_cache:
                    self._observer.cache_lookup(input_hash=input_hash)
                    cached_state = self._find_cached_state(step, input_hash)

                if cached_state:
                    self._observer.cache_hit(input_hash=input_hash)
                    logger.info(
                        f"  [CACHED] Using result from "
                        f"{cached_state.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    instructions = self._load_from_cache(cached_state, step)
                    self._instructions[step.step_name] = instructions
                    adapter_ctx.outputs[step_class] = instructions

                    if hasattr(step, "_transformation") and step._transformation:
                        transformation = step._transformation(self)
                        transform_start = datetime.now(timezone.utc)
                        current_data = self.get_data("current")
                        transformed_data = transformation.transform(current_data, instructions)
                        self.set_data(transformed_data, step_name=step.step_name)
                    step.log_instructions(instructions)
                    reconstructed_count = self._reconstruct_extractions_from_cache(
                        cached_state, step_def
                    )
                    if step_def.extraction_binds:
                        self._observer.cache_reconstructed(input_hash=input_hash)
                    if reconstructed_count == 0 and step_def.extraction_binds:
                        logger.info("  [PARTIAL CACHE] Re-running extraction")
                        step.extract_data(adapter_ctx)
                else:
                    if use_cache:
                        self._observer.cache_miss(input_hash=input_hash)
                        logger.info("  [FRESH] No cache found, running fresh")
                    if step_def.consensus_strategy is not None:
                        logger.info(
                            f"  [CONSENSUS] strategy={step_def.consensus_strategy.name}, "
                            f"max_attempts={step_def.consensus_strategy.max_attempts}"
                        )

                    call_params = step.prepare_calls()
                    instructions = []

                    # Build agent once per step (reused across consensus iterations)
                    from llm_pipeline.agent_registry import get_agent_tools
                    instructions_type = step.instructions

                    # Collect tools: new PipelineTool binds + legacy agent registry
                    agent_name = getattr(step, '_agent_name', None)
                    step_tools = list(get_agent_tools(agent_name) if agent_name else [])

                    # Resolve PipelineTool binds (new system)
                    _tool_binds = getattr(step, '_tool_binds', [])
                    if _tool_binds:
                        from llm_pipeline.tool import resolve_tool_binds
                        pipeline_tool_fns = resolve_tool_binds(
                            _tool_binds,
                            adapter_ctx,
                            self._build_runtime_ctx(step_name=step.step_name),
                        )
                        step_tools.extend(pipeline_tool_fns)

                    step_model = self._resolve_step_model(step)
                    step_usage_limits = self._resolve_step_usage_limits(step)

                    # Build validators: always register both, they adapt per-call via ctx.deps
                    step_validators = [
                        not_found_validator(step_def.not_found_indicators),
                        array_length_validator(),
                    ]

                    agent = build_step_agent(
                        step_name=step.step_name,
                        output_type=instructions_type,
                        validators=step_validators,
                        instrument=self._instrumentation_settings,
                        tools=step_tools,
                        system_instruction_key=step.system_instruction_key,
                    )

                    for idx, params in enumerate(call_params):
                        # Per-call token vars (populated in non-consensus path)

                        # Rebuild StepDeps per-call so per-call params flow correctly
                        step_deps = StepDeps(
                            session=self.session,
                            pipeline_context=self._context,
                            prompt_service=prompt_service,
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            variable_resolver=self._variable_resolver,
                            array_validation=params.get("array_validation"),
                            validation_context=params.get("validation_context"),
                        )

                        user_prompt = step.build_user_prompt(
                            variables=params.get("variables", {}),
                            prompt_service=prompt_service,
                        )

                        # Auto-inject review feedback into prompt
                        review_ctx = self._context.get("_review_context")
                        if review_ctx and isinstance(review_ctx, dict):
                            user_prompt = _append_review_to_prompt(
                                user_prompt, review_ctx,
                            )

                        # Resolve system prompt for LLMCallStarting event
                        if step_def.consensus_strategy is not None:
                            instruction = self._execute_with_consensus(
                                agent, user_prompt, step_deps, instructions_type,
                                strategy=step_def.consensus_strategy,
                                current_step_name=current_step_name,
                                step_model=step_model,
                                step_usage_limits=step_usage_limits,
                            )
                        else:
                            run_result = None
                            try:
                                run_kwargs = dict(
                                    deps=step_deps,
                                    model=step_model,
                                )
                                if step_usage_limits is not None:
                                    run_kwargs["usage_limits"] = step_usage_limits
                                run_result = agent.run_sync(
                                    user_prompt,
                                    **run_kwargs,
                                )
                                instruction = run_result.output
                            except UnexpectedModelBehavior as exc:
                                instruction = instructions_type.create_failure(str(exc))
                        instructions.append(instruction)

                    self._instructions[step.step_name] = instructions
                    adapter_ctx.outputs[step_class] = instructions

                    if hasattr(step, "_transformation") and step._transformation:
                        transformation = step._transformation(self)
                        transform_start = datetime.now(timezone.utc)
                        current_data = self.get_data("current")
                        transformed_data = transformation.transform(current_data, instructions)
                        self.set_data(transformed_data, step_name=step.step_name)
                    step.extract_data(adapter_ctx)
                    execution_time_ms = int(
                        (datetime.now(timezone.utc) - step_start).total_seconds() * 1000
                    )
                    self._save_step_state(
                        step, step_num, instructions, input_hash, execution_time_ms, step_model,
                    )
                    step.log_instructions(instructions)
                self._executed_steps.add(step_class)

                # Clear review context after step runs (don't leak to subsequent steps)
                self._context.pop("_review_context", None)

                if step_def.action_after:
                    action_method = getattr(self, f"_{step_def.action_after}", None)
                    if action_method and callable(action_method):
                        action_method(self.context)

                # Review gate: pause if step has review configured
                if step_def.review is not None:
                    review_cls = step_def.review
                    review_config = review_cls() if isinstance(review_cls, type) else review_cls
                    should_review = review_config.enabled
                    if should_review and review_config.condition is not None:
                        should_review = review_config.condition(self._context, instructions)
                    if should_review:
                        review_data = step.prepare_review(instructions)
                        self._pause_for_review(
                            pipeline_run, step, step_num, review_config, review_data,
                        )
                        # Close step + root spans before the early
                        # return — pause-for-review counts as a
                        # successful span closure (the run will resume
                        # later as a new trace).
                        _step_cm.__exit__(None, None, None)
                        _step_cm = None
                        _root_cm.__exit__(None, None, None)
                        return self

                # Normal end-of-iteration: close the step span before
                # falling through to the next loop iteration.
                _step_cm.__exit__(None, None, None)
                _step_cm = None

            pipeline_execution_time_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            pipeline_run.status = "completed"
            pipeline_run.completed_at = datetime.now(timezone.utc)
            pipeline_run.step_count = len(self._executed_steps)
            pipeline_run.total_time_ms = int(pipeline_execution_time_ms)
            self._real_session.add(pipeline_run)
            self._real_session.flush()

            self._current_step = None
            # Close the observer's root span on the success path.
            _root_cm.__exit__(None, None, None)
            return self

        except Exception as e:
            if pipeline_run:
                pipeline_run.status = "failed"
                pipeline_run.completed_at = datetime.now(timezone.utc)
                self._real_session.add(pipeline_run)
                self._real_session.flush()

            self._current_step = None
            # Close any open step span first (innermost-to-outermost),
            # then close the root span. Both marked ERROR so Langfuse
            # surfaces them as failed.
            if _step_cm is not None:
                _step_cm.__exit__(type(e), e, e.__traceback__)
            _root_cm.__exit__(type(e), e, e.__traceback__)
            raise

    def clear_cache(self) -> int:
        from llm_pipeline.state import PipelineStepState
        from sqlmodel import select

        states = self.session.exec(
            select(PipelineStepState).where(
                PipelineStepState.run_id == self.run_id
            )
        ).all()
        count = len(states)
        for state in states:
            self.session.delete(state)
        self.session.commit()
        logger.info(f"[OK] Cleared {count} cached step(s) for run {self.run_id}")
        return count

    def store_extractions(self, model_class: Type[SQLModel], instances: List[SQLModel]) -> None:
        if model_class not in self.extractions:
            self.extractions[model_class] = []
        self.extractions[model_class].extend(instances)

    def get_extractions(self, model_class: Type[TModel]) -> List[TModel]:
        if model_class not in self.REGISTRY.get_models():
            raise ValueError(
                f"{model_class.__name__} is not in {self.REGISTRY.__name__}."
            )
        if model_class in self._model_extraction_step:
            extraction_step = self._model_extraction_step[model_class]
            self._validate_step_access(
                extraction_step, f"model '{model_class.__name__}'", model_class
            )
        return self.extractions.get(model_class, [])

    def _resolve_step_model(self, step) -> str:
        """Resolve model for a step via the shared resolver.

        Delegates to ``llm_pipeline.model.resolver.resolve_model_with_fallbacks``
        using a ``StepDefinition``-shaped shim over the step instance. The
        step instance exposes ``step_name`` directly but stores the tier-1
        model on ``_step_model`` (populated by ``PipelineStrategy.create_step``),
        so we wrap it in a minimal shim that matches the resolver's
        expected shape.
        """
        from llm_pipeline.model.resolver import resolve_model_with_fallbacks

        class _StepDefShim:
            step_name = step.step_name
            model = getattr(step, "_step_model", None)

        model, _source = resolve_model_with_fallbacks(
            _StepDefShim(),
            self._real_session,
            self.pipeline_name,
            self._model,
        )
        return model

    def _resolve_step_usage_limits(self, step):
        """Resolve usage limits for a step from DB config."""
        from sqlmodel import select
        from llm_pipeline.db.step_config import StepModelConfig
        from pydantic_ai.usage import UsageLimits
        config = self._real_session.exec(
            select(StepModelConfig).where(
                StepModelConfig.pipeline_name == self.pipeline_name,
                StepModelConfig.step_name == step.step_name,
            )
        ).first()
        if config and config.request_limit is not None:
            return UsageLimits(request_limit=config.request_limit)
        return None

    def _emit_review_span_for_resume(self) -> None:
        """Emit a backdated review span for the just-completed review.

        Looks up the most recently completed ``PipelineReview`` for
        this run and asks the observer to emit a span covering the
        wait window (``created_at`` -> ``completed_at``). The span
        nests under the original root via the OTEL parent context
        attached by ``pipeline_run`` on resume.

        Silent no-op when no completed review record exists (defensive
        — every resume is triggered by a review submission so a record
        should always be present).
        """
        from datetime import datetime as _dt, timezone as _tz
        from sqlmodel import select as _sel
        from llm_pipeline.state import PipelineReview

        try:
            review = self._real_session.exec(
                _sel(PipelineReview)
                .where(PipelineReview.run_id == self.run_id)
                .where(PipelineReview.status == "completed")
                .order_by(PipelineReview.completed_at.desc())
            ).first()
        except Exception:
            logger.debug(
                "Failed to fetch PipelineReview for run_id=%s",
                self.run_id, exc_info=True,
            )
            return
        if review is None:
            return

        end_time = review.completed_at or _dt.now(_tz.utc)
        try:
            self._observer.review(
                step_name=review.step_name,
                start_time=review.created_at,
                end_time=end_time,
                decision=review.decision,
                notes=review.notes,
                user_id=review.user_id,
                review_data=review.review_data,
                token=review.token,
            )
        except Exception:
            logger.debug(
                "Failed to emit review span for run_id=%s token=%s",
                self.run_id, review.token, exc_info=True,
            )

    def _hash_step_inputs(self, step, step_number: int) -> str:
        try:
            calls = step.prepare_calls()
            input_data = json.dumps(calls, sort_keys=True, default=str)
        except Exception:
            input_data = json.dumps(dict(sorted(self.context.items())), default=str)
        return hashlib.sha256(input_data.encode()).hexdigest()[:16]

    def _find_cached_state(self, step, input_hash: str):
        from llm_pipeline.state import PipelineStepState
        from llm_pipeline.db.prompt import Prompt
        from sqlmodel import select

        prompt_system_key = getattr(step, "system_instruction_key", None)
        current_prompt_version = None
        if prompt_system_key:
            prompt = self.session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == prompt_system_key,
                    Prompt.is_active == True,  # noqa: E712
                    Prompt.is_latest == True,  # noqa: E712
                )
            ).first()
            if prompt:
                current_prompt_version = prompt.version

        query = select(PipelineStepState).where(
            PipelineStepState.pipeline_name == self.pipeline_name,
            PipelineStepState.step_name == step.step_name,
            PipelineStepState.input_hash == input_hash,
        )
        if current_prompt_version:
            query = query.where(
                PipelineStepState.prompt_version == current_prompt_version
            )
        return self.session.exec(
            query.order_by(PipelineStepState.created_at.desc())
        ).first()

    def _rehydrate_resumed_step_output(
        self, step_index: int, adapter_ctx: "AdapterContext",
    ) -> None:
        """Rebuild ``adapter_ctx.outputs[step_class]`` for an already-run step.

        On resume, ``execute_from_step`` populates ``self._instructions``
        from persisted ``PipelineStepState.result_data`` (a list of dicts).
        Later steps' ``FromOutput(StepCls)`` sources read from
        ``adapter_ctx.outputs``, so we must materialize the prior step's
        output back into the adapter context here. Without this, the
        first step that reads a prior step's output raises
        ``KeyError: FromOutput: no outputs recorded for step X``.
        """
        selected_strategy = None
        step_def = None
        for strategy in self._strategies:
            if not strategy.can_handle(self.context):
                continue
            bindings = strategy.get_bindings()
            if step_index < len(bindings):
                selected_strategy = strategy
                step_def = self._compile_bind_to_step_def(bindings[step_index])
                break

        if step_def is None:
            return

        # Need a step instance to read INSTRUCTIONS class + step_name
        step = step_def.create_step(pipeline=self)
        step_class = type(step)
        instructions_class = getattr(step_class, "INSTRUCTIONS", None)

        raw = self._instructions.get(step.step_name)
        if not raw:
            return
        if not isinstance(raw, list):
            raw = [raw]

        rehydrated: List[Any] = []
        for item in raw:
            if (
                instructions_class is not None
                and isinstance(item, dict)
                and issubclass(instructions_class, BaseModel)
            ):
                rehydrated.append(instructions_class(**item))
            else:
                rehydrated.append(item)

        adapter_ctx.outputs[step_class] = rehydrated

    def _load_from_cache(self, cached_state, step) -> List[Any]:
        instructions_class = getattr(step, "INSTRUCTIONS", None)
        if not isinstance(cached_state.result_data, list):
            cached_state.result_data = [cached_state.result_data]
        instructions = []
        for instruction_dict in cached_state.result_data:
            if instructions_class and issubclass(instructions_class, BaseModel):
                instructions.append(instructions_class(**instruction_dict))
            else:
                instructions.append(instruction_dict)
        return instructions

    def _reconstruct_extractions_from_cache(self, cached_state, step_def) -> int:
        from llm_pipeline.state import PipelineRunInstance
        from sqlmodel import select

        cached_run_id = cached_state.run_id
        extraction_binds = getattr(step_def, "extraction_binds", [])
        if not extraction_binds:
            return 0

        logger.info(f"  -> Reconstructing extractions from cached run {cached_run_id[:8]}...")
        total = 0
        for ext_bind in extraction_binds:
            extraction_class = ext_bind.extraction
            model_class = extraction_class.MODEL
            run_instances = self.session.exec(
                select(PipelineRunInstance).where(
                    PipelineRunInstance.run_id == cached_run_id,
                    PipelineRunInstance.model_type == model_class.__name__,
                )
            ).all()
            instances = []
            for run_instance in run_instances:
                instance = self.session.get(model_class, run_instance.model_id)
                if instance:
                    instances.append(instance)
            if model_class not in self.extractions:
                self.extractions[model_class] = []
            self.extractions[model_class].extend(instances)
            total += len(instances)
            if instances:
                logger.info(
                    f"  -> Reconstructed {len(instances)} {model_class.__name__} instances"
                )
        return total

    def _save_step_state(self, step, step_number, instructions, input_hash, execution_time_ms=None, model_name=None):
        from llm_pipeline.state import PipelineStepState
        from llm_pipeline.db.prompt import Prompt
        from sqlmodel import select

        serialized = []
        for instruction in instructions:
            if hasattr(instruction, "model_dump"):
                serialized.append(instruction.model_dump(mode="json"))
            elif hasattr(instruction, "dict"):
                serialized.append(instruction.dict())
            elif hasattr(instruction, "__dict__"):
                serialized.append(vars(instruction))
            else:
                serialized.append({"result": str(instruction)})

        context_snapshot = dict(self._context)
        prompt_system_key = getattr(step, "system_instruction_key", None)
        prompt_user_key = getattr(step, "user_prompt_key", None)
        prompt_version = None
        if prompt_system_key:
            prompt = self.session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == prompt_system_key,
                    Prompt.is_active == True,  # noqa: E712
                    Prompt.is_latest == True,  # noqa: E712
                )
            ).first()
            if prompt:
                prompt_version = prompt.version

        state = PipelineStepState(
            pipeline_name=self.pipeline_name,
            run_id=self.run_id,
            step_name=step.step_name,
            step_number=step_number,
            input_hash=input_hash,
            result_data=serialized,
            context_snapshot=context_snapshot,
            prompt_system_key=prompt_system_key,
            prompt_user_key=prompt_user_key,
            prompt_version=prompt_version,
            execution_time_ms=execution_time_ms,
            model=model_name,
        )
        self._real_session.add(state)
        self._real_session.flush()
    def _pause_for_review(self, pipeline_run, step, step_number, review_config, review_data):
        """Pause pipeline execution for human review.

        Creates a PipelineReview record, updates run status to awaiting_review,
        emits ReviewRequested event, and optionally sends a webhook notification.
        The caller should return from execute() after this call.
        """
        import os as _os
        from llm_pipeline.state import PipelineReview

        token = str(uuid.uuid4())

        # Capture input_data for resume
        input_data = None
        if self._validated_input is not None:
            input_data = self._validated_input.model_dump(mode="json") if hasattr(self._validated_input, 'model_dump') else dict(self._validated_input)

        review_record = PipelineReview(
            token=token,
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            step_name=step.step_name,
            step_number=step_number,
            status="pending",
            review_data=review_data.model_dump(mode="json"),
            input_data=input_data,
        )
        self._real_session.add(review_record)

        pipeline_run.status = "awaiting_review"
        self._real_session.add(pipeline_run)
        self._real_session.commit()  # commit, not flush — releases DB lock for event flush

        # Webhook notification (fire-and-forget)
        webhook_url = (
            review_config.webhook_url
            or _os.environ.get("LLM_PIPELINE_REVIEW_WEBHOOK")
        )
        if webhook_url:
            self._send_review_webhook(webhook_url, token, step, review_data)

        self._awaiting_review = True

        logger.info(
            "Pipeline paused for review at step '%s' (run=%s, token=%s)",
            step.step_name, self.run_id, token,
        )

    def _send_review_webhook(self, url, token, step, review_data):
        """POST review notification to webhook URL."""
        import os as _os
        try:
            import httpx
            base_url = _os.environ.get("LLM_PIPELINE_BASE_URL", "http://localhost:8642")
            httpx.post(url, json={
                "event": "review_requested",
                "run_id": self.run_id,
                "pipeline_name": self.pipeline_name,
                "step_name": step.step_name,
                "token": token,
                "review_link": f"{base_url}/review/{token}",
                "callback_url": f"{base_url}/reviews/{token}",
                "callback_method": "POST",
                "callback_schema": {
                    "decision": "approved | minor_revision | major_revision | restart",
                    "notes": "string | null",
                    "resume_from": "string | null  (step name, only for major_revision)",
                },
                "review_data": review_data.model_dump(mode="json"),
            }, timeout=10)
        except ImportError:
            logger.warning("httpx not installed, skipping review webhook")
        except Exception:
            logger.warning("Failed to send review webhook to %s", url, exc_info=True)

    def save(
        self,
        session: Session = None,
        tables: Optional[List[Type[SQLModel]]] = None,
    ) -> Dict[str, int]:
        """Save extracted database instances to database."""
        session = session or self._real_session

        if not hasattr(self, "REGISTRY"):
            raise AttributeError(
                f"{self.__class__.__name__} must define REGISTRY class attribute."
            )

        models_to_save = tables if tables else self.REGISTRY.get_models()
        if tables:
            registry_models = self.REGISTRY.get_models()
            for model_class in tables:
                if model_class not in registry_models:
                    raise ValueError(
                        f"{model_class.__name__} is not in {self.REGISTRY.__name__}."
                    )

        for model_class in models_to_save:
            self.ensure_table(model_class, session)

        results = {}
        for model_class in models_to_save:
            instances = self.get_extractions(model_class)
            self._track_created_instances(model_class, instances, session)
            model_name = model_class.__name__
            results[f"{model_name.lower()}s_saved"] = len(instances)

        session.commit()
        return results

    def _track_created_instances(self, model_class, instances, session):
        from llm_pipeline.state import PipelineRunInstance

        for instance in instances:
            if hasattr(instance, "id") and instance.id:
                run_instance = PipelineRunInstance(
                    run_id=self.run_id,
                    model_type=model_class.__name__,
                    model_id=instance.id,
                )
                session.add(run_instance)

    def ensure_table(self, model_class: Type[SQLModel], session: Session) -> None:
        if model_class not in self.REGISTRY.get_models():
            raise ValueError(
                f"{model_class.__name__} is not in {self.REGISTRY.__name__}."
            )
        from sqlmodel import SQLModel as SM
        engine = session.get_bind()
        SM.metadata.create_all(engine, tables=[model_class.__table__])

    def _execute_with_consensus(
        self, agent, user_prompt, step_deps, instructions_type,
        strategy: 'ConsensusStrategy', current_step_name: str,
        step_model: str | None = None,
        step_usage_limits=None,
    ):
        """Execute LLM calls with consensus strategy, accumulating token usage.

        Returns:
            tuple of (result, total_input_tokens, total_output_tokens, total_requests)
            where token values are int | None (None when no usage data available).
        """
        from pydantic_ai import UnexpectedModelBehavior

        results = []
        result_groups = []

        for attempt in range(strategy.max_attempts):
            try:
                _consensus_kwargs = dict(deps=step_deps, model=step_model or self._model)
                if step_usage_limits is not None:
                    _consensus_kwargs["usage_limits"] = step_usage_limits
                run_result = agent.run_sync(user_prompt, **_consensus_kwargs)
                instruction = run_result.output
            except UnexpectedModelBehavior as exc:
                instruction = instructions_type.create_failure(str(exc))

            results.append(instruction)
            matched_group = None
            for group in result_groups:
                if instructions_match(instruction, group[0]):
                    group.append(instruction)
                    matched_group = group
                    break
            if matched_group is None:
                result_groups.append([instruction])
                matched_group = result_groups[-1]

            self._observer.consensus_attempt(
                attempt=attempt + 1,
                max_attempts=strategy.max_attempts,
                strategy=strategy.name,
            )
            if not strategy.should_continue(results, result_groups, attempt + 1, strategy.max_attempts):
                break

        consensus_result = strategy.select(results, result_groups)

        if consensus_result.consensus_reached:
            logger.info(
                f"  [CONSENSUS] {strategy.name}: reached after {consensus_result.total_attempts} attempts"
            )
            self._observer.consensus_reached(
                attempts_used=consensus_result.total_attempts,
                agreement=None,
            )
        else:
            logger.info(
                f"  [NO CONSENSUS] {strategy.name}: after {consensus_result.total_attempts} attempts"
            )
            largest_group = max(result_groups, key=len)
            self._observer.consensus_failed(
                attempts_used=consensus_result.total_attempts,
                reason=f"largest_group={len(largest_group)} below threshold={strategy.threshold}",
            )
        return consensus_result.result

    def close(self) -> None:
        """Close the database session if the pipeline owns it."""
        if self._owns_session and self._real_session:
            try:
                self._real_session.rollback()
            except Exception:
                pass
            self._real_session.close()
            self._real_session = None


__all__ = ["PipelineConfig"]
