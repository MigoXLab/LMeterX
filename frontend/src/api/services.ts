/**
 * @file services.ts
 * @description API services for the frontend
 * @author Charm
 * @copyright 2025
 * */

import { Dataset } from '../types';
import { LoginResponse, UserInfo } from '../types/auth';
import { HttpTask, LlmTask } from '../types/job';
import api, { uploadFiles } from './apiClient';

type BasicFileLike =
  | File
  | Blob
  | {
      originFileObj?: File;
      file?: File;
      blobFile?: Blob;
      name?: string;
    }
  | FileList
  | null
  | undefined;

type FileLike = BasicFileLike | BasicFileLike[];

const isFileList = (
  value: BasicFileLike | BasicFileLike[]
): value is FileList => {
  return (
    typeof FileList !== 'undefined' &&
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    'length' in value &&
    typeof (value as FileList).item === 'function'
  );
};

const extractFile = (fileLike: FileLike): File => {
  if (!fileLike) {
    throw new Error(
      'No file provided. Please reselect the file and try again.'
    );
  }

  if (fileLike instanceof File) {
    return fileLike;
  }

  if (fileLike instanceof Blob) {
    return new File([fileLike], 'upload.bin', { type: fileLike.type });
  }

  if (isFileList(fileLike)) {
    if (!fileLike.length) {
      throw new Error(
        'No file provided. Please reselect the file and try again.'
      );
    }
    return extractFile(fileLike[0]);
  }

  if (Array.isArray(fileLike)) {
    if (!fileLike.length) {
      throw new Error(
        'No file provided. Please reselect the file and try again.'
      );
    }
    return extractFile(fileLike[0]);
  }

  const possibleFile =
    (fileLike as any)?.originFileObj ??
    (fileLike as any)?.file ??
    (fileLike as any)?.blobFile;

  if (possibleFile instanceof File) {
    return possibleFile;
  }

  if (possibleFile instanceof Blob) {
    const name = (fileLike as any)?.name || 'upload.bin';
    return new File([possibleFile], name, { type: possibleFile.type });
  }

  throw new Error(
    'Invalid file data received. Please remove the file and select it again.'
  );
};

// Dataset API methods
export const datasetApi = {
  // Get all datasets
  getAllDatasets: () => api.get<Dataset[]>('/datasets'),

  // Get a specific dataset by ID
  getDataset: (id: string) => api.get<Dataset>(`/datasets/${id}`),

  // Create a new dataset
  createDataset: (formData: FormData) =>
    api.uploadFile<Dataset>('/datasets', formData),

  // Update a dataset
  updateDataset: (id: string, data: Partial<Dataset>) =>
    api.put<Dataset>(`/datasets/${id}`, data),

  // Delete a dataset
  deleteDataset: (id: string) => api.delete<void>(`/datasets/${id}`),
};

// LLM Task API methods
export const llmTaskApi = {
  // Get all LLM tasks
  getAllJobs: (status?: string, limit?: number, skip?: number) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (limit) params.append('limit', limit.toString());
    if (skip) params.append('skip', skip.toString());

    return api.get<LlmTask[]>(`/llm-tasks?${params.toString()}`);
  },

  // Get a specific task by ID
  getJob: (id: string) => api.get<LlmTask>(`/llm-tasks/${id}`),

  // Get only the status of a specific task by ID (lightweight)
  getJobStatus: (id: string) =>
    api.get<{
      id: string;
      name: string;
      status: string;
      error_message?: string;
      updated_at?: string;
    }>(`/llm-tasks/${id}/status`),

  // Create a new task
  createJob: (
    data: Omit<
      LlmTask,
      'id' | 'created_at' | 'updated_at' | 'status' | 'result_id'
    >
  ) => api.post<LlmTask>('/llm-tasks', data),

  // Update a task
  updateJob: (id: string, data: Partial<LlmTask>) =>
    api.put<LlmTask>(`/llm-tasks/${id}`, data),

  // Delete a task
  deleteJob: (id: string) => api.delete<void>(`/llm-tasks/${id}`),

  // Stop a running task
  stopJob: (id: string) => api.post<LlmTask>(`/llm-tasks/stop/${id}`),

  // Test API endpoint
  testApiEndpoint: (data: any) => api.post<any>('/llm-tasks/test', data),

  // Get real-time performance metrics for a running task (incremental fetch)
  getRealtimeMetrics: (jobId: string, since: number = 0) =>
    api.get<{ status: string; data: any[]; error?: string }>(
      `/llm-tasks/${jobId}/realtime-metrics`,
      { params: { since } }
    ),
};

/** @deprecated Use llmTaskApi instead */
export const jobApi = llmTaskApi;

// HTTP Task API methods
export const httpTaskApi = {
  getAllJobs: (status?: string, limit?: number, skip?: number) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (limit) params.append('limit', limit.toString());
    if (skip) params.append('skip', skip.toString());

    return api.get<HttpTask[]>(`/http-tasks?${params.toString()}`);
  },

  getJob: (id: string) => api.get(`/http-tasks/${id}`),

  getJobStatus: (id: string) => api.get(`/http-tasks/${id}/status`),

  createJob: (data: any) => api.post<HttpTask>('/http-tasks', data),

  updateJob: (id: string, data: Partial<HttpTask>) =>
    api.put<HttpTask>(`/http-tasks/${id}`, data),

  deleteJob: (id: string) => api.delete<void>(`/http-tasks/${id}`),

  testJob: (data: any) => api.post('/http-tasks/test', data),

  stopJob: (id: string) => api.post<HttpTask>(`/http-tasks/stop/${id}`),

  getJobResult: (jobId: string) => api.get(`/http-tasks/${jobId}/results`),

  // Get real-time performance metrics for a running task (incremental fetch)
  getRealtimeMetrics: (jobId: string, since: number = 0) =>
    api.get<{ status: string; data: any[]; error?: string }>(
      `/http-tasks/${jobId}/realtime-metrics`,
      { params: { since } }
    ),
};

/** @deprecated Use httpTaskApi instead */
/** @deprecated Use httpTaskApi instead */
/** @deprecated Use httpTaskApi instead */
export const commonJobApi = httpTaskApi;

// Results API methods
export const resultApi = {
  // Legacy wrapper: backend no longer provides a generic /results list route.
  // Use task_id when available and resolve to the canonical LLM task result API.
  getAllResults: (JobId?: string, _limit?: number, _skip?: number) => {
    if (!JobId) {
      return Promise.reject(
        new Error(
          'getAllResults requires job_id. Use resultApi.getJobResult(taskId) or llmTaskApi.getAllJobs().'
        )
      );
    }
    const params = new URLSearchParams();
    if (typeof _limit === 'number') params.append('limit', _limit.toString());
    if (typeof _skip === 'number') params.append('skip', _skip.toString());
    const query = params.toString();
    const path = query
      ? `/llm-tasks/${JobId}/results?${query}`
      : `/llm-tasks/${JobId}/results`;
    return api.get<any>(path);
  },

  // Legacy wrapper: kept for compatibility, id is treated as task_id.
  getResult: (id: string) => api.get<any>(`/llm-tasks/${id}/results`),

  // Get the result for a specific job
  getJobResult: (jobId: string) => api.get<any>(`/llm-tasks/${jobId}/results`),
};

// Performance Comparison API methods
export const comparisonApi = {
  // Get available model tasks for comparison
  getAvailableModelTasks: () =>
    api.get<{
      data: Array<{
        model_name: string;
        concurrent_users: number;
        task_id: string;
        task_name: string;
        created_at: string;
      }>;
      status: string;
      error?: string;
    }>('/llm-tasks/comparison/available'),

  // Compare performance metrics for selected tasks
  comparePerformance: (selectedTasks: string[]) =>
    api.post<{
      data: Array<{
        task_id: string;
        model_name: string;
        concurrent_users: number;
        task_name: string;
        ttft: number;
        total_tps: number;
        completion_tps: number;
        avg_total_token_per_req: number;
        avg_completion_token_per_req: number;
        avg_response_time: number;
        rps: number;
      }>;
      status: string;
      error?: string;
    }>('/llm-tasks/comparison', { selected_tasks: selectedTasks }),

  // Get available HTTP API tasks for comparison
  getAvailableHttpTasks: () =>
    api.get<{
      data: Array<{
        task_id: string;
        task_name: string;
        method: string;
        target_url: string;
        concurrent_users: number;
        created_at: string;
        duration: number;
      }>;
      status: string;
      error?: string;
    }>('/http-tasks/comparison/available'),

  // Compare performance metrics for HTTP API tasks
  compareHttpPerformance: (selectedTasks: string[]) =>
    api.post<{
      data: Array<{
        task_id: string;
        task_name: string;
        method: string;
        target_url: string;
        concurrent_users: number;
        duration: string;
        request_count: number;
        failure_count: number;
        success_rate: number;
        rps: number;
        avg_response_time: number;
        p95_response_time: number;
        min_response_time: number;
        max_response_time: number;
        avg_content_length: number;
      }>;
      status: string;
      error?: string;
    }>('/http-tasks/comparison', { selected_tasks: selectedTasks }),
};

// Skills API (Web URL analysis)
export const skillApi = {
  /** Analyze a webpage URL to discover business APIs and generate loadtest configs. */
  analyzeUrl: (data: {
    target_url: string;
    cookies?: Array<{ name: string; value: string }>;
    headers?: Array<{ name: string; value: string }>;
    wait_seconds?: number;
    scroll?: boolean;
    concurrent_users?: number;
    duration?: number;
    spawn_rate?: number;
  }) =>
    api.post<{
      status: string;
      message: string;
      target_url: string;
      analysis_summary: string;
      discovered_apis: Array<{
        name: string;
        target_url: string;
        method: string;
        headers: Array<{ key: string; value: string }>;
        request_body: string | null;
        http_status: number | null;
        source: string;
        confidence: string;
      }>;
      loadtest_configs: Array<{
        temp_task_id: string;
        name: string;
        method: string;
        target_url: string;
        headers: Array<{ key: string; value: string }>;
        cookies: Array<{ key: string; value: string }>;
        request_body: string;
        concurrent_users: number;
        duration: number;
        spawn_rate: number;
        load_mode: string;
      }>;
      llm_used: boolean;
    }>('/skills/analyze-url', data, {
      timeout: 120000, // 2 minutes timeout for page analysis
    }),
};

// Get log content (supports incremental fetching)
export const logApi = {
  getServiceLogContent: (
    serviceName: string,
    offset: number = 0,
    tail: number = 0
  ) => api.get<any>(`/logs/${serviceName}`, { params: { offset, tail } }),

  getTaskLogContent: (taskId: string, offset: number = 0, tail: number = 0) =>
    api.get<any>(`/logs/task/${taskId}`, { params: { offset, tail } }),
};

// Analysis API methods
export const analysisApi = {
  // Perform AI analysis on task results (single or multiple tasks)
  analyzeTasks: (taskIds: string[], language?: string) =>
    api.post<{
      task_ids: string[];
      analysis_report: string;
      status: string;
      error_message?: string;
      created_at: string;
    }>(
      '/analyze',
      {
        task_ids: taskIds,
        language: language || 'en',
      },
      {
        timeout: 300000, // 5 minutes timeout for AI analysis
      }
    ),

  // Get analysis result for a task
  getAnalysis: (taskId: string) =>
    api.get<{
      data?: {
        task_ids: string[];
        analysis_report: string;
        status: string;
        error_message?: string;
        created_at: string;
      };
      status: string;
      error?: string;
    }>(`/analyze/${taskId}`, {
      timeout: 300000, // 5 minutes timeout for getting analysis result
    }),
};

// Auth API methods
export const authApi = {
  login: (username: string, password: string) =>
    api.post<LoginResponse>('/auth/login', { username, password }),
  me: () => api.get<UserInfo>('/auth/profile'),
  logout: () => api.post<void>('/auth/logout'),
};

// System Configuration API methods
export const systemApi = {
  // Get all system configurations
  getSystemConfigs: () => api.get<any>('/system'),

  // Create a new system configuration
  createSystemConfig: (config: {
    config_key: string;
    config_value: string;
    description?: string;
  }) => api.post<any>('/system', config),

  // Update a system configuration
  updateSystemConfig: (
    configKey: string,
    config: {
      config_key: string;
      config_value: string;
      description?: string;
    }
  ) => api.put<any>(`/system/${configKey}`, config),

  // Batch create or update system configurations
  batchUpsertSystemConfigs: (
    configs: Array<{
      config_key: string;
      config_value: string;
      description?: string;
    }>
  ) => api.post<any>('/system/batch', { configs }),

  // Delete a system configuration
  deleteSystemConfig: (configKey: string) =>
    api.delete<any>(`/system/${configKey}`),

  // Get AI service configuration
  getAIServiceConfig: () => api.get<any>('/system/ai-service'),
} as const;

// Monitoring API methods (Engine resource metrics from VictoriaMetrics)
export const monitoringApi = {
  /** List engines that have reported metrics recently. */
  getEngines: () =>
    api.get<{
      status: string;
      data: Array<{
        engine_id: string;
        last_seen: number;
        cpu_percent: number;
      }>;
    }>('/monitoring/engines'),

  /** Get Engine system resource metrics (CPU, Memory, Network). */
  getEngineResources: (params: {
    engine_id?: string;
    start?: number;
    end?: number;
    max_points?: number;
  }) =>
    api.get<{
      status: string;
      data: Record<
        string,
        Array<{
          metric: Record<string, string>;
          values: Array<[number, number]>;
        }>
      >;
    }>('/monitoring/engine-resources', { params }),

  /** Get task performance metrics from VictoriaMetrics. */
  getTaskMetrics: (
    taskId: string,
    since: number = 0,
    maxPoints: number = 1200
  ) =>
    api.get<{ status: string; data: any[] }>(
      `/monitoring/task-metrics/${taskId}`,
      { params: { since, max_points: maxPoints } }
    ),
};

// Define the upload service
export const uploadCertificateFiles = async (
  certFile: FileLike,
  keyFile: FileLike,
  taskId: string,
  certType: string = 'combined'
) => {
  if (!taskId) {
    taskId = `temp-${Date.now()}`;
  }

  // Process upload based on certificate type
  const normalizedCertFile = certFile ? extractFile(certFile) : null;
  const normalizedKeyFile = keyFile ? extractFile(keyFile) : null;

  if (certType === 'combined' && normalizedCertFile) {
    // Combined certificate mode
    const formData = new FormData();
    formData.append('files', normalizedCertFile, normalizedCertFile.name);
    return uploadFiles(formData, 'cert', taskId, certType);
  }
  if (certType === 'separate') {
    // Separate upload mode
    let certConfig = {};

    // If there is a certificate file, upload it first
    if (normalizedCertFile) {
      const certFormData = new FormData();
      certFormData.append('files', normalizedCertFile, normalizedCertFile.name);
      const certResult = await uploadFiles(
        certFormData,
        'cert',
        taskId,
        'cert_file'
      );
      certConfig = certResult.cert_config;
    }

    // If there is a key file, upload it
    if (normalizedKeyFile) {
      const keyFormData = new FormData();
      keyFormData.append('files', normalizedKeyFile, normalizedKeyFile.name);
      const keyResult = await uploadFiles(
        keyFormData,
        'cert',
        taskId,
        'key_file'
      );
      certConfig = keyResult.cert_config; // Use the final configuration
    }

    return { cert_config: certConfig };
  }

  throw new Error('Invalid certificate type or file');
};

// Upload dataset file
export const uploadDatasetFile = async (
  datasetFile: FileLike,
  taskId: string
) => {
  if (!taskId) {
    taskId = `temp-${Date.now()}`;
  }

  const normalizedDatasetFile = extractFile(datasetFile);
  const formData = new FormData();
  formData.append('files', normalizedDatasetFile, normalizedDatasetFile.name);
  return uploadFiles(formData, 'dataset', taskId);
};
