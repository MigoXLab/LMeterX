/**
 * @file useCommonJobs.ts
 * @description Custom hook for managing common API jobs
 */
import type { MessageInstance } from 'antd/es/message/interface';
import axios from 'axios';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getApiBaseUrl } from '../utils/runtimeConfig';

import { Pagination as ApiPagination, CommonJob } from '../types/job';
import { getToken } from '../utils/auth';

interface AntdPagination {
  current: number;
  pageSize: number;
  total: number;
}

const VITE_API_BASE_URL = getApiBaseUrl();

const buildAuthHeaders = () => {
  const token = getToken();
  return token
    ? {
        // Use X-Authorization to avoid upstream filters blocking Authorization
        'X-Authorization': `Bearer ${token}`,
      }
    : {};
};

export const useCommonJobs = (messageApi: MessageInstance) => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<CommonJob[]>([]);
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
  const [creatorFilter, setCreatorFilter] = useState('');

  const pollingTimerRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fetchingRef = useRef(false);
  const initialLoadDoneRef = useRef(false);
  const isManualRefreshRef = useRef(false);

  const lastRequestParamsRef = useRef<{
    page: number;
    pageSize: number;
    status: string;
    search: string;
    creator: string;
  } | null>(null);

  // Use refs to access latest values without causing re-renders
  const paginationRef = useRef(pagination);
  const statusFilterRef = useRef(statusFilter);
  const searchTextRef = useRef(searchText);
  const creatorFilterRef = useRef(creatorFilter);

  // Keep refs in sync with state
  useEffect(() => {
    paginationRef.current = pagination;
  }, [pagination]);

  useEffect(() => {
    statusFilterRef.current = statusFilter;
  }, [statusFilter]);

  useEffect(() => {
    searchTextRef.current = searchText;
  }, [searchText]);

  useEffect(() => {
    creatorFilterRef.current = creatorFilter;
  }, [creatorFilter]);

  const fetchJobs = useCallback(
    async (
      isManualRefresh = false,
      override?: Partial<{
        page: number;
        pageSize: number;
        status: string;
        search: string;
        creator: string;
      }>
    ) => {
      // Mark as manual refresh to prevent useEffect from triggering
      if (isManualRefresh) {
        isManualRefreshRef.current = true;
      }

      const currentParams = {
        page: override?.page ?? paginationRef.current.current,
        pageSize: override?.pageSize ?? paginationRef.current.pageSize,
        status: override?.status ?? statusFilterRef.current,
        search: override?.search ?? searchTextRef.current,
        creator: override?.creator ?? creatorFilterRef.current,
      };

      // If a fetch is in-flight with identical params, skip; otherwise allow new fetch
      if (
        fetchingRef.current &&
        !isManualRefresh &&
        lastRequestParamsRef.current &&
        lastRequestParamsRef.current.page === currentParams.page &&
        lastRequestParamsRef.current.pageSize === currentParams.pageSize &&
        lastRequestParamsRef.current.status === currentParams.status &&
        lastRequestParamsRef.current.search === currentParams.search &&
        lastRequestParamsRef.current.creator === currentParams.creator
      ) {
        if (isManualRefresh) {
          isManualRefreshRef.current = false;
        }
        return;
      }

      lastRequestParamsRef.current = currentParams;
      setLoading(true);
      fetchingRef.current = true;
      setError(null);

      try {
        const response = await axios.get<{
          data: CommonJob[];
          pagination?: ApiPagination;
          total?: number;
        }>(`${VITE_API_BASE_URL}/common-tasks`, {
          params: {
            page: currentParams.page,
            pageSize: currentParams.pageSize,
            ...(currentParams.status && { status: currentParams.status }),
            ...(currentParams.search && { search: currentParams.search }),
            ...(currentParams.creator && { creator: currentParams.creator }),
            _t: Date.now(),
          },
          headers: {
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
            Expires: '0',
            ...buildAuthHeaders(),
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
              current: respPagination.page || currentParams.page,
              pageSize: respPagination.page_size || currentParams.pageSize,
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
        // Reset manual refresh flag after a short delay to allow state updates to complete
        if (isManualRefresh) {
          setTimeout(() => {
            isManualRefreshRef.current = false;
          }, 100);
        }
      }
    },
    [t]
  );

  const fetchJobStatuses = useCallback(async () => {
    const hasRunningTasks = jobs.some(job =>
      ['running', 'pending', 'created', 'queued', 'locked'].includes(
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
      const response = await axios.get(
        `${VITE_API_BASE_URL}/common-tasks/status`,
        {
          signal: controller.signal,
          timeout: 30000,
          headers: buildAuthHeaders(),
        }
      );

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
        localStorage.removeItem('common_job_polling_active');
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
      ['running', 'pending', 'created', 'queued', 'locked'].includes(
        job.status?.toLowerCase() || ''
      )
    );

    if (!hasRunningTasks) {
      return;
    }

    try {
      const now = Date.now();
      const existingPollingTimestamp = parseInt(
        localStorage.getItem('common_job_polling_timestamp') || '0'
      );
      if (now - existingPollingTimestamp < 25000) {
        return;
      }
      localStorage.setItem('common_job_polling_timestamp', now.toString());
      localStorage.setItem('common_job_polling_active', 'true');
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
        localStorage.setItem(
          'common_job_polling_timestamp',
          Date.now().toString()
        );
      } catch {
        /* ignore */
      }
      fetchJobStatuses();
    }, pollingInterval);

    pollingTimerRef.current = intervalId;
  }, [fetchJobStatuses, jobs, stopPolling]);

  useEffect(() => {
    fetchJobs();
  }, []);

  useEffect(() => {
    if (!initialLoadDoneRef.current) {
      return;
    }
    // Skip if this is triggered by a manual refresh
    if (isManualRefreshRef.current) {
      return;
    }
    fetchJobs();
  }, [
    pagination.current,
    pagination.pageSize,
    statusFilter,
    searchText,
    creatorFilter,
    fetchJobs,
  ]);

  useEffect(() => {
    const hasRunningTasks = jobs.some(job =>
      ['running', 'pending', 'created', 'queued', 'locked'].includes(
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
    async (data: any) => {
      try {
        setLoading(true);
        const response = await axios.post(
          `${VITE_API_BASE_URL}/common-tasks`,
          data,
          { headers: buildAuthHeaders() }
        );
        if (response.status === 200 || response.status === 201) {
          messageApi.success(t('pages.jobs.createSuccess'));
          await fetchJobs(true);
          return true;
        }
      } catch (error: any) {
        messageApi.error(
          error?.response?.data?.message ||
            error?.message ||
            t('pages.jobs.createFailed')
        );
      } finally {
        setLoading(false);
      }
      return false;
    },
    [fetchJobs, messageApi, t]
  );

  const stopJob = useCallback(
    async (taskId: string) => {
      try {
        const response = await axios.post(
          `${VITE_API_BASE_URL}/common-tasks/stop/${taskId}`,
          null,
          { headers: buildAuthHeaders() }
        );
        if (response.status === 200) {
          messageApi.success(t('pages.jobs.stopSuccess'));
          await fetchJobs(true);
          return true;
        }
      } catch (error: any) {
        messageApi.error(
          error?.response?.data?.message ||
            error?.message ||
            t('pages.jobs.stopFailed')
        );
      }
      return false;
    },
    [fetchJobs, messageApi, t]
  );

  const updateJobName = useCallback(
    async (taskId: string, name: string) => {
      const trimmedName = name.trim();
      if (!trimmedName) {
        messageApi.error(t('pages.jobs.renameFailed'));
        return false;
      }
      setLoading(true);
      try {
        await axios.put(
          `${VITE_API_BASE_URL}/common-tasks/${taskId}`,
          { name: trimmedName },
          { headers: buildAuthHeaders() }
        );
        messageApi.success(t('pages.jobs.renameSuccess'));
        await fetchJobs(true);
        return true;
      } catch (error: any) {
        messageApi.error(
          error?.response?.data?.error || t('pages.jobs.renameFailed')
        );
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchJobs, messageApi, t]
  );

  const deleteJob = useCallback(
    async (taskId: string) => {
      setLoading(true);
      try {
        await axios.delete(`${VITE_API_BASE_URL}/common-tasks/${taskId}`, {
          headers: buildAuthHeaders(),
        });
        messageApi.success(t('pages.jobs.deleteSuccess'));
        await fetchJobs(true);
        return true;
      } catch (error: any) {
        messageApi.error(
          error?.response?.data?.error || t('pages.jobs.deleteFailed')
        );
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchJobs, messageApi, t]
  );

  return {
    filteredJobs: jobs,
    pagination,
    setPagination,
    loading,
    refreshing,
    error,
    lastRefreshTime,
    searchInput,
    statusFilter,
    creatorFilter,
    createJob,
    stopJob,
    updateJobName,
    deleteJob,
    manualRefresh: async (
      override?: Partial<{
        page: number;
        pageSize: number;
        status: string;
        search: string;
        creator: string;
      }>
    ) => {
      setRefreshing(true);
      isManualRefreshRef.current = true;
      // Update pagination state before fetching if override is provided
      if (override?.page !== undefined || override?.pageSize !== undefined) {
        setPagination(prev => ({
          ...prev,
          current: override?.page ?? prev.current,
          pageSize: override?.pageSize ?? prev.pageSize,
        }));
      }
      if (override?.status !== undefined) {
        setStatusFilter(override.status);
      }
      if (override?.search !== undefined) {
        setSearchText(override.search);
      }
      if (override?.creator !== undefined) {
        setCreatorFilter(override.creator);
      }
      await fetchJobs(true, override);
      setRefreshing(false);
    },
    performSearch: (value: string) => {
      setSearchText(value || '');
      setPagination(prev => ({
        ...prev,
        current: 1,
      }));
    },
    updateSearchInput: (value: string) => setSearchInput(value),
    setStatusFilter: (status: string) => {
      setStatusFilter(status);
      setPagination(prev => ({
        ...prev,
        current: 1,
      }));
    },
    setCreatorFilter: (creator: string) => {
      setCreatorFilter(creator);
      setPagination(prev => ({
        ...prev,
        current: 1,
      }));
    },
  };
};
