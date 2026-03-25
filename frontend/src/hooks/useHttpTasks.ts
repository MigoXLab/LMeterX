/**
 * @file useHttpTasks.ts
 * @description Custom hook for managing HTTP API tasks
 */
import type { MessageInstance } from 'antd/es/message/interface';
import axios from 'axios';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getApiBaseUrl } from '../utils/runtimeConfig';

import { Pagination as ApiPagination, HttpTask } from '../types/job';
import { getToken } from '../utils/auth';

interface AntdPagination {
  current: number;
  pageSize: number;
  total: number;
}

const VITE_API_BASE_URL = getApiBaseUrl();

/** Polling interval when active tasks exist (ms) */
const ACTIVE_POLLING_INTERVAL = 5000;

const buildAuthHeaders = () => {
  const token = getToken();
  return token
    ? {
        // Use X-Authorization to avoid upstream filters blocking Authorization
        'X-Authorization': `Bearer ${token}`,
      }
    : {};
};

const isActiveStatus = (status?: string) =>
  ['running', 'pending', 'created', 'queued', 'locked'].includes(
    status?.toLowerCase() || ''
  );

export const useHttpTasks = (messageApi: MessageInstance) => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<HttpTask[]>([]);
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

  // Use ref to always access the latest jobs in polling callbacks (avoid stale closure)
  const jobsRef = useRef<HttpTask[]>(jobs);
  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

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
          data: HttpTask[];
          pagination?: ApiPagination;
          total?: number;
        }>(`${VITE_API_BASE_URL}/http-tasks`, {
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

  /**
   * Lightweight status-only poll.
   * Reads jobs from ref so the callback never goes stale inside setInterval.
   */
  const fetchJobStatuses = useCallback(async () => {
    const currentJobs = jobsRef.current;
    const hasRunningTasks = currentJobs.some(job => isActiveStatus(job.status));

    if (!hasRunningTasks || fetchingRef.current) {
      return;
    }

    fetchingRef.current = true;
    setRefreshing(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await axios.get(
        `${VITE_API_BASE_URL}/http-tasks/status`,
        {
          signal: controller.signal,
          timeout: 10000,
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
            (acc: Record<string, string>, update: any) => {
              if (update && update.id) {
                acc[update.id] = update.status.toLowerCase();
              }
              return acc;
            },
            {} as Record<string, string>
          );

          setJobs(prevJobs => {
            let hasChanges = false;
            const updatedJobs = prevJobs.map(job => {
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
              setLastRefreshTime(new Date());
              return updatedJobs;
            }
            return prevJobs;
          });
        }
      }
    } catch {
      /* ignore polling errors */
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      fetchingRef.current = false;
      setRefreshing(false);
    }
  }, []); // No deps – reads from jobsRef

  const stopPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    // Already polling or tab hidden → skip
    if (
      pollingTimerRef.current !== null ||
      document.visibilityState !== 'visible'
    ) {
      return;
    }

    const hasRunningTasks = jobsRef.current.some(job =>
      isActiveStatus(job.status)
    );

    if (!hasRunningTasks) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') {
        stopPolling();
        return;
      }
      fetchJobStatuses();
    }, ACTIVE_POLLING_INTERVAL);

    pollingTimerRef.current = intervalId;
  }, [fetchJobStatuses, stopPolling]);

  // Initial data fetch
  useEffect(() => {
    fetchJobs();
  }, []);

  // Re-fetch when filters or pagination change
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

  // Start / stop polling based on whether active tasks exist
  useEffect(() => {
    const hasRunningTasks = jobs.some(job => isActiveStatus(job.status));

    if (hasRunningTasks) {
      startPolling();
    } else {
      stopPolling();
    }

    return () => stopPolling();
  }, [jobs, startPolling, stopPolling]);

  // Visibility change handling – refresh immediately when tab becomes visible
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const lastRefresh = lastRefreshTime?.getTime() || 0;
        if (Date.now() - lastRefresh > 5000) {
          fetchJobs(true);
        }
        startPolling();
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
          `${VITE_API_BASE_URL}/http-tasks`,
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
          `${VITE_API_BASE_URL}/http-tasks/stop/${taskId}`,
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
          `${VITE_API_BASE_URL}/http-tasks/${taskId}`,
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
        await axios.delete(`${VITE_API_BASE_URL}/http-tasks/${taskId}`, {
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
