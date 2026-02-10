# LLM Provider API Reference

API reference for LLM provider abstractions, implementations, and execution utilities.

## Module: `llm_pipeline.llm`

Provider-agnostic LLM integration layer with structured output validation.

### Exports

```python
from llm_pipeline.llm import (
    LLMProvider,           # Abstract base class for providers
    RateLimiter,          # API rate limiting utility
    flatten_schema,       # Schema flattening for $ref resolution
    format_schema_for_llm # Schema formatting for LLM prompts
)
```

---

## LLMProvider

**Module:** `llm_pipeline.llm.provider`

Abstract base class defining the interface for LLM provider implementations.

### Class Definition

```python
class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implementations handle:
    - API authentication
    - Request formatting
    - Response parsing
    - Rate limiting
    - Retry logic
    """
```

### Abstract Methods

#### `call_structured()`

Call LLM with structured output validation and retry logic.

```python
@abstractmethod
def call_structured(
    self,
    prompt: str,
    system_instruction: str,
    result_class: Type[BaseModel],
    max_retries: int = 3,
    not_found_indicators: Optional[List[str]] = None,
    strict_types: bool = True,
    array_validation: Optional[ArrayValidationConfig] = None,
    validation_context: Optional[ValidationContext] = None,
    **kwargs
) -> Optional[Dict[str, Any]]
```

**Parameters:**

- `prompt` (str): User prompt text
- `system_instruction` (str): System instruction text
- `result_class` (Type[BaseModel]): Pydantic model class for validation
- `max_retries` (int): Maximum retry attempts (default: 3)
- `not_found_indicators` (Optional[List[str]]): Phrases indicating LLM couldn't find information
- `strict_types` (bool): Validate field types strictly (default: True)
- `array_validation` (Optional[ArrayValidationConfig]): Array validation configuration
- `validation_context` (Optional[ValidationContext]): Context data for Pydantic validators

**Returns:** `Optional[Dict[str, Any]]` - Validated JSON response dict, or None if all retries failed

**Example:**

```python
from llm_pipeline.llm import LLMProvider
from pydantic import BaseModel

class CustomProvider(LLMProvider):
    def call_structured(
        self,
        prompt: str,
        system_instruction: str,
        result_class: Type[BaseModel],
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        # Implement custom provider logic
        response = self.api.generate(prompt, system_instruction)
        return validate_and_return(response, result_class)
```

---

## GeminiProvider

**Module:** `llm_pipeline.llm.gemini`

Google Gemini LLM provider implementation with structured output validation.

**Installation:** `pip install llm-pipeline[gemini]`

### Class Definition

```python
class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM provider.

    Uses google-generativeai SDK for structured output with validation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.0-flash-lite",
        rate_limiter: Optional[RateLimiter] = None
    )
```

**Parameters:**

- `api_key` (Optional[str]): Gemini API key. Falls back to `GEMINI_API_KEY` environment variable
- `model_name` (str): Model to use (default: "gemini-2.0-flash-lite")
- `rate_limiter` (Optional[RateLimiter]): Custom rate limiter instance. Creates default if None

### Methods

#### `call_structured()`

Implements `LLMProvider.call_structured()` with Gemini-specific logic.

**Validation Layers:**

1. **Schema Structure**: Validates response structure matches Pydantic schema
2. **Array Response**: Validates array length, order, and original values
3. **Pydantic Validation**: Full Pydantic model validation with custom validators
4. **Not Found Detection**: Checks for phrases indicating missing information

**Retry Logic:**

- Exponential backoff for rate limits (2^attempt seconds)
- Parses API retry delay suggestions from error messages
- Continues on validation failures until max_retries exhausted

**Example:**

```python
from llm_pipeline.llm.gemini import GeminiProvider
from pydantic import BaseModel

class ParsedData(BaseModel):
    name: str
    quantity: int

provider = GeminiProvider(api_key="your-api-key")

result = provider.call_structured(
    prompt="Extract name and quantity from: '5 widgets'",
    system_instruction="You are a data extraction assistant",
    result_class=ParsedData
)

if result:
    data = ParsedData(**result)
    print(f"Parsed: {data.name} x {data.quantity}")
```

---

## execute_llm_step()

**Module:** `llm_pipeline.llm.executor`

Provider-agnostic LLM step executor function. Handles prompt retrieval, variable formatting, and dispatching to LLM providers.

### Function Signature

```python
def execute_llm_step(
    system_instruction_key: str,
    user_prompt_key: str,
    variables: Any,
    result_class: Type[T],
    provider: Any = None,
    prompt_service: Any = None,
    context: Optional[Dict[str, Any]] = None,
    array_validation: Optional[ArrayValidationConfig] = None,
    system_variables: Optional[Any] = None,
    validation_context: Optional[ValidationContext] = None
) -> T
```

**Parameters:**

- `system_instruction_key` (str): Key for system instruction prompt in database
- `user_prompt_key` (str): Key for user prompt template in database
- `variables` (Any): PromptVariables instance or dict with template variables
- `result_class` (Type[T]): Pydantic model class for result validation
- `provider` (Any): LLMProvider instance for making LLM calls
- `prompt_service` (Any): PromptService instance for prompt retrieval
- `context` (Optional[Dict[str, Any]]): Context for prompt retrieval (strategy selection)
- `array_validation` (Optional[ArrayValidationConfig]): Array validation configuration
- `system_variables` (Optional[Any]): System prompt variables (PromptVariables.System)
- `validation_context` (Optional[ValidationContext]): Context data for Pydantic validators

**Returns:** `T` - Validated Pydantic result object

**Raises:**

- `ValueError`: If provider or prompt_service not provided

**Execution Flow:**

1. Convert PromptVariables instances to dicts
2. Retrieve system instruction via prompt_service
3. Retrieve and format user prompt with variables
4. Call LLM via provider.call_structured()
5. Validate response with Pydantic
6. Return result or call result_class.create_failure()

**Example:**

```python
from llm_pipeline.llm.executor import execute_llm_step
from llm_pipeline.llm.gemini import GeminiProvider
from llm_pipeline.prompts import PromptService
from pydantic import BaseModel

class ExtractionResult(BaseModel):
    value: str

    @classmethod
    def create_failure(cls, reason: str):
        return cls(value=f"FAILED: {reason}")

class PromptVariables(BaseModel):
    input_text: str

provider = GeminiProvider()
prompt_service = PromptService(session)

result = execute_llm_step(
    system_instruction_key="extraction_system",
    user_prompt_key="extract_value",
    variables=PromptVariables(input_text="Sample data"),
    result_class=ExtractionResult,
    provider=provider,
    prompt_service=prompt_service
)
```

---

## RateLimiter

**Module:** `llm_pipeline.llm.rate_limiter`

Simple rate limiter using sliding window approach to prevent exceeding API quotas.

### Class Definition

```python
class RateLimiter:
    """
    Simple rate limiter to ensure we don't exceed API quotas.

    Uses a sliding window approach to track request timestamps.
    """

    def __init__(
        self,
        max_requests: int,
        time_window_seconds: float
    )
```

**Parameters:**

- `max_requests` (int): Maximum requests allowed in time window
- `time_window_seconds` (float): Time window in seconds (e.g., 60 for per-minute)

### Methods

#### `wait_if_needed()`

Block until next request is allowed under rate limit.

```python
def wait_if_needed(self) -> None
```

**Example:**

```python
from llm_pipeline.llm import RateLimiter

limiter = RateLimiter(max_requests=10, time_window_seconds=60)

for request in requests:
    limiter.wait_if_needed()  # Blocks if limit reached
    make_api_call(request)
```

#### `get_wait_time()`

Calculate seconds to wait before next request (0 if can request immediately).

```python
def get_wait_time(self) -> float
```

**Returns:** `float` - Seconds to wait, or 0 if request can proceed

#### `reset()`

Clear all recorded request timestamps.

```python
def reset(self) -> None
```

---

## Validation Layers

The LLM provider system implements multiple validation layers to ensure response quality.

### Layer 1: Schema Structure Validation

**Module:** `llm_pipeline.llm.validation`

**Function:** `validate_structured_output()`

```python
def validate_structured_output(
    response_json: Any,
    expected_schema: Dict[str, Any],
    strict_types: bool = True
) -> Tuple[bool, List[str]]
```

Validates response matches Pydantic JSON schema structure.

**Validates:**
- Required fields present
- Field types match schema (if strict_types=True)
- Nested object/array structure
- anyOf type unions

**Returns:** `(is_valid, errors)` tuple

### Layer 2: Array Response Validation

**Function:** `validate_array_response()`

```python
def validate_array_response(
    response_json: Dict[str, Any],
    config: ArrayValidationConfig,
    attempt: int
) -> Tuple[bool, List[str]]
```

Validates LLM array response matches input array length and order.

**Validates:**
- Array length matches input
- Order preserved (or reorderable via match_field)
- Original values present in match_field

**Configuration:**

```python
from llm_pipeline.types import ArrayValidationConfig

config = ArrayValidationConfig(
    input_array=["Item 1", "Item 2", "Item 3"],
    match_field="original",          # Field containing original value
    filter_empty_inputs=False,       # Skip empty input items
    allow_reordering=True,           # Allow LLM to reorder, we'll fix it
    strip_number_prefix=True         # Strip "1. " prefixes for matching
)
```

### Layer 3: Pydantic Validation

Pydantic model validation with custom validators and ValidationContext.

**Example:**

```python
from pydantic import BaseModel, field_validator
from llm_pipeline.types import ValidationContext

class ExtractedData(BaseModel):
    row_index: int

    @field_validator('row_index')
    @classmethod
    def validate_row_index(cls, v, info):
        # Access validation context
        num_rows = info.context.get('num_rows')
        if v >= num_rows:
            raise ValueError(f"Row index {v} exceeds sheet rows {num_rows}")
        return v

# Pass context during execution
validation_context = ValidationContext(num_rows=100)
result = execute_llm_step(
    ...,
    validation_context=validation_context
)
```

### Layer 4: Extraction Instance Validation

**Module:** `llm_pipeline.extraction`

**Method:** `_validate_instance()`

Validates extraction instances before database save:
- No NaN/NULL values in required fields
- Foreign key values exist in reference tables
- Field constraints satisfied

### Layer 5: Database Constraints

SQLAlchemy/SQLModel database constraints validated during commit:
- Unique constraints
- Foreign key constraints
- Check constraints
- NOT NULL constraints

---

## Schema Formatting Utilities

### flatten_schema()

**Module:** `llm_pipeline.llm.schema`

Flatten Pydantic JSON schema by inlining all `$ref` references.

```python
def flatten_schema(schema: Dict[str, Any]) -> Dict[str, Any]
```

Removes `$defs` section and replaces `$ref` pointers with actual definitions.

**Parameters:**

- `schema` (Dict[str, Any]): Pydantic JSON schema with potential $defs and $ref

**Returns:** `Dict[str, Any]` - Flattened schema with references inlined

**Example:**

```python
from llm_pipeline.llm import flatten_schema
from pydantic import BaseModel

class Address(BaseModel):
    street: str

class Person(BaseModel):
    name: str
    address: Address

schema = Person.model_json_schema()
# Contains: {"$defs": {"Address": {...}}, "properties": {"address": {"$ref": "#/$defs/Address"}}}

flattened = flatten_schema(schema)
# Contains: {"properties": {"address": {"type": "object", "properties": {"street": {...}}}}}
```

### format_schema_for_llm()

Format Pydantic model into clear, LLM-friendly instructions.

```python
def format_schema_for_llm(result_class: Type[LLMResultMixin]) -> str
```

Generates formatted string with:
1. Flattened JSON schema
2. Example from `result_class.get_example()`
3. Instructions for JSON-only response

**Parameters:**

- `result_class` (Type[LLMResultMixin]): Pydantic model class (must have get_example() method)

**Returns:** `str` - Formatted schema instructions for LLM prompt

**Example:**

```python
from llm_pipeline.llm import format_schema_for_llm
from llm_pipeline.step import LLMResultMixin

class ExtractionResult(LLMResultMixin):
    name: str
    count: int

    @classmethod
    def get_example(cls):
        return cls(name="Widget", count=5)

formatted = format_schema_for_llm(ExtractionResult)
# Returns multi-line string with:
# EXPECTED JSON SCHEMA:
# {
#   "type": "object",
#   "properties": {
#     "name": {"type": "string"},
#     "count": {"type": "integer"}
#   },
#   ...
# }
#
# RESPONSE FORMAT EXAMPLE:
# {"name": "Widget", "count": 5}
# ...
```

---

## Helper Functions

### check_not_found_response()

**Module:** `llm_pipeline.llm.validation`

Check if LLM response indicates it couldn't find requested information.

```python
def check_not_found_response(
    response_text: str,
    not_found_indicators: List[str]
) -> bool
```

**Example:**

```python
from llm_pipeline.llm.validation import check_not_found_response

indicators = ["not found", "no data", "cannot extract"]
response = "I cannot find the requested information in the document."

if check_not_found_response(response, indicators):
    print("LLM indicated data not found")
```

### extract_retry_delay_from_error()

Extract retry delay suggestion from rate limit error messages.

```python
def extract_retry_delay_from_error(error: Exception) -> Optional[float]
```

Parses error messages for patterns like "Please retry in 30s" or "retry_delay { seconds: 30 }".

**Returns:** `Optional[float]` - Suggested delay in seconds, or None

---

## Usage Example

Complete example using GeminiProvider with all validation layers:

```python
from llm_pipeline.llm.gemini import GeminiProvider
from llm_pipeline.llm.executor import execute_llm_step
from llm_pipeline.prompts import PromptService
from llm_pipeline.types import ArrayValidationConfig, ValidationContext
from pydantic import BaseModel, field_validator

# Define result model
class LocationData(BaseModel):
    original: str
    city: str
    country: str

    @field_validator('city')
    @classmethod
    def validate_city(cls, v, info):
        if not v or v == "UNKNOWN":
            raise ValueError("City must be specified")
        return v

    @classmethod
    def create_failure(cls, reason: str):
        return cls(original="", city="FAILED", country=reason)

    @classmethod
    def get_example(cls):
        return cls(original="NYC", city="New York", country="USA")

# Configure provider with rate limiting
provider = GeminiProvider(
    api_key="your-api-key",
    model_name="gemini-2.0-flash-lite"
)

# Setup array validation
locations = ["Los Angeles", "Chicago", "Boston"]
array_config = ArrayValidationConfig(
    input_array=locations,
    match_field="original",
    allow_reordering=True
)

# Setup validation context
validation_context = ValidationContext(
    allowed_countries=["USA", "Canada", "Mexico"]
)

# Execute with all validation layers
results = execute_llm_step(
    system_instruction_key="location_extraction_system",
    user_prompt_key="normalize_locations",
    variables={"locations": locations},
    result_class=LocationData,
    provider=provider,
    prompt_service=PromptService(session),
    array_validation=array_config,
    validation_context=validation_context
)
```

---

## See Also

- [Prompt System API](prompts.md) - Prompt retrieval and variable formatting
- [Step API](step.md) - LLMStep and step_definition decorator
- [Types](../architecture/concepts.md#types) - ArrayValidationConfig and ValidationContext details
- [Validation](../architecture/patterns.md#validation-layers) - Multi-layer validation architecture
