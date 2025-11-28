/**
 * @file apiClient.ts
 * @description API client for the frontend
 * @author Charm
 * @copyright 2025
 * */
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';

// Define the base API URL
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// Create an axios instance - Use a consistent BASE_URL
const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 300000, // Increase to 300 seconds (5 minutes) to match backend AI service timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

// API response interface
export interface ApiResponse<T> {
  data: T;
  status: number;
  statusText: string;
  pagination?: {
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
}

// Generic function to handle API requests
const handleRequest = async <T>(
  request: Promise<AxiosResponse>
): Promise<ApiResponse<T>> => {
  try {
    const response = await request;
    return {
      data: response.data,
      status: response.status,
      statusText: response.statusText,
      pagination: response.data.pagination,
    };
  } catch (error: any) {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      throw {
        data: error.response.data,
        status: error.response.status,
        statusText: error.response.statusText,
      };
    } else if (error.request) {
      // The request was made but no response was received
      throw {
        data: null,
        status: 0,
        statusText: 'No response received from server',
      };
    } else {
      // Something happened in setting up the request that triggered an Error
      throw {
        data: null,
        status: 0,
        statusText: error.message || 'Unknown error occurred',
      };
    }
  }
};

// Add a response interceptor
apiClient.interceptors.response.use(
  response => {
    // Handle successful responses
    return response;
  },
  error => {
    // Special handling for 304 status code
    if (error.response && error.response.status === 304) {
      // For a 304 response, do not treat it as an error, but return a successful response with empty data
      return {
        data: { data: [], status: 'cached' },
        status: 200,
        statusText: 'OK (From Cache)',
        headers: error.response.headers,
        config: error.config,
      };
    }

    // Reject other errors normally
    return Promise.reject(error);
  }
);

// API client methods
export const api = {
  get: <T>(url: string, config?: AxiosRequestConfig) =>
    handleRequest<T>(apiClient.get(url, config)),

  post: <T>(url: string, data?: any, config?: AxiosRequestConfig) =>
    handleRequest<T>(apiClient.post(url, data, config)),

  put: <T>(url: string, data?: any, config?: AxiosRequestConfig) =>
    handleRequest<T>(apiClient.put(url, data, config)),

  delete: <T>(url: string, config?: AxiosRequestConfig) =>
    handleRequest<T>(apiClient.delete(url, config)),

  // Special method for file upload
  uploadFile: <T>(
    url: string,
    formData: FormData,
    config?: AxiosRequestConfig
  ) => {
    const uploadConfig = {
      ...config,
      headers: {
        ...config?.headers,
        'Content-Type': 'multipart/form-data',
      },
    };
    return handleRequest<T>(apiClient.post(url, formData, uploadConfig));
  },
};

// Add file upload method
export const uploadFiles = async (
  files: FormData,
  file_type: string,
  taskId: string,
  certType?: string
) => {
  // Ensure taskId is not empty
  if (!taskId) {
    taskId = `temp-${Date.now()}`;
  }

  // Validate taskId format (alphanumeric with hyphens and underscores only)
  const taskIdRegex = /^[a-zA-Z0-9_-]+$/;
  if (!taskIdRegex.test(taskId)) {
    throw new Error(
      'Invalid task ID format. Only alphanumeric characters, hyphens, and underscores are allowed.'
    );
  }

  let url = `${BASE_URL}/upload?file_type=${file_type}&task_id=${encodeURIComponent(taskId)}`;

  // If a certificate type is provided, add it to the URL
  if (certType) {
    url += `&cert_type=${encodeURIComponent(certType)}`;
  }

  const response = await fetch(url, {
    method: 'POST',
    body: files,
    // Do not set Content-Type, let the browser automatically set multipart/form-data with a boundary
  });

  if (!response.ok) {
    const errorText = await response.text();
    let errorMessage = `Upload failed: ${response.status} ${response.statusText}`;
    let errorPayload: any = null;

    try {
      errorPayload = JSON.parse(errorText);
      const detail = errorPayload?.detail;
      if (Array.isArray(detail)) {
        errorMessage =
          detail
            .map(item => {
              if (!item) {
                return '';
              }
              if (typeof item === 'string') {
                return item;
              }
              const { msg }: { msg?: string } = item;
              if (msg) {
                if (/Expected UploadFile/i.test(msg)) {
                  return 'Server did not receive the uploaded file. Please reselect the file and try again.';
                }
                return msg;
              }
              if (item.message) {
                return item.message;
              }
              if (item.type) {
                return `${item.type}`;
              }
              return JSON.stringify(item);
            })
            .filter(Boolean)
            .join('; ') || errorMessage;
      } else if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (detail?.msg) {
        const { msg }: { msg: string } = detail;
        errorMessage = /Expected UploadFile/i.test(msg)
          ? 'Server did not receive the uploaded file. Please reselect the file and try again.'
          : msg;
      } else if (typeof errorPayload?.error === 'string') {
        const errMsg = errorPayload.error;
        errorMessage = /Expected UploadFile/i.test(errMsg)
          ? 'Server did not receive the uploaded file. Please reselect the file and try again.'
          : errMsg;
      }
    } catch {
      // If not JSON, use the text as is
      errorMessage = errorText?.trim() || errorMessage;
    }

    const error = new Error(errorMessage) as Error & {
      status?: number;
      responseData?: unknown;
      raw?: string;
    };
    error.status = response.status;
    error.responseData = errorPayload ?? errorText;
    error.raw = errorText;
    throw error;
  }

  return response.json();
};

export default api;
