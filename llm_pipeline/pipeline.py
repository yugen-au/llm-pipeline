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
    List,
    Optional,
    Type,
    TypeVar,
    TYPE_CHECKING,
)

from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session

from llm_pipeline.context import PipelineInputData
from llm_pipeline.consensus import instructions_match, ConsensusResult
from llm_pipeline.naming import to_snake_case

logger = logging.getLogger(__name__)

from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    CacheLookup, CacheHit, CacheMiss, CacheReconstruction,
    LLMCallPrepared, LLMCallStarting, LLMCallCompleted,
    ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed,
    TransformationStarting, TransformationCompleted,
    InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved,
)

if TYPE_CHECKING:
    from pydantic_ai import InstrumentationSettings
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.agent_registry import AgentRegistry
    from llm_pipeline.consensus import ConsensusStrategy
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.prompts.variables import VariableResolver
    from llm_pipeline.events.emitter import PipelineEventEmitter
    from llm_pipeline.events.types import PipelineEvent

TModel = TypeVar("TModel", bound=SQLModel)


def _calc_llm_cost(usage: object, model: str | None) -> tuple[float | None, float | None, float | None]:
    """Best-effort cost calculation via genai_prices. Returns (total, input, output) or (None,None,None)."""
    if not usage or not model:
        return None, None, None
    try:
        from genai_prices import calc_price
        price = calc_price(usage=usage, model_ref=model)
        return float(price.total_price), float(price.input_price), float(price.output_price)
    except Exception:
        return None, None, None


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
    AGENT_REGISTRY: ClassVar[Optional[Type["AgentRegistry"]]] = None
    INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None

    def __init_subclass__(cls, registry=None, strategies=None, agent_registry=None, **kwargs):
        super().__init_subclass__(**kwargs)

        if registry is not None or strategies is not None or agent_registry is not None:
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

            if agent_registry is not None:
                expected = f"{pipeline_name_prefix}AgentRegistry"
                if agent_registry.__name__ != expected:
                    raise ValueError(
                        f"AgentRegistry for {cls.__name__} must be named '{expected}', "
                        f"got '{agent_registry.__name__}'"
                    )

        if registry is not None:
            cls.REGISTRY = registry
        if strategies is not None:
            cls.STRATEGIES = strategies
        if agent_registry is not None:
            cls.AGENT_REGISTRY = agent_registry

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
        event_emitter: Optional["PipelineEventEmitter"] = None,
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
            event_emitter: Optional PipelineEventEmitter for lifecycle/LLM/extraction events. None disables events.
            instrumentation_settings: Optional pydantic-ai InstrumentationSettings for per-agent OTel instrumentation.
        """
        from llm_pipeline.db import init_pipeline_db, get_session as db_get_session
        from llm_pipeline.session import ReadOnlySession

        self._model = model
        self._variable_resolver = variable_resolver
        self._event_emitter = event_emitter
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

        self._build_execution_order()
        self._validate_foreign_key_dependencies()
        self._validate_registry_order()

        self.run_id = run_id or str(uuid.uuid4())

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

    def get_extra(self) -> dict[str, Any]:
        """Return extra deps to inject into StepDeps.extra.

        Subclasses override to supply domain-specific deps (e.g. workbook_context).
        """
        return {}

    def _emit(self, event: "PipelineEvent") -> None:
        """Forward event to emitter if configured.

        Args:
            event: PipelineEvent instance to emit.
        """
        if self._event_emitter is not None:
            self._event_emitter.emit(event)

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
            for step_def in strategy.get_steps():
                step_class = step_def.step_class
                if step_class not in [s.step_class for s in all_steps]:
                    all_steps.append(step_def)

        for position, step_def in enumerate(all_steps):
            step_class = step_def.step_class
            self._step_order[step_class] = position
            for extraction_class in step_def.extractions:
                model = extraction_class.MODEL
                self._model_extraction_step[model] = step_class
            if step_def.transformation:
                self._step_data_transformations[step_class] = step_class

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

    def _validate_foreign_key_dependencies(self) -> None:
        if not self.REGISTRY or not hasattr(self.REGISTRY, "MODELS"):
            return
        registry_models = self.REGISTRY.MODELS
        model_positions = {model: i for i, model in enumerate(registry_models)}
        for model in registry_models:
            dependencies = self._get_foreign_key_dependencies(model)
            model_position = model_positions[model]
            for dependency in dependencies:
                if dependency not in model_positions:
                    continue
                if model_positions[dependency] > model_position:
                    raise ValueError(
                        f"Foreign key dependency error in {self.REGISTRY.__name__}:\n"
                        f"  '{model.__name__}' at position {model_position}, "
                        f"but FK to '{dependency.__name__}' at position {model_positions[dependency]}.\n"
                        f"Move '{dependency.__name__}' before '{model.__name__}'."
                    )

    def _validate_registry_order(self) -> None:
        if not self.REGISTRY or not hasattr(self.REGISTRY, "MODELS"):
            return
        registry_models = self.REGISTRY.MODELS
        extracted_models = [m for m in registry_models if m in self._model_extraction_step]
        for i, model in enumerate(extracted_models):
            extraction_step = self._model_extraction_step[model]
            extraction_position = self._step_order[extraction_step]
            for prev_model in extracted_models[:i]:
                prev_step = self._model_extraction_step[prev_model]
                prev_position = self._step_order[prev_step]
                if prev_position > extraction_position:
                    raise ValueError(
                        f"Extraction order mismatch in {self.REGISTRY.__name__}:\n"
                        f"  '{prev_model.__name__}' before '{model.__name__}' in registry, "
                        f"but extracted later.\n"
                        f"Reorder registry to match extraction order."
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

    def _validate_and_merge_context(self, step, new_context: Any) -> None:
        from llm_pipeline.context import PipelineContext

        if hasattr(step, "_context") and step._context:
            context_class = step._context
            if not isinstance(new_context, context_class):
                raise TypeError(
                    f"{step.__class__.__name__}.process_instructions() must return "
                    f"{context_class.__name__}, got {type(new_context).__name__}"
                )
            if isinstance(new_context, PipelineContext):
                new_context = new_context.model_dump()

        if new_context is None:
            new_context = {}
        elif isinstance(new_context, dict):
            pass
        else:
            raise TypeError(
                f"{step.__class__.__name__}.process_instructions() must return dict or "
                f"PipelineContext, got {type(new_context).__name__}"
            )
        self._context.update(new_context)
        if self._event_emitter:
            self._emit(ContextUpdated(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
                step_name=step.step_name,
                new_keys=list(new_context.keys()),
                context_snapshot=dict(self._context),
            ))

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

        if self.AGENT_REGISTRY is None:
            raise ValueError(
                f"{self.__class__.__name__} must specify agent_registry= parameter."
            )

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

        if self._event_emitter:
            self._emit(PipelineStarted(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
            ))

        try:
            max_steps = max(len(s.get_steps()) for s in self._strategies)

            for step_index in range(max_steps):
                if self._event_emitter:
                    self._emit(StepSelecting(
                        run_id=self.run_id,
                        pipeline_name=self.pipeline_name,
                        step_index=step_index,
                        strategy_count=len(self._strategies),
                    ))

                step_num = step_index + 1
                selected_strategy = None
                step_def = None

                for strategy in self._strategies:
                    if strategy.can_handle(self.context):
                        steps = strategy.get_steps()
                        if step_index < len(steps):
                            selected_strategy = strategy
                            step_def = steps[step_index]
                            break

                if not step_def:
                    break

                self._current_strategy = selected_strategy
                step = step_def.create_step(pipeline=self)
                step_class = type(step)
                self._current_step = step_class
                current_step_name = step.step_name

                if self._event_emitter:
                    self._emit(StepSelected(
                        run_id=self.run_id,
                        pipeline_name=self.pipeline_name,
                        step_name=step.step_name,
                        step_number=step_num,
                        strategy_name=selected_strategy.name,
                    ))

                if step.should_skip():
                    logger.info(f"\nSTEP {step_num}: {step.step_name} SKIPPED")
                    if self._event_emitter:
                        self._emit(StepSkipped(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            step_number=step_num,
                            reason="should_skip returned True",
                        ))
                    self._executed_steps.add(step_class)
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

                if self._event_emitter:
                    self._emit(StepStarted(
                        run_id=self.run_id,
                        pipeline_name=self.pipeline_name,
                        step_name=step.step_name,
                        step_number=step_num,
                        system_key=step.system_instruction_key,
                        user_key=step.user_prompt_key,
                    ))

                step_start = datetime.now(timezone.utc)
                input_hash = self._hash_step_inputs(step, step_num)

                cached_state = None
                if use_cache:
                    if self._event_emitter:
                        self._emit(CacheLookup(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            input_hash=input_hash,
                        ))
                    cached_state = self._find_cached_state(step, input_hash)

                # Step-level token accumulators (sum across all calls)
                _step_input_tokens = 0
                _step_output_tokens = 0
                _step_total_requests = 0
                _step_total_tokens: int | None = None
                _step_cost_usd = 0.0

                if cached_state:
                    if self._event_emitter:
                        self._emit(CacheHit(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            input_hash=input_hash,
                            cached_at=cached_state.created_at,
                        ))
                    logger.info(
                        f"  [CACHED] Using result from "
                        f"{cached_state.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    instructions = self._load_from_cache(cached_state, step)
                    self._instructions[step.step_name] = instructions
                    if self._event_emitter:
                        self._emit(InstructionsStored(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            instruction_count=len(instructions),
                        ))
                    new_context = step.process_instructions(instructions)
                    self._validate_and_merge_context(step, new_context)

                    if hasattr(step, "_transformation") and step._transformation:
                        transformation = step._transformation(self)
                        if self._event_emitter:
                            self._emit(TransformationStarting(
                                transformation_class=step._transformation.__name__,
                                cached=True,
                                step_name=step.step_name,
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                timestamp=datetime.now(timezone.utc),
                            ))
                        transform_start = datetime.now(timezone.utc)
                        current_data = self.get_data("current")
                        transformed_data = transformation.transform(current_data, instructions)
                        self.set_data(transformed_data, step_name=step.step_name)
                        if self._event_emitter:
                            self._emit(TransformationCompleted(
                                data_key=step.step_name,
                                execution_time_ms=(datetime.now(timezone.utc) - transform_start).total_seconds() * 1000,
                                cached=True,
                                step_name=step.step_name,
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                timestamp=datetime.now(timezone.utc),
                            ))

                    step.log_instructions(instructions)
                    if self._event_emitter:
                        self._emit(InstructionsLogged(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            logged_keys=[step.step_name],
                        ))
                    reconstructed_count = self._reconstruct_extractions_from_cache(
                        cached_state, step_def
                    )
                    if self._event_emitter and step_def.extractions:
                        self._emit(CacheReconstruction(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            model_count=len(step_def.extractions),
                            instance_count=reconstructed_count,
                        ))
                    if reconstructed_count == 0 and step_def.extractions:
                        logger.info("  [PARTIAL CACHE] Re-running extraction")
                        step.extract_data(instructions)
                else:
                    if use_cache:
                        if self._event_emitter:
                            self._emit(CacheMiss(
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                step_name=step.step_name,
                                input_hash=input_hash,
                            ))
                        logger.info("  [FRESH] No cache found, running fresh")
                    if step_def.consensus_strategy is not None:
                        logger.info(
                            f"  [CONSENSUS] strategy={step_def.consensus_strategy.name}, "
                            f"max_attempts={step_def.consensus_strategy.max_attempts}"
                        )

                    call_params = step.prepare_calls()
                    instructions = []

                    if self._event_emitter:
                        self._emit(LLMCallPrepared(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            call_count=len(call_params),
                            system_key=step.system_instruction_key,
                            user_key=step.user_prompt_key,
                        ))

                    # Build agent once per step (reused across consensus iterations)
                    output_type, step_tools = step.get_agent(self.AGENT_REGISTRY)

                    # Build validators: always register both, they adapt per-call via ctx.deps
                    step_validators = [
                        not_found_validator(step_def.not_found_indicators),
                        array_length_validator(),
                    ]

                    agent = build_step_agent(
                        step_name=step.step_name,
                        output_type=output_type,
                        validators=step_validators,
                        instrument=self._instrumentation_settings,
                        tools=step_tools,
                        system_instruction_key=step.system_instruction_key,
                    )

                    for idx, params in enumerate(call_params):
                        # Per-call token vars (populated in non-consensus path)
                        _call_input_tokens: int | None = None
                        _call_output_tokens: int | None = None
                        _call_total_tokens: int | None = None

                        # Rebuild StepDeps per-call so per-call params flow correctly
                        step_deps = StepDeps(
                            session=self.session,
                            pipeline_context=self._context,
                            prompt_service=prompt_service,
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            event_emitter=self._event_emitter,
                            variable_resolver=self._variable_resolver,
                            array_validation=params.get("array_validation"),
                            validation_context=params.get("validation_context"),
                            extra=self.get_extra(),
                        )

                        user_prompt = step.build_user_prompt(
                            variables=params.get("variables", {}),
                            prompt_service=prompt_service,
                        )

                        # Resolve system prompt for LLMCallStarting event
                        if self._event_emitter:
                            sys_key = step.system_instruction_key
                            if self._variable_resolver:
                                var_class = self._variable_resolver.resolve(sys_key, 'system')
                                if var_class:
                                    sys_vars = var_class()
                                    sys_vars_dict = (
                                        sys_vars.model_dump()
                                        if hasattr(sys_vars, 'model_dump')
                                        else sys_vars
                                    )
                                    rendered_system = prompt_service.get_system_prompt(
                                        prompt_key=sys_key,
                                        variables=sys_vars_dict,
                                        variable_instance=sys_vars,
                                    )
                                else:
                                    rendered_system = prompt_service.get_prompt(
                                        prompt_key=sys_key,
                                        prompt_type='system',
                                    )
                            else:
                                rendered_system = prompt_service.get_prompt(
                                    prompt_key=sys_key,
                                    prompt_type='system',
                                )
                            self._emit(LLMCallStarting(
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                step_name=step.step_name,
                                call_index=idx,
                                rendered_system_prompt=rendered_system,
                                rendered_user_prompt=user_prompt,
                            ))

                        if step_def.consensus_strategy is not None:
                            # Consensus path: per-attempt LLMCallCompleted events
                            # are emitted inside _execute_with_consensus
                            instruction, _c_input, _c_output, _c_requests, _c_cost = (
                                self._execute_with_consensus(
                                    agent, user_prompt, step_deps, output_type,
                                    strategy=step_def.consensus_strategy,
                                    current_step_name=current_step_name,
                                )
                            )
                            # Merge consensus token totals into step-level accumulators
                            _step_input_tokens += _c_input or 0
                            _step_output_tokens += _c_output or 0
                            _step_total_requests += _c_requests
                            _step_cost_usd += _c_cost or 0.0
                        else:
                            run_result = None
                            try:
                                run_result = agent.run_sync(
                                    user_prompt,
                                    deps=step_deps,
                                    model=self._model,
                                )
                                instruction = run_result.output
                                # Capture per-call token usage
                                _usage = run_result.usage()
                                if _usage:
                                    _call_input_tokens = _usage.input_tokens
                                    _call_output_tokens = _usage.output_tokens
                                    _call_total_tokens = (
                                        (_call_input_tokens or 0) + (_call_output_tokens or 0)
                                    )
                                    _step_input_tokens += _call_input_tokens or 0
                                    _step_output_tokens += _call_output_tokens or 0
                                _step_total_requests += 1
                            except UnexpectedModelBehavior as exc:
                                instruction = output_type.create_failure(str(exc))

                            # Non-consensus: emit single LLMCallCompleted per call
                            _cost_total, _cost_in, _cost_out = _calc_llm_cost(_usage, self._model)
                            _step_cost_usd += _cost_total or 0.0
                            if self._event_emitter:
                                self._emit(LLMCallCompleted(
                                    run_id=self.run_id,
                                    pipeline_name=self.pipeline_name,
                                    step_name=step.step_name,
                                    call_index=idx,
                                    raw_response=_extract_raw_response(run_result) if run_result else None,
                                    parsed_result=(
                                        instruction.model_dump()
                                        if hasattr(instruction, 'model_dump')
                                        else None
                                    ),
                                    model_name=self._model,
                                    attempt_count=1,
                                    validation_errors=[],
                                    input_tokens=_call_input_tokens,
                                    output_tokens=_call_output_tokens,
                                    total_tokens=_call_total_tokens,
                                    cost_usd=_cost_total,
                                    input_cost_usd=_cost_in,
                                    output_cost_usd=_cost_out,
                                ))

                        instructions.append(instruction)

                    self._instructions[step.step_name] = instructions
                    if self._event_emitter:
                        self._emit(InstructionsStored(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            instruction_count=len(instructions),
                        ))
                    new_context = step.process_instructions(instructions)
                    self._validate_and_merge_context(step, new_context)

                    if hasattr(step, "_transformation") and step._transformation:
                        transformation = step._transformation(self)
                        if self._event_emitter:
                            self._emit(TransformationStarting(
                                transformation_class=step._transformation.__name__,
                                cached=False,
                                step_name=step.step_name,
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                timestamp=datetime.now(timezone.utc),
                            ))
                        transform_start = datetime.now(timezone.utc)
                        current_data = self.get_data("current")
                        transformed_data = transformation.transform(current_data, instructions)
                        self.set_data(transformed_data, step_name=step.step_name)
                        if self._event_emitter:
                            self._emit(TransformationCompleted(
                                data_key=step.step_name,
                                execution_time_ms=(datetime.now(timezone.utc) - transform_start).total_seconds() * 1000,
                                cached=False,
                                step_name=step.step_name,
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                timestamp=datetime.now(timezone.utc),
                            ))

                    step.extract_data(instructions)
                    execution_time_ms = int(
                        (datetime.now(timezone.utc) - step_start).total_seconds() * 1000
                    )
                    _step_total_tokens = _step_input_tokens + _step_output_tokens if _step_total_requests > 0 else None
                    self._save_step_state(
                        step, step_num, instructions, input_hash, execution_time_ms, self._model,
                        input_tokens=_step_input_tokens if _step_total_requests > 0 else None,
                        output_tokens=_step_output_tokens if _step_total_requests > 0 else None,
                        total_tokens=_step_total_tokens,
                        total_requests=_step_total_requests if _step_total_requests > 0 else None,
                    )
                    step.log_instructions(instructions)
                    if self._event_emitter:
                        self._emit(InstructionsLogged(
                            run_id=self.run_id,
                            pipeline_name=self.pipeline_name,
                            step_name=step.step_name,
                            logged_keys=[step.step_name],
                        ))

                if self._event_emitter:
                    # Timing includes cache-lookup or LLM-call depending on path;
                    # CEO-approved: step_start stays after logging block (L541).
                    # Token fields are None on cached path (no LLM calls made).
                    self._emit(StepCompleted(
                        run_id=self.run_id,
                        pipeline_name=self.pipeline_name,
                        step_name=step.step_name,
                        step_number=step_num,
                        execution_time_ms=(datetime.now(timezone.utc) - step_start).total_seconds() * 1000,
                        input_tokens=_step_input_tokens if _step_total_requests > 0 else None,
                        output_tokens=_step_output_tokens if _step_total_requests > 0 else None,
                        total_tokens=_step_total_tokens if _step_total_requests > 0 else None,
                        cost_usd=_step_cost_usd if _step_total_requests > 0 and _step_cost_usd > 0 else None,
                    ))

                self._executed_steps.add(step_class)
                if step_def.action_after:
                    action_method = getattr(self, f"_{step_def.action_after}", None)
                    if action_method and callable(action_method):
                        action_method(self.context)

            pipeline_execution_time_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            pipeline_run.status = "completed"
            pipeline_run.completed_at = datetime.now(timezone.utc)
            pipeline_run.step_count = len(self._executed_steps)
            pipeline_run.total_time_ms = int(pipeline_execution_time_ms)
            self._real_session.add(pipeline_run)
            self._real_session.flush()

            if self._event_emitter:
                self._emit(PipelineCompleted(
                    run_id=self.run_id,
                    pipeline_name=self.pipeline_name,
                    execution_time_ms=pipeline_execution_time_ms,
                    steps_executed=len(self._executed_steps),  # unique step classes (includes skipped, deduplicates repeated)
                ))

            self._current_step = None
            return self

        except Exception as e:
            if pipeline_run:
                pipeline_run.status = "failed"
                pipeline_run.completed_at = datetime.now(timezone.utc)
                self._real_session.add(pipeline_run)
                self._real_session.flush()

            if self._event_emitter:
                import traceback
                self._emit(PipelineError(
                    run_id=self.run_id,
                    pipeline_name=self.pipeline_name,
                    step_name=current_step_name,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                ))
            self._current_step = None
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
                select(Prompt).where(Prompt.prompt_key == prompt_system_key)
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
        extraction_classes = getattr(step_def, "extractions", [])
        if not extraction_classes:
            return 0

        logger.info(f"  -> Reconstructing extractions from cached run {cached_run_id[:8]}...")
        total = 0
        for extraction_class in extraction_classes:
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

    def _save_step_state(self, step, step_number, instructions, input_hash, execution_time_ms=None, model_name=None,
                         input_tokens=None, output_tokens=None, total_tokens=None, total_requests=None):
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
                select(Prompt).where(Prompt.prompt_key == prompt_system_key)
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
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            total_requests=total_requests,
        )
        self._real_session.add(state)
        self._real_session.flush()
        if self._event_emitter:
            self._emit(StateSaved(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
                step_name=step.step_name,
                step_number=step_number,
                input_hash=input_hash,
                execution_time_ms=float(execution_time_ms) if execution_time_ms is not None else 0.0,
            ))

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
        self, agent, user_prompt, step_deps, output_type,
        strategy: 'ConsensusStrategy', current_step_name: str,
    ):
        """Execute LLM calls with consensus strategy, accumulating token usage.

        Returns:
            tuple of (result, total_input_tokens, total_output_tokens, total_requests)
            where token values are int | None (None when no usage data available).
        """
        from pydantic_ai import UnexpectedModelBehavior

        results = []
        result_groups = []
        # Token accumulators across all consensus attempts
        _consensus_input_tokens = 0
        _consensus_output_tokens = 0
        _consensus_requests = 0
        _consensus_cost_usd = 0.0
        _has_any_usage = False

        if self._event_emitter:
            self._emit(ConsensusStarted(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
                step_name=current_step_name,
                threshold=strategy.threshold,
                max_calls=strategy.max_attempts,
                strategy_name=strategy.name,
            ))

        for attempt in range(strategy.max_attempts):
            _call_input_tokens = None
            _call_output_tokens = None
            _call_total_tokens = None
            run_result = None
            try:
                run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
                instruction = run_result.output
                # Capture per-call token usage defensively
                _usage = run_result.usage()
                if _usage:
                    _has_any_usage = True
                    _call_input_tokens = _usage.input_tokens if _usage.input_tokens is not None else None
                    _call_output_tokens = _usage.output_tokens if _usage.output_tokens is not None else None
                    _call_total_tokens = (
                        (_call_input_tokens or 0) + (_call_output_tokens or 0)
                    )
                    _consensus_input_tokens += _call_input_tokens or 0
                    _consensus_output_tokens += _call_output_tokens or 0
            except UnexpectedModelBehavior as exc:
                instruction = output_type.create_failure(str(exc))
            _consensus_requests += 1

            # Emit per-attempt LLMCallCompleted with per-call token values
            _cost_total, _cost_in, _cost_out = _calc_llm_cost(_usage, self._model)
            _consensus_cost_usd += _cost_total or 0.0
            if self._event_emitter:
                self._emit(LLMCallCompleted(
                    run_id=self.run_id,
                    pipeline_name=self.pipeline_name,
                    step_name=current_step_name,
                    call_index=attempt,
                    raw_response=_extract_raw_response(run_result) if run_result else None,
                    parsed_result=(
                        instruction.model_dump()
                        if hasattr(instruction, 'model_dump')
                        else None
                    ),
                    model_name=self._model,
                    attempt_count=attempt + 1,
                    validation_errors=[],
                    input_tokens=_call_input_tokens,
                    output_tokens=_call_output_tokens,
                    total_tokens=_call_total_tokens,
                    cost_usd=_cost_total,
                    input_cost_usd=_cost_in,
                    output_cost_usd=_cost_out,
                ))

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

            if self._event_emitter:
                self._emit(ConsensusAttempt(
                    run_id=self.run_id,
                    pipeline_name=self.pipeline_name,
                    step_name=current_step_name,
                    attempt=attempt + 1,
                    group_count=len(result_groups),
                ))

            if not strategy.should_continue(results, result_groups, attempt + 1, strategy.max_attempts):
                break

        consensus_result = strategy.select(results, result_groups)

        if consensus_result.consensus_reached:
            logger.info(
                f"  [CONSENSUS] {strategy.name}: reached after {consensus_result.total_attempts} attempts"
            )
            if self._event_emitter:
                self._emit(ConsensusReached(
                    run_id=self.run_id,
                    pipeline_name=self.pipeline_name,
                    step_name=current_step_name,
                    attempt=consensus_result.total_attempts,
                    threshold=strategy.threshold,
                ))
        else:
            logger.info(
                f"  [NO CONSENSUS] {strategy.name}: after {consensus_result.total_attempts} attempts"
            )
            largest_group = max(result_groups, key=len)
            if self._event_emitter:
                self._emit(ConsensusFailed(
                    run_id=self.run_id,
                    pipeline_name=self.pipeline_name,
                    step_name=current_step_name,
                    max_calls=strategy.max_attempts,
                    largest_group_size=len(largest_group),
                ))

        return (
            consensus_result.result,
            _consensus_input_tokens if _has_any_usage else None,
            _consensus_output_tokens if _has_any_usage else None,
            _consensus_requests,
            _consensus_cost_usd,
        )

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
