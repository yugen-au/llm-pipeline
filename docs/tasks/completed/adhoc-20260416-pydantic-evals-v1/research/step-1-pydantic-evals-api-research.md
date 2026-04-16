# pydantic-evals API Research

## Package Info
- PyPI: `pydantic-evals` (separate from `pydantic-ai`, no dependency on it)
- Install: `pip install pydantic-evals` or `pip install 'pydantic-evals[logfire]'`
- Current in uv.lock but NOT in pyproject.toml dependencies yet

---

## Core Primitives

### Case[InputsT, OutputT, MetadataT]
Dataclass (not BaseModel). Single test scenario.

```python
Case(
    name: str | None = None,          # identifier in reports
    inputs: InputsT,                   # REQUIRED - task input
    metadata: MetadataT | None = None, # arbitrary metadata for evaluators
    expected_output: OutputT | None = None,  # for comparison evaluators
    evaluators: tuple[Evaluator, ...] = (),  # case-specific evaluators
)
```

- `inputs` can be any type: str, dict, Pydantic model, etc.
- `expected_output` is optional; EqualsExpected skips if None
- Case-specific evaluators run IN ADDITION to dataset-level evaluators

### Dataset[InputsT, OutputT, MetadataT]
BaseModel (Pydantic). Collection of cases + evaluators.

```python
Dataset(
    name: str | None = None,              # dataset name (will be required)
    cases: Sequence[Case[I, O, M]],       # REQUIRED
    evaluators: Sequence[Evaluator] = (), # run on ALL cases
    report_evaluators: Sequence[ReportEvaluator] = (),  # run once on full report
)
```

Methods:
- `add_case(name, inputs, metadata, expected_output, evaluators)` - convenience
- `add_evaluator(evaluator, specific_case=None)` - add to all or specific case
- `evaluate(task, ...)` - async, returns EvaluationReport
- `evaluate_sync(task, ...)` - sync wrapper
- `to_file(path, fmt, schema_path, custom_evaluator_types, custom_report_evaluator_types)`
- `from_file(path, fmt, custom_evaluator_types, custom_report_evaluator_types)` - classmethod

### EvaluatorContext[InputsT, OutputT, MetadataT]
Passed to every evaluator's `evaluate()` method.

Fields:
- `name: str` - case name
- `inputs: InputsT` - task inputs
- `metadata: MetadataT | None` - case metadata
- `expected_output: OutputT | None` - expected output
- `output: OutputT` - actual task output
- `duration: float` - task execution time (seconds)
- `span_tree: SpanTree | None` - OpenTelemetry spans (if logfire configured)
- `metrics: dict[str, int | float]` - custom metrics set during task
- `attributes: dict[str, Any]` - custom attributes set during task

### EvaluationReport[InputsT, OutputT, MetadataT]
Generic dataclass. Result of evaluation.

Fields:
- `name: str` - report/experiment name
- `cases: list[ReportCase[I, O, M]]` - per-case results
- `failures: list[ReportCaseFailure[I, O, M]]` - cases where task raised exception
- `analyses: list[ReportAnalysis]` - report-evaluator outputs
- `evaluator_failures: list[EvaluatorFailure]` - report-evaluator exceptions
- `metadata: dict[str, Any] | None` - experiment metadata
- `trace_id: str | None` - OTel trace ID
- `span_id: str | None` - OTel span ID

Methods:
- `print(...)` - rich console output with many display options
- `render(...)` - returns formatted string
- `console_table(baseline=...)` - rich Table, supports baseline diff
- `failures_table(...)` - rich Table of failures only
- `case_groups()` - groups by source_case_name for repeat>1 experiments
- `averages()` - returns ReportCaseAggregate

### ReportCase[InputsT, OutputT, MetadataT]
Per-case result within report.

Fields:
- `name, inputs, metadata, expected_output, output` - mirrors Case + actual output
- `source_case_name: str | None` - for repeat>1 aggregation
- `trace_id, span_id` - OTel IDs

### ReportCaseFailure[InputsT, OutputT, MetadataT]
Case where task execution raised exception.
- `name, inputs, metadata, expected_output` - case info
- `error_message: str`, `stacktrace: str`

### ReportAnalysis (discriminated union)
- `ConfusionMatrix` - labels + matrix
- `PrecisionRecall` - curves + AUC
- `ScalarResult` - single value + optional unit
- `TableResult` - headers + rows
- `LinePlot` - XY curves

---

## Built-in Evaluators

### Case-Level

| Evaluator | Constructor | Returns | Notes |
|---|---|---|---|
| `EqualsExpected` | `EqualsExpected()` | `bool` | `ctx.output == ctx.expected_output`; skips (returns `{}`) if expected_output is None |
| `Equals` | `Equals(value, evaluation_name=None)` | `bool` | `ctx.output == value` |
| `Contains` | `Contains(value, case_sensitive=True, as_strings=False, evaluation_name=None)` | `EvaluationReason` | Substring for str, membership for list/tuple, key-value for dict |
| `IsInstance` | `IsInstance(type_name, evaluation_name=None)` | `EvaluationReason` | Checks `__name__`/`__qualname__` across MRO |
| `MaxDuration` | `MaxDuration(seconds: float \| timedelta)` | `bool` | `ctx.duration <= seconds` |
| `LLMJudge` | `LLMJudge(rubric, model='openai:gpt-5.2', include_input=False, include_expected_output=False, model_settings=None, score=False, assertion={'include_reason': True})` | `dict` with `_pass` and/or `_score` keys | Configurable output modes |
| `HasMatchingSpan` | `HasMatchingSpan(query: SpanQuery, evaluation_name=None)` | `bool` | Requires logfire/OTel |

### Report-Level

| Evaluator | Constructor | Output |
|---|---|---|
| `ConfusionMatrixEvaluator` | `ConfusionMatrixEvaluator(predicted_from, expected_from)` | `ConfusionMatrix` |
| `PrecisionRecallEvaluator` | (params TBD) | `PrecisionRecall` |

### No "Python" Evaluator
There is no built-in evaluator named "Python". Custom evaluators fill this role.

---

## Custom Evaluator Authoring

### Requirements
1. `@dataclass` decorator (REQUIRED)
2. Inherit from `Evaluator` (or `Evaluator[InputsT, OutputT, MetadataT]` for typed)
3. Implement `evaluate(self, ctx: EvaluatorContext) -> EvaluatorOutput`

### Return Types (EvaluatorOutput)
- `bool` - pass/fail assertion
- `int` / `float` - numeric score
- `str` - categorical label
- `EvaluationReason(value: bool|int|float|str, reason: str)` - value + explanation
- `dict[str, <any of above>]` - multiple named results (each key = separate report column)
- `{}` (empty dict) - evaluator doesn't apply to this case (skip)

### Sync vs Async
Both `def evaluate(...)` and `async def evaluate(...)` work. Framework handles both.

### Configurable Parameters
Dataclass fields become constructor parameters:
```python
@dataclass
class ContainsKeyword(Evaluator):
    keyword: str
    case_sensitive: bool = True
    def evaluate(self, ctx: EvaluatorContext) -> bool: ...
```

### Custom Display Name
Override `get_default_evaluation_name() -> str` or use `evaluation_name` field.

### Error Handling
Exceptions during evaluation captured as `EvaluatorFailure` (evaluator name, message, stacktrace). Appear in `report.cases[i].evaluator_failures`.

---

## Dataset I/O

### YAML Format
```yaml
# yaml-language-server: $schema=my_tests_schema.json
name: my_tests
cases:
  - name: test_1
    inputs: hello
    expected_output: HELLO
    evaluators:
      - EqualsExpected
evaluators:
  - IsInstance:
      type_name: str
report_evaluators: []
```

### JSON Format
```json
{
  "$schema": "my_tests_schema.json",
  "name": null,
  "cases": [
    {
      "name": "test_1",
      "inputs": {"question": "What is X?"},
      "metadata": {"difficulty": "easy"},
      "expected_output": {"answer": "Y"},
      "evaluators": ["EqualsExpected"]
    }
  ],
  "evaluators": [],
  "report_evaluators": []
}
```

### Schema Sidecar
- `to_file()` auto-generates `{stem}_schema.json` alongside data file
- Configurable via `schema_path` param (string template with `{stem}`)
- `schema_path=None` disables schema generation
- `custom_evaluator_types` list required for custom evaluators to appear in schema

### Evaluator Serialization in YAML/JSON
- Simple: just class name string `"EqualsExpected"`
- With params: dict `{"Contains": {"value": "hello", "case_sensitive": false}}`

---

## Execution Model

### evaluate() Signature
```python
async def evaluate(
    task: Callable[[InputsT], Awaitable[OutputT]] | Callable[[InputsT], OutputT],
    name: str | None = None,
    max_concurrency: int | None = None,
    progress: bool = True,
    retry_task: RetryConfig | None = None,
    retry_evaluators: RetryConfig | None = None,
    task_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    repeat: int = 1,
    lifecycle: type[CaseLifecycle] | None = None,
) -> EvaluationReport
```

### Task Function
- Signature: `(InputsT) -> OutputT` or `(InputsT) -> Awaitable[OutputT]`
- Single argument = the case's `inputs`
- Return value = compared against `expected_output` by evaluators

### Execution Flow
1. For each case (concurrent up to max_concurrency via anyio.Semaphore):
   a. Run task_fn(case.inputs) -> output
   b. Run dataset-level evaluators + case-level evaluators on (inputs, output, expected_output)
   c. Collect into ReportCase
2. Run report_evaluators on full results
3. Return EvaluationReport

### CaseLifecycle
Per-case setup/teardown hooks. New instance per case.

### Custom Metrics During Task
```python
from pydantic_evals import increment_eval_metric, set_eval_attribute
increment_eval_metric('api_calls', 3)
set_eval_attribute('used_cache', True)
```
Accessible in evaluators via `ctx.metrics` and `ctx.attributes`.

---

## pydantic-ai Agent Integration

### Agent as task_fn
pydantic-evals does NOT depend on pydantic-ai. Integration is via wrapper:

```python
from pydantic_ai import Agent

agent = Agent('openai:gpt-4o', result_type=MyOutput)

async def task_fn(inputs: MyInput) -> MyOutput:
    result = await agent.run(inputs.prompt)
    return result.output

report = await dataset.evaluate(task_fn)
```

### Span Flow
If logfire is configured, pydantic-ai agent spans flow into the evaluation's span tree. HasMatchingSpan can verify tool calls, model invocations etc.

---

## Field-Level Evaluation (KEY DESIGN INSIGHT)

### EqualsExpected Does NOT Support Partial Matching
`EqualsExpected` uses `ctx.output == ctx.expected_output` (Python `==`). For Pydantic models, this means ALL fields must match. No way to check only some fields.

### Strategies for Partial Field Matching

**Strategy 1: Custom per-field evaluator (RECOMMENDED for our use case)**
```python
@dataclass
class FieldEquals(Evaluator):
    field_name: str
    
    def evaluate(self, ctx: EvaluatorContext) -> EvaluatorOutput:
        if ctx.expected_output is None:
            return {}
        expected_val = getattr(ctx.expected_output, self.field_name, None)
        if expected_val is None:
            return {}  # field not in expected, skip
        actual_val = getattr(ctx.output, self.field_name, None)
        return {self.field_name: actual_val == expected_val}
```

**Strategy 2: Auto-generate from Pydantic schema**
Iterate `model.model_fields` to create one evaluator per field, or a single evaluator returning a dict with all field comparisons. This fits llm-pipeline's `instructions_schema` pattern perfectly.

**Strategy 3: Dict return with selective fields**
```python
@dataclass
class PartialMatch(Evaluator):
    fields: list[str]
    
    def evaluate(self, ctx: EvaluatorContext) -> dict[str, bool]:
        if ctx.expected_output is None:
            return {}
        return {
            f: getattr(ctx.output, f) == getattr(ctx.expected_output, f)
            for f in self.fields
            if hasattr(ctx.expected_output, f)
        }
```

### Implication for llm-pipeline
Since each step has a typed Instructions class (Pydantic BaseModel), we can:
1. Auto-discover fields via `InstructionsClass.model_fields`
2. Generate a `FieldMatchEvaluator` per field or a single evaluator returning `dict[field_name, bool]`
3. Let users specify in YAML which fields to check via `expected_output` (only non-None fields evaluated)
4. The `{}` return pattern means evaluators can self-skip when field not in expected_output

---

## YAML Dataset Format for llm-pipeline Integration

Example dataset for a sentiment analysis step:
```yaml
# yaml-language-server: $schema=sentiment_analysis_schema.json
name: sentiment_analysis_eval
cases:
  - name: positive_review
    inputs:
      text: "This product is amazing!"
    expected_output:
      sentiment: positive
      # explanation field omitted = not checked
    evaluators:
      - LLMJudge:
          rubric: "Explanation should justify the positive sentiment"
          include_input: true
  - name: negative_review
    inputs:
      text: "Terrible experience, never again"
    expected_output:
      sentiment: negative
evaluators:
  - IsInstance:
      type_name: SentimentInstructions
  - FieldMatch:
      # custom evaluator: only checks fields present in expected_output
```

---

## Summary of Key API Facts

| Aspect | Detail |
|---|---|
| Generic params | `Dataset[InputsT, OutputT, MetadataT]` |
| Task signature | `(InputsT) -> OutputT` or async |
| Evaluator base | `@dataclass class MyEval(Evaluator)` |
| Evaluate return | `bool \| int \| float \| str \| EvaluationReason \| dict` |
| Skip pattern | Return `{}` from evaluator |
| Partial match | NOT built-in, need custom evaluator |
| Serialization | YAML/JSON + auto JSON Schema sidecar |
| Concurrency | `max_concurrency` param, anyio.Semaphore |
| Report comparison | `report.print(baseline=other_report)` for diffs |
| Report aggregation | `report.averages()` -> ReportCaseAggregate |
| Lifecycle hooks | `CaseLifecycle` class for per-case setup/teardown |
| Metrics in task | `increment_eval_metric()`, `set_eval_attribute()` |
| Agent integration | Wrapper function, no direct pydantic-ai coupling |
