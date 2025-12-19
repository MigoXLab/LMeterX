/**
 * @file index.ts
 * @description Type definitions for the frontend
 * @author Charm
 * @copyright 2025
 */

// Dataset Types
export interface Dataset {
  _id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  file_name: string;
  object_name: string;
  prompt_count: number;
}

// Job status/types (legacy)
export enum JobStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  STOPPED = 'stopped',
}

export interface JobConfigLegacy {
  _id: string;
  name: string;
  description?: string;
  dataset_id: string;
  llm_service_url: string;
  api_key?: string;
  headers?: Record<string, string>;
  stream: boolean;
  model?: string;
  users: number;
  spawn_rate: number;
  run_time?: string;
  headless: boolean;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  result_id?: string;
  error_message?: string;
  additional_params?: Record<string, any>;
}

export interface RequestStats {
  total_requests: number;
  success_requests: number;
  failure_requests: number;
  avg_response_time_ms: number;
  min_response_time_ms: number;
  max_response_time_ms: number;
  median_response_time_ms: number;
  p95_response_time_ms: number;
  p99_response_time_ms: number;
  rps: number;
}

export interface TokenStats {
  total_tokens: number;
  completion_tokens: number;
  prompt_tokens: number;
  tokens_per_second: number;
}

export interface JobResultsLegacy {
  start_time: string;
  end_time: string;
  duration_seconds: number;
  first_token?: RequestStats;
  generation_time?: RequestStats;
  completed?: RequestStats;
  token_stats?: TokenStats;
  metrics?: Record<string, any>;
  errors?: Array<Record<string, any>>;
}

export interface JobResultLegacy {
  _id: string;
  job_id: string;
  created_at: string;
  results: JobResultsLegacy;
  job_config: JobConfigLegacy;
}
