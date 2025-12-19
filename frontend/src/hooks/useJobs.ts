/**
 * @file useJobs.ts
 * @description Custom hook for managing jobs
 */
import type { MessageInstance } from 'antd/es/message/interface';
import axios from 'axios';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pagination as ApiPagination, Job } from '../types/job';

interface AntdPagination {
  current: number;
  pageSize: number;
  total: number;
}

const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export const useJobs = (messageApi: MessageInstance) => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<Job[]>([]);
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
  const [searchInput, setSearchInput] = useState('');
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
          data: Job[];
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
            setPagination(prev => ({
              ...prev,
              total: response.data.total || 0,
            }));
          } else if (response.headers['x-total-count']) {
            setPagination(prev => ({
              ...prev,
              total: parseInt(response.headers['x-total-count'], 10) || 0,
            }));
          }
          setLastRefreshTime(new Date());
        }
      } catch (err) {
        setError(t('common.fetchTasksFailed'));
      } finally {
        setLoading(false);
        fetchingRef.current = false;
        if (!initialLoadDoneRef.current) {
          initialLoadDoneRef.current = true;
        }
      }
    },
    [pagination.current, pagination.pageSize, statusFilter, searchText, t]
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
        timeout: 30000,
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
    } catch {
      /* ignore */
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
        localStorage.removeItem('job_polling_active');
      } catch {
        /* ignore */
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
        localStorage.getItem('job_polling_timestamp') || '0'
      );
      if (now - existingPollingTimestamp < 25000) {
        return;
      }
      localStorage.setItem('job_polling_timestamp', now.toString());
      localStorage.setItem('job_polling_active', 'true');
    } catch {
      /* ignore */
    }

    const pollingInterval = 30000;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') {
        stopPolling();
        return;
      }
      try {
        localStorage.setItem('job_polling_timestamp', Date.now().toString());
      } catch {
        /* ignore */
      }
      fetchJobStatuses();
    }, pollingInterval);
    pollingTimerRef.current = intervalId;
  }, [jobs, fetchJobStatuses, stopPolling]);

  useEffect(() => {
    fetchJobs();
  }, []);

  useEffect(() => {
    if (!initialLoadDoneRef.current) {
      return;
    }
    fetchJobs();
  }, [pagination.current, pagination.pageSize, statusFilter, searchText, fetchJobs]);

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

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const lastRefresh = lastRefreshTime?.getTime() || 0;
        if (Date.now() - lastRefresh > 30000) {
          fetchJobs(true);
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
    async (values: Omit<Job, 'id' | 'status' | 'created_at' | 'updated_at'>) => {
      setLoading(true);
      try {
        const response = await axios.post(`${VITE_API_BASE_URL}/tasks`, values);
        if (response.data?.task_id) {
          messageApi.success(t('common.createSuccess'));
          await fetchJobs(true);
          return true;
        }
        messageApi.error(t('common.createFailed'));
        return false;
      } catch (error: any) {
        const errorMsg =
          error.response?.data?.error || t('common.createFailed');
        messageApi.error(`${t('common.createFailed')}: ${errorMsg}`);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchJobs, messageApi, t]
  );

  const stopJob = useCallback(
    async (jobId: string) => {
      messageApi.loading({ content: t('common.stoppingTask'), key: jobId });
      try {
        await axios.post(`${VITE_API_BASE_URL}/tasks/stop/${jobId}`);
        messageApi.success({ content: t('common.taskStopping'), key: jobId });
        setTimeout(() => fetchJobs(true), 1000);
      } catch (error: any) {
        const errorMsg =
          error.response?.data?.message || t('common.stopTaskFailed');
        messageApi.error({ content: errorMsg, key: jobId });
      }
    },
    [fetchJobs, messageApi, t]
  );

  const performSearch = useCallback(
    (text: string) => {
      setSearchText(text);
      setSearchInput(text);
      if (text !== searchText) {
        setPagination(prev => ({
          ...prev,
          current: 1,
        }));
      }
    },
    [searchText]
  );

  const updateSearchInput = useCallback((text: string) => {
    setSearchInput(text);
  }, []);

  const setStatusFilterWithReset = useCallback(
    (status: string) => {
      setStatusFilter(status);
      if (status !== statusFilter) {
        setPagination(prev => ({
          ...prev,
          current: 1,
        }));
      }
    },
    [statusFilter]
  );

  return {
    jobs,
    filteredJobs: jobs,
    pagination,
    setPagination,
    loading,
    refreshing,
    error,
    lastRefreshTime,
    searchText,
    searchInput,
    statusFilter,
    createJob,
    stopJob,
    manualRefresh: () => fetchJobs(true),
    performSearch,
    updateSearchInput,
    setStatusFilter: setStatusFilterWithReset,
  };
};
