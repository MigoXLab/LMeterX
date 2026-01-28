/**
 * @file request.ts
 * @description Request utility for the frontend
 * @author Charm
 * @copyright 2025
 */
import { message } from 'antd';
import axios from 'axios';
import { getApiBaseUrl } from './runtimeConfig';

// Create axios instance
const request = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 300000, // Increase to 300 seconds (5 minutes) to match backend AI service timeout
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    Pragma: 'no-cache',
    Expires: '0',
  },
});

// Add request interceptor
request.interceptors.request.use(
  config => {
    // Add timestamp to prevent caching
    if (config.method === 'get') {
      config.params = {
        ...config.params,
        _t: new Date().getTime(),
      };
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// Add response interceptor
request.interceptors.response.use(
  response => {
    return response.data;
  },
  error => {
    // Log error details for debugging
    console.error('Request error:', error);

    // Don't show generic error messages here - let specific components handle their own errors
    // This allows components to extract and display backend error messages

    // Only handle truly generic network errors that don't have response data
    if (
      !error.response &&
      error.code === 'ECONNABORTED' &&
      error.message.includes('timeout')
    ) {
      // Only show generic timeout message if there's no backend response
      message.error('Network timeout, please check your connection');
    }

    return Promise.reject(error);
  }
);

export default request;
