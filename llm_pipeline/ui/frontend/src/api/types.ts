/**
 * TypeScript interfaces mirroring backend Pydantic response models.
 *
 * All types match the shapes returned by FastAPI endpoints in
 * llm_pipeline/ui/routes/. Provisional types (pipelines) are typed
 * against existing DB/introspection models but their endpoints do
 * not exist yet (task 24).
 */

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

/** Pipeline run status values observed in the backend. */
export type RunStatus = 'running' | 'completed' | 'failed'

/** Single item in GET /api/runs response list. */
export interface RunListItem {
  run_id: string
  pipeline_name: string
  status: string
  started_at: string
  completed_at: string | null
  step_count: number | null
  total_time_ms: number | null
}

/** GET /api/runs response body. */
export interface RunListResponse {
  items: RunListItem[]
  total: number
  offset: number
  limit: number
}

/** Embedded step summary inside RunDetail. */
export interface StepSummary {
  step_name: string
  step_number: number
  execution_time_ms: number | null
  created_at: string
}

/** GET /api/runs/{run_id} response body. */
export interface RunDetail {
  run_id: string
  pipeline_name: string
  status: string
  started_at: string
  completed_at: string | null
  step_count: number | null
  total_time_ms: number | null
  steps: StepSummary[]
}

/**
 * POST /api/runs request body.
 *
 * `input_data` is optional and forwarded to the pipeline factory as
 * initial context when provided (task 38).
 */
export interface TriggerRunRequest {
  pipeline_name: string
  input_data?: Record<string, unknown>
}

/** POST /api/runs response body (202 Accepted). */
export interface TriggerRunResponse {
  run_id: string
  status: string
}

// ---------------------------------------------------------------------------
// Query params
// ---------------------------------------------------------------------------

/** Query params for GET /api/runs. All fields optional for partial filtering. */
export interface RunListParams {
  pipeline_name?: string
  status?: string
  started_after?: string
  started_before?: string
  offset?: number
  limit?: number
}

/** Query params for GET /api/runs/{run_id}/events. */
export interface EventListParams {
  event_type?: string
  step_name?: string
  offset?: number
  limit?: number
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

/** Single step context snapshot. */
export interface ContextSnapshot {
  step_name: string
  step_number: number
  context_snapshot: Record<string, unknown>
}

/** GET /api/runs/{run_id}/context response body. */
export interface ContextEvolutionResponse {
  run_id: string
  snapshots: ContextSnapshot[]
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

/** Single item in GET /api/runs/{run_id}/steps response list. */
export interface StepListItem {
  step_name: string
  step_number: number
  execution_time_ms: number | null
  model: string | null
  created_at: string
}

/** GET /api/runs/{run_id}/steps response body. */
export interface StepListResponse {
  items: StepListItem[]
}

/** GET /api/runs/{run_id}/steps/{step_number} response body. */
export interface StepDetail {
  step_name: string
  step_number: number
  pipeline_name: string
  run_id: string
  input_hash: string
  result_data: Record<string, unknown>
  context_snapshot: Record<string, unknown>
  prompt_system_key: string | null
  prompt_user_key: string | null
  prompt_version: string | null
  model: string | null
  execution_time_ms: number | null
  created_at: string
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

/** Single event item from GET /api/runs/{run_id}/events. */
export interface EventItem {
  event_type: string
  pipeline_name: string
  run_id: string
  timestamp: string
  event_data: Record<string, unknown>
}

/** GET /api/runs/{run_id}/events response body. */
export interface EventListResponse {
  items: EventItem[]
  total: number
  offset: number
  limit: number
}

// ---------------------------------------------------------------------------
// Typed event_data interfaces
// ---------------------------------------------------------------------------

/** event_data shape for llm_call_starting events. */
export interface LLMCallStartingData {
  call_index: number
  rendered_system_prompt: string
  rendered_user_prompt: string
}

/** event_data shape for llm_call_completed events. */
export interface LLMCallCompletedData {
  call_index: number
  raw_response: string | null
  parsed_result: Record<string, unknown> | null
  model_name: string | null
  attempt_count: number
  validation_errors: string[]
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  cost_usd: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
}

/** event_data shape for context_updated events. */
export interface ContextUpdatedData {
  new_keys: string[]
  context_snapshot: Record<string, unknown>
}

/** Before/after snapshot for a single updated record. */
export interface UpdatedRecord {
  id: number | null
  before: Record<string, unknown>
  after: Record<string, unknown>
}

/** event_data shape for extraction_completed events. */
export interface ExtractionCompletedData {
  extraction_class: string
  model_class: string
  instance_count: number
  execution_time_ms: number
  created?: Record<string, unknown>[]
  updated?: UpdatedRecord[]
}

/** event_data shape for tool_call_starting events. */
export interface ToolCallStartingData {
  tool_name: string
  tool_args: Record<string, unknown>
  call_index: number
  step_name: string | null
}

/** event_data shape for tool_call_completed events. */
export interface ToolCallCompletedData {
  tool_name: string
  result_preview: string | null
  execution_time_ms: number
  call_index: number
  error: string | null
  step_name: string | null
}

// ---------------------------------------------------------------------------
// Step prompt content (GET /api/pipelines/{name}/steps/{step_name}/prompts)
// ---------------------------------------------------------------------------

/** Single prompt item within a step's prompt content response. */
export interface StepPromptItem {
  prompt_key: string
  prompt_type: string
  content: string
  required_variables: string[] | null
  version: string
}

/** GET /api/pipelines/{name}/steps/{step_name}/prompts response body. */
export interface StepPromptsResponse {
  pipeline_name: string
  step_name: string
  prompts: StepPromptItem[]
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

/** Prompt entity matching llm_pipeline/db/prompt.py SQLModel fields. */
export interface Prompt {
  id: number
  prompt_key: string
  prompt_name: string
  prompt_type: string
  category: string | null
  step_name: string | null
  content: string
  required_variables: string[] | null
  description: string | null
  version: string
  is_active: boolean
  created_at: string
  updated_at: string
  created_by: string | null
}

/** GET /api/prompts response body. */
export interface PromptListResponse {
  items: Prompt[]
  total: number
  offset: number
  limit: number
}

/** Single variant (system or user) within a grouped prompt detail response. */
export interface PromptVariant {
  id: number
  prompt_key: string
  prompt_name: string
  prompt_type: string
  category: string | null
  step_name: string | null
  content: string
  required_variables: string[] | null
  description: string | null
  version: string
  is_active: boolean
  created_at: string
  updated_at: string
  created_by: string | null
}

/** GET /api/prompts/{prompt_key} response body -- grouped wrapper with variants. */
export interface PromptDetail {
  prompt_key: string
  variants: PromptVariant[]
}

/** Query params for GET /api/prompts. All fields optional for partial filtering. */
export interface PromptListParams {
  prompt_type?: string
  category?: string
  step_name?: string
  is_active?: boolean
  offset?: number
  limit?: number
}

// ---------------------------------------------------------------------------
// Pipelines (@provisional - endpoints do not exist until task 24)
// ---------------------------------------------------------------------------

/**
 * Extraction metadata for a pipeline step.
 *
 * @provisional - shape from PipelineIntrospector.get_metadata().
 */
export interface ExtractionMetadata {
  class_name: string
  model_class: string | null
  methods: string[]
}

/**
 * Transformation metadata for a pipeline step.
 *
 * @provisional - shape from PipelineIntrospector.get_metadata().
 */
export interface TransformationMetadata {
  class_name: string
  input_type: string | null
  input_schema: Record<string, unknown> | null
  output_type: string | null
  output_schema: Record<string, unknown> | null
}

/** Individual step metadata within a pipeline strategy. */
export interface PipelineStepMetadata {
  step_name: string
  class_name: string
  system_key: string | null
  user_key: string | null
  instructions_class: string | null
  instructions_schema: Record<string, unknown> | null
  context_class: string | null
  context_schema: Record<string, unknown> | null
  extractions: ExtractionMetadata[]
  transformation: TransformationMetadata | null
  action_after: string | null
  tools?: string[]
}

/**
 * Strategy metadata within a pipeline.
 *
 * @provisional - shape from PipelineIntrospector.get_metadata().
 */
export interface PipelineStrategyMetadata {
  name: string
  display_name: string
  class_name: string
  steps: PipelineStepMetadata[]
  error: string | null
}

/**
 * Full pipeline metadata from PipelineIntrospector.get_metadata().
 *
 * @provisional - backend endpoint (GET /api/pipelines/{name}) does not
 * exist until task 24.
 */
export interface PipelineMetadata {
  pipeline_name: string
  registry_models: string[]
  strategies: PipelineStrategyMetadata[]
  execution_order: string[]
  pipeline_input_schema: Record<string, unknown> | null
}

/** Simplified pipeline list item for GET /api/pipelines. */
export interface PipelineListItem {
  name: string
  strategy_count: number | null
  step_count: number | null
  has_input_schema: boolean
  registry_model_count: number | null
  error: string | null
}

/**
 * Minimal JSON Schema type alias.
 *
 * Intentionally loose -- full JSON Schema typing is out of scope.
 * Used as the prop type for InputForm's `schema` parameter.
 */
export type JsonSchema = Record<string, unknown>

// ---------------------------------------------------------------------------
// WebSocket message types (WS /ws/runs/{run_id})
// ---------------------------------------------------------------------------

/** Server heartbeat sent every 30s on inactivity. */
export interface WsHeartbeat {
  type: 'heartbeat'
  timestamp: string
}

/** Sent when a live run's stream completes (pipeline finished). */
export interface WsStreamComplete {
  type: 'stream_complete'
  run_id: string
}

/** Sent after replaying all persisted events for a completed/failed run. */
export interface WsReplayComplete {
  type: 'replay_complete'
  run_status: string
  event_count: number
}

/** Sent on server error (e.g. run not found before close 4004). */
export interface WsError {
  type: 'error'
  detail: string
}

/**
 * Wrapper for raw pipeline events received over WebSocket.
 *
 * Adds `type: 'pipeline_event'` discriminant so WsMessage forms a proper
 * discriminated union narrowable via `switch(msg.type)`. The WebSocket
 * handler is responsible for tagging incoming EventItem payloads with
 * this type before passing them through the union.
 */
export type WsPipelineEvent = { type: 'pipeline_event' } & EventItem

/**
 * Discriminated union of all WebSocket message types.
 *
 * All members share a `type` discriminant field, enabling exhaustive
 * narrowing via `switch(msg.type)`. Raw pipeline events are wrapped
 * in WsPipelineEvent to add the missing discriminant.
 */
export type WsMessage =
  | WsHeartbeat
  | WsStreamComplete
  | WsReplayComplete
  | WsError
  | WsPipelineEvent

/**
 * Global run-creation notification received on /ws/runs.
 *
 * Standalone type -- NOT part of WsMessage union which is per-run only.
 * Used by useRunNotifications hook to detect externally-started runs.
 */
export interface WsRunCreated {
  type: 'run_created'
  run_id: string
  pipeline_name: string
  started_at: string
}

// ---------------------------------------------------------------------------
// Shared utilities
// ---------------------------------------------------------------------------

/**
 * Convert a partial filter/params object to a URL query string.
 *
 * Omits null/undefined values. Returns empty string when no params remain,
 * otherwise returns `?key=value&...` ready to append to a path.
 */
export function toSearchParams(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const filtered = Object.entries(params).filter(([, v]) => v != null)
  if (filtered.length === 0) return ''
  return '?' + new URLSearchParams(filtered.map(([k, v]) => [k, String(v)])).toString()
}

// ---------------------------------------------------------------------------
// API error
// ---------------------------------------------------------------------------

/**
 * Typed error thrown by apiClient on non-OK responses.
 * Carries HTTP status code and detail message from the backend.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/**
 * Thrown on 409 rename conflicts where the backend provides a suggested
 * alternative name. Subclass of ApiError so existing `instanceof ApiError`
 * checks still match.
 */
export class RenameConflictError extends ApiError {
  readonly suggestedName: string

  constructor(detail: string, suggestedName: string) {
    super(409, detail)
    this.name = 'RenameConflictError'
    this.suggestedName = suggestedName
  }
}
