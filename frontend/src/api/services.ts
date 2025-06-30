/**
 * @file services.ts
 * @description API services for the frontend
 * @author Charm
 * @copyright 2025
 * */

import { BenchmarkJob, BenchmarkResult, Dataset } from '../types';
import api, { uploadFiles } from './apiClient';

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

// Benchmark Job API methods
export const benchmarkJobApi = {
  // Get all benchmark jobs
  getAllJobs: (status?: string, limit?: number, skip?: number) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (limit) params.append('limit', limit.toString());
    if (skip) params.append('skip', skip.toString());

    return api.get<BenchmarkJob[]>(`/tasks?${params.toString()}`);
  },

  // Get a specific benchmark job by ID
  getJob: (id: string) => api.get<BenchmarkJob>(`/tasks/${id}`),

  // Get only the status of a specific benchmark job by ID (lightweight)
  getJobStatus: (id: string) =>
    api.get<{
      id: string;
      name: string;
      status: string;
      error_message?: string;
      updated_at?: string;
    }>(`/tasks/${id}/status`),

  // Create a new benchmark job
  createJob: (
    data: Omit<
      BenchmarkJob,
      'id' | 'created_at' | 'updated_at' | 'status' | 'result_id'
    >
  ) => api.post<BenchmarkJob>('/tasks', data),

  // Update a benchmark job
  updateJob: (id: string, data: Partial<BenchmarkJob>) =>
    api.put<BenchmarkJob>(`/tasks/${id}`, data),

  // Delete a benchmark job
  deleteJob: (id: string) => api.delete<void>(`/tasks/${id}`),

  // Stop a running benchmark job
  stopJob: (id: string) => api.post<BenchmarkJob>(`/tasks/stop/${id}`),

  // Test API endpoint
  testApiEndpoint: (data: any) => api.post<any>('/tasks/test', data),
};

// Results API methods
export const resultApi = {
  // Get all results
  getAllResults: (benchmarkJobId?: string, limit?: number, skip?: number) => {
    const params = new URLSearchParams();
    if (benchmarkJobId) params.append('benchmark_job_id', benchmarkJobId);
    if (limit) params.append('limit', limit.toString());
    if (skip) params.append('skip', skip.toString());

    return api.get<BenchmarkResult[]>(`/results?${params.toString()}`);
  },

  // Get a specific result by ID
  getResult: (id: string) => api.get<BenchmarkResult>(`/results/${id}`),

  // Get the result for a specific benchmark job
  getJobResult: (jobId: string) => api.get<any>(`/tasks/${jobId}/results`),
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
    }>('/tasks/comparison/available'),

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
        avg_total_tpr: number;
        avg_completion_tpr: number;
        avg_response_time: number;
        rps: number;
      }>;
      status: string;
      error?: string;
    }>('/tasks/comparison', { selected_tasks: selectedTasks }),
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

// System API methods
export const systemApi = {};

// Define the upload service
export const uploadCertificateFiles = async (
  certFile: File | null,
  keyFile: File | null,
  taskId: string,
  certType: string = 'combined'
) => {
  if (!taskId) {
    taskId = `temp-${Date.now()}`;
  }

  // Process upload based on certificate type
  if (certType === 'combined' && certFile) {
    // Combined certificate mode
    const formData = new FormData();
    formData.append('file', certFile);
    return uploadFiles(formData, 'cert', taskId, certType);
  }
  if (certType === 'separate') {
    // Separate upload mode
    let certConfig = {};

    // If there is a certificate file, upload it first
    if (certFile) {
      const certFormData = new FormData();
      certFormData.append('file', certFile);
      const certResult = await uploadFiles(
        certFormData,
        'cert',
        taskId,
        'cert_file'
      );
      certConfig = certResult.cert_config;
    }

    // If there is a key file, upload it
    if (keyFile) {
      const keyFormData = new FormData();
      keyFormData.append('file', keyFile);
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
