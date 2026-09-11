/**
 * @file job.ts
 * @description Task type definitions (LLM + HTTP API)
 */

export interface LlmTask {
  id: string;
  name: string;
  model?: string;
  api_type?: string;
  target_host?: string;
  api_path?: string;
  request_payload?: string;
  field_mapping?: {
    prompt?: string;
    image?: string;
    stream_prefix?: string;
    data_format?: string;
    content?: string;
    reasoning_content?: string;
    prompt_tokens?: string;
    completion_tokens?: string;
    total_tokens?: string;
    end_prefix?: string;
    stop_flag?: string;
    end_field?: string;
  };
  concurrent_users?: number;
  spawn_rate?: number;
  dataset_id?: string;
  duration: number;
  concurrency?: number;
  chat_type?: number;
  stream_mode?: boolean;
  headers?: Array<{
    key: string;
    value: string | null;
    fixed?: boolean;
    sensitive?: boolean;
    configured?: boolean;
  }>;
  redacted_header_keys?: string[];
  has_configured_headers?: boolean;
  copy_source_task_id?: string;
  inherit_source_headers?: boolean;
  copy_policy?: {
    credentials_removed: boolean;
    credential_reuse_allowed: boolean;
    credentials_inherited_on_start?: boolean;
  };
  cookies?: Array<{
    key: string;
    value: string;
  }>;
  cert_config?: {
    cert_file?: string;
    key_file?: string;
  };
  // Stepped load configuration
  load_mode?: 'fixed' | 'stepped';
  step_start_users?: number;
  step_increment?: number;
  step_duration?: number;
  step_max_users?: number;
  step_sustain_duration?: number;
  // Warmup configuration
  warmup_enabled?: boolean;
  warmup_duration?: number;
  created_by?: string;
  test_data?: string;
  cluster_id?: string;
  engine_id?: string;
  status:
    | 'created'
    | 'queuing'
    | 'running'
    | 'stopping'
    | 'stopped'
    | 'completed'
    | 'failed'
    | 'failed_requests';
  created_at: string;
  updated_at: string;
  error_message?: string;
}

export interface HttpTask {
  id: string;
  name: string;
  method: string;
  target_url: string;
  headers?: Array<{
    key: string;
    value: string | null;
    fixed?: boolean;
    sensitive?: boolean;
    configured?: boolean;
  }>;
  redacted_header_keys?: string[];
  has_configured_headers?: boolean;
  copy_source_task_id?: string;
  inherit_source_headers?: boolean;
  copy_policy?: {
    credentials_removed: boolean;
    credential_reuse_allowed: boolean;
    credentials_inherited_on_start?: boolean;
  };
  cookies?: Array<{
    key: string;
    value: string;
  }>;
  request_body?: string;
  dataset_file?: string;
  curl_command?: string;
  success_assert?: string;
  concurrent_users: number;
  spawn_rate?: number;
  duration: number;
  // Stepped load configuration
  load_mode?: 'fixed' | 'stepped';
  step_start_users?: number;
  step_increment?: number;
  step_duration?: number;
  step_max_users?: number;
  step_sustain_duration?: number;
  created_by?: string;
  cluster_id?: string;
  engine_id?: string;
  status:
    | 'created'
    | 'queuing'
    | 'running'
    | 'stopping'
    | 'stopped'
    | 'completed'
    | 'failed'
    | 'failed_requests';
  created_at: string;
  updated_at: string;
  error_message?: string;
}

export interface AgentTask {
  id: string;
  name: string;
  protocol: 'a2a' | 'mcp';
  protocol_version: string;
  target_url: string;
  concurrent_users: number;
  spawn_rate: number;
  duration: number;
  created_by?: string;
  cluster_id?: string;
  engine_id?: string;
  status:
    | 'created'
    | 'queuing'
    | 'running'
    | 'stopping'
    | 'stopped'
    | 'completed'
    | 'failed'
    | 'failed_requests';
  error_message?: string;
  created_at: string;
  updated_at: string;
  headers?: Array<{
    key: string;
    value: string | null;
    sensitive?: boolean;
    configured?: boolean;
    required_on_copy?: boolean;
    inherited_on_start?: boolean;
  }>;
  redacted_header_keys?: string[];
  has_configured_headers?: boolean;
  dataset_configured?: boolean;
  dataset_file_name?: string | null;
  dataset_reupload_required?: boolean;
  copy_source_task_id?: string;
  inherit_source_headers?: boolean;
  inherit_source_dataset?: boolean;
  copy_policy?: {
    credentials_removed: boolean;
    credential_reuse_allowed: boolean;
    credentials_inherited_on_start?: boolean;
    dataset_inherited_on_start?: boolean;
  };
  request_timeout?: number;
  dataset_file?: string;
  a2a_mode?: 'sync' | 'stream' | 'async_poll';
  agent_card_url?: string;
  a2a_tenant?: string;
  poll_interval?: number;
  task_timeout?: number;
  a2a_scenarios?: Array<Record<string, unknown>>;
  cascade_count_paths?: string[];
  mcp_calls?: Array<Record<string, unknown>>;
  token_count_path?: string;
}

export interface AgentTaskPayload {
  name: string;
  protocol: 'a2a' | 'mcp';
  target_url: string;
  protocol_version?: string;
  headers: Array<{ key: string; value: string }>;
  duration: number;
  concurrent_users: number;
  spawn_rate: number;
  request_timeout: number;
  cluster_id: string;
  dataset_file?: string;
  copy_source_task_id?: string;
  inherit_source_headers?: boolean;
  inherit_source_dataset?: boolean;
  a2a_mode?: 'sync' | 'stream' | 'async_poll';
  agent_card_url?: string;
  a2a_tenant?: string;
  poll_interval?: number;
  task_timeout?: number;
  a2a_scenarios?: Array<Record<string, unknown>>;
  cascade_count_paths?: string[];
  mcp_calls?: Array<Record<string, unknown>>;
  token_count_path?: string;
}

/**
 * Per-metric stat snapshot used in LLM real-time charts.
 * Each key in the `metrics` dict maps a metric name (e.g. "Total_time")
 * to its avg_response_time, current_rps and current_fail_per_sec.
 */
export interface MetricEntryStat {
  avg_response_time: number;
  current_rps: number;
  current_fail_per_sec: number;
}

export interface RealtimeMetricPoint {
  timestamp: number;
  current_users: number;
  current_rps: number;
  current_fail_per_sec: number;
  avg_response_time: number;
  min_response_time: number;
  max_response_time: number;
  median_response_time: number;
  p95_response_time: number;
  total_requests: number;
  total_failures: number;
  /** Per-metric breakdown (LLM API only) */
  metrics?: Record<string, MetricEntryStat>;
}

export interface Pagination {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  statusText: string;
  pagination?: Pagination;
}

export interface Cluster {
  id: string;
  name: string;
  status: 'active' | 'inactive' | 'draining';
  online_engines: number;
  available_slots: number;
  running_tasks: number;
}

/** @deprecated Use LlmTask instead */
export type Job = LlmTask;
/** @deprecated Use HttpTask instead */
export type CommonJob = HttpTask;
