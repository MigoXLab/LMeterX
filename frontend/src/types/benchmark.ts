/**
 * @file benchmark.ts
 * @description Benchmark job type definitions
 * @author Charm
 * @copyright 2025
 */
export interface BenchmarkJob {
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
    value: string;
  }>;
  cookies?: Array<{
    key: string;
    value: string;
  }>;
  cert_config?: {
    cert_file?: string;
    key_file?: string;
  };
  test_data?: string;
  status:
    | 'pending'
    | 'running'
    | 'completed'
    | 'failed'
    | 'failed_requests'
    | 'stopped'
    | 'created'
    | 'idle';
  created_at: string;
  updated_at: string;
  error_message?: string;
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
