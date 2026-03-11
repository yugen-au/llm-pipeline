# llm-pipeline

Declarative LLM pipeline orchestration framework.

## Installation

```bash
pip install llm-pipeline
```

## Event System

Observe pipeline execution in real time using the event system. `InMemoryEventHandler` collects all events for a run:

```python
from llm_pipeline import InMemoryEventHandler, CompositeEmitter

# Attach handler to pipeline at construction
handler = InMemoryEventHandler()
pipeline = MyPipeline(provider=provider, event_emitter=handler)
pipeline.execute(data)

# Events are stored as dicts
for event in handler.get_events(pipeline.run_id):
    print(f"{event['event_type']}: {event['timestamp']}")

# Filter by type
llm_events = handler.get_events_by_type('llm_call_starting', pipeline.run_id)
for event in llm_events:
    print(f"Prompt: {event['rendered_user_prompt']}")
```

Use `CompositeEmitter` to attach multiple handlers simultaneously:

```python
from llm_pipeline import InMemoryEventHandler, CompositeEmitter, LoggingEventHandler

memory_handler = InMemoryEventHandler()
log_handler = LoggingEventHandler()

emitter = CompositeEmitter([memory_handler, log_handler])
pipeline = MyPipeline(provider=provider, event_emitter=emitter)
```

31 event types are available in `llm_pipeline.events`, covering pipeline lifecycle, step execution, LLM calls, cache hits, consensus polling, and more.

## UI

The optional web UI provides a dashboard for browsing pipeline runs and events.

```bash
pip install llm-pipeline[ui]

# Start UI (default port 8642)
llm-pipeline ui

# Development mode with hot reload
llm-pipeline ui --dev --port 8642

# Connect to a specific database
llm-pipeline ui --db /path/to/pipeline.db
```

## LLMCallResult

`provider.call_structured()` returns an `LLMCallResult` with structured output and metadata:

```python
from llm_pipeline import LLMCallResult

# Construct directly using factory methods (for testing)
result = LLMCallResult.success(
    parsed={"name": "widget", "count": 5},
    raw_response='{"name": "widget", "count": 5}',
    model_name="gemini-2.0-flash-lite",
    attempt_count=1,
)

print(result.parsed)            # {'name': 'widget', 'count': 5}
print(result.raw_response)      # original text from LLM
print(result.model_name)        # model that produced the result
print(result.attempt_count)     # number of attempts (includes retries)
print(result.validation_errors) # list of validation error strings
print(result.is_success)        # True when parsed is not None
print(result.is_failure)        # True when parsed is None

# Failure case
failed = LLMCallResult.failure(
    raw_response="I cannot extract the requested data.",
    model_name="gemini-2.0-flash-lite",
    attempt_count=3,
    validation_errors=["Field 'count' must be a positive integer"],
)
print(failed.is_failure)  # True
```

## Documentation

Full documentation: [docs/](docs/)
