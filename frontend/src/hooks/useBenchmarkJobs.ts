/**
 * @file useBenchmarkJobs.ts
 * @description Custom hook for managing benchmark jobs
 * @author Charm
 * @copyright 2025
 * */
import type { MessageInstance } from 'antd/es/message/interface';
import axios from 'axios';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pagination as ApiPagination, BenchmarkJob } from '../types/benchmark';

// Frontend pagination state uses Ant Design's format
interface AntdPagination {
  current: number;
  pageSize: number;
  total: number;
}

const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export const useBenchmarkJobs = (messageApi: MessageInstance) => {
  const [jobs, setJobs] = useState<BenchmarkJob[]>([]);
  const [pagination, setPagination] = useState<AntdPagination>({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshTime, setLastRefreshTime] = useState<Date | null>(null);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const pollingTimerRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fetchingRef = useRef(false);
  const initialLoadDoneRef = useRef(false);

  const fetchJobs = useCallback(
    async (isManualRefresh = false) => {
      if (fetchingRef.current && !isManualRefresh) return;

      setLoading(true);
      fetchingRef.current = true;
      setError(null);

      try {
        const response = await axios.get<{
          data: BenchmarkJob[];
          pagination?: ApiPagination;
          total?: number;
        }>(`${VITE_API_BASE_URL}/tasks`, {
          params: {
            page: pagination.current,
            pageSize: pagination.pageSize,
            ...(statusFilter && { status: statusFilter }),
            ...(searchText && { search: searchText }),
            _t: Date.now(),
          },
          headers: {
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
            Expires: '0',
          },
        });

        if (response.status === 200 && response.data) {
          const { data, pagination: respPagination } = response.data;
          const jobData = Array.isArray(data) ? data : [];
          setJobs(jobData);

          if (respPagination) {
            setPagination(prev => ({
              ...prev,
              total: respPagination.total || 0,
              current: respPagination.page || prev.current,
              pageSize: respPagination.page_size || prev.pageSize,
            }));
          } else if (response.data.total) {
            // Fallback for other pagination formats
            setPagination(prev => ({
              ...prev,
              total: response.data.total || 0,
            }));
          } else if (response.headers['x-total-count']) {
            // Fallback for older API
            setPagination(prev => ({
              ...prev,
              total: parseInt(response.headers['x-total-count'], 10) || 0,
            }));
          }
          setLastRefreshTime(new Date());
        }
      } catch (err) {
        // Failed to fetch tasks
        setError('Failed to fetch task list, please try again later');
      } finally {
        setLoading(false);
        fetchingRef.current = false;
        if (!initialLoadDoneRef.current) {
          initialLoadDoneRef.current = true;
        }
      }
    },
    [pagination.current, pagination.pageSize, statusFilter, searchText]
  );

  const fetchJobStatuses = useCallback(async () => {
    const hasRunningTasks = jobs.some(job =>
      ['running', 'pending', 'created', 'queued'].includes(
        job.status?.toLowerCase() || ''
      )
    );

    if (!hasRunningTasks || fetchingRef.current) {
      return;
    }

    fetchingRef.current = true;
    setRefreshing(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await axios.get(`${VITE_API_BASE_URL}/tasks/status`, {
        signal: controller.signal,
        timeout: 15000,
      });

      if (controller.signal.aborted) return;

      if (response.status === 200 && response.data) {
        const statusUpdates = Array.isArray(response.data.data)
          ? response.data.data
          : Array.isArray(response.data)
            ? response.data
            : [];
        if (statusUpdates.length > 0) {
          const statusMap = statusUpdates.reduce(
            (acc, update) => {
              if (update && update.id) {
                acc[update.id] = update.status.toLowerCase();
              }
              return acc;
            },
            {} as Record<string, string>
          );

          let hasChanges = false;
          const updatedJobs = jobs.map(job => {
            const newStatus = statusMap[job.id];
            if (newStatus && newStatus !== job.status?.toLowerCase()) {
              hasChanges = true;
              return {
                ...job,
                status: newStatus,
                updated_at: new Date().toISOString(),
              };
            }
            return job;
          });

          if (hasChanges) {
            setJobs(updatedJobs);
            setLastRefreshTime(new Date());
          }
        }
      }
    } catch (error) {
      // Status update request failed
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      fetchingRef.current = false;
      setRefreshing(false);
    }
  }, [jobs]);

  const stopPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
      try {
        localStorage.removeItem('benchmark_polling_active');
      } catch (e) {
        // localStorage error in stopPolling cleanup
      }
    }
  }, []);

  const startPolling = useCallback(() => {
    if (
      pollingTimerRef.current !== null ||
      document.visibilityState !== 'visible'
    ) {
      return;
    }

    const hasRunningTasks = jobs.some(job =>
      ['running', 'pending', 'created', 'queued'].includes(
        job.status?.toLowerCase() || ''
      )
    );

    if (!hasRunningTasks) {
      return;
    }

    try {
      const now = Date.now();
      const existingPollingTimestamp = parseInt(
        localStorage.getItem('benchmark_polling_timestamp') || '0'
      );
      if (now - existingPollingTimestamp < 25000) {
        // Slightly less than interval
        return; // Another tab is polling
      }
      localStorage.setItem('benchmark_polling_timestamp', now.toString());
      localStorage.setItem('benchmark_polling_active', 'true');
    } catch (e) {
      // Could not set localStorage for polling coordination
    }

    const pollingInterval = 30000;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') {
        stopPolling();
        return;
      }
      try {
        // Keep alive for this tab
        localStorage.setItem(
          'benchmark_polling_timestamp',
          Date.now().toString()
        );
      } catch (e) {
        /* ignore */
      }
      fetchJobStatuses();
    }, pollingInterval);
    pollingTimerRef.current = intervalId;
  }, [jobs, fetchJobStatuses, stopPolling]);

  // Main data fetching effect
  useEffect(() => {
    // No dependency array, runs once on mount
    fetchJobs();
  }, []);

  // Effect for re-fetching when filters or pagination change
  useEffect(() => {
    if (!initialLoadDoneRef.current) {
      return; // Don't fetch on initial mount, the above effect handles it
    }
    fetchJobs();
  }, [
    pagination.current,
    pagination.pageSize,
    statusFilter,
    searchText,
    fetchJobs,
  ]);

  // Polling lifecycle management
  useEffect(() => {
    const hasRunningTasks = jobs.some(job =>
      ['running', 'pending', 'created', 'queued'].includes(
        job.status?.toLowerCase() || ''
      )
    );

    if (hasRunningTasks) {
      startPolling();
    } else {
      stopPolling();
    }

    return () => stopPolling();
  }, [jobs, startPolling, stopPolling]);

  // Page visibility handler
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const lastRefresh = lastRefreshTime?.getTime() || 0;
        if (Date.now() - lastRefresh > 30000) {
          fetchJobs(true); // Force refresh
        } else {
          startPolling();
        }
      } else {
        stopPolling();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [startPolling, stopPolling, fetchJobs, lastRefreshTime]);

  const createJob = useCallback(
    async (
      values: Omit<BenchmarkJob, 'id' | 'status' | 'created_at' | 'updated_at'>
    ) => {
      setLoading(true);
      try {
        const response = await axios.post(`${VITE_API_BASE_URL}/tasks`, values);
        if (response.data?.task_id) {
          messageApi.success('Created successfully');
          await fetchJobs(true); // Refresh list to show the new job
          return true;
        }
        messageApi.error('Failed to create task: Unable to get task ID');
        return false;
      } catch (error: any) {
        const errorMsg = error.response?.data?.error || 'Failed to create task';
        messageApi.error(`Failed to create task: ${errorMsg}`);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchJobs, messageApi]
  );

  const stopJob = useCallback(
    async (jobId: string) => {
      messageApi.loading({ content: 'Stopping task...', key: jobId });
      try {
        await axios.post(`${VITE_API_BASE_URL}/tasks/stop/${jobId}`);
        messageApi.success({ content: 'Task is being stopped...', key: jobId });
        setTimeout(() => fetchJobs(true), 1000); // Refresh list after a short delay
      } catch (error: any) {
        const errorMsg = error.response?.data?.message || 'Failed to stop task';
        messageApi.error({ content: errorMsg, key: jobId });
      }
    },
    [fetchJobs, messageApi]
  );

  const setSearchTextWithReset = useCallback(
    (text: string) => {
      setSearchText(text);
      // Reset pagination to first page when searching
      if (text !== searchText) {
        setPagination(prev => ({
          ...prev,
          current: 1,
        }));
      }
    },
    [searchText]
  );

  const filteredJobs = useMemo(() => {
    if (!searchText) return jobs;
    return jobs.filter(job => {
      const search = searchText.toLowerCase();
      return (
        (job.id || '').toLowerCase().includes(search) ||
        (job.name || '').toLowerCase().includes(search) ||
        (job.model || '').toLowerCase().includes(search)
      );
    });
  }, [jobs, searchText]);

  return {
    jobs,
    filteredJobs,
    pagination,
    setPagination,
    loading,
    refreshing,
    error,
    lastRefreshTime,
    createJob,
    stopJob,
    manualRefresh: () => fetchJobs(true),
    setSearchText: setSearchTextWithReset,
    setStatusFilter,
  };
};
