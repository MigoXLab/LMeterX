/**
 * @file TaskLog.tsx
 * @description Task log page
 * @author Charm
 * @copyright 2025
 */

import {
  DownloadOutlined,
  DownOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  MonitorOutlined,
  SearchOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Input,
  message,
  Select,
  Space,
  Switch,
  Tooltip,
  Typography,
} from 'antd';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { jobApi, logApi } from '../api/services';
import { LoadingSpinner } from '../components/ui/LoadingState';
import { PageHeader } from '../components/ui/PageHeader';
import { Job } from '../types/job';
import { decodeUnicodeEscapes } from '../utils/data';
import {
  buildSlsLogLine,
  normalizeLogTimestamp,
  stripNestedLogPrefix,
} from '../utils/logFormat';

const { Search } = Input;
const { Text } = Typography;

// Pre-compiled regexes for log line parsing (created once at module load)
// Pattern 1: Structured log with pipe separators (3 or 4 segments)
const STRUCTURED_LOG_REGEX =
  /^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)\s*\|\s*(INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)\s*\|\s*(?:\S+:\d+\s*\|\s*)?(.*)/i;
// Pattern 2: Locust-style log
const LOCUST_LOG_REGEX =
  /^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:[.,]\d{3})?)\]\s+(?:.+?)\/(INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)\/(?:[^:]+):\s*(.*)/i;
// Fallback: any line with a level keyword
const LEVEL_REGEX =
  /(^|\s)(INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)(\s|:)/i;

const FINAL_TASK_STATUSES = [
  'COMPLETED',
  'FAILED',
  'STOPPED',
  'CANCELLED',
  'ERROR',
  'FAILED_REQUESTS',
];

const isTaskInFinalState = (status: string | null | undefined): boolean => {
  if (!status) return false;
  return FINAL_TASK_STATUSES.includes(status.toUpperCase());
};

const INITIAL_LOG_LOOKBACK_SECONDS = 10 * 60;
const ALL_LOG_LOOKBACK_SECONDS = 60 * 60;
const INCREMENTAL_LOG_LIMIT = 100;
const HISTORY_LOG_PAGE_SIZE = 1000;
const HISTORY_LOAD_SCROLL_THRESHOLD = 240;
const VIRTUAL_LOG_LINE_THRESHOLD = 1000;
const COMPLETED_TASK_LOG_PADDING_SECONDS = 60;
// SLS ingestion can lag behind a fast task reaching its final state. Keep
// polling briefly so the last log batch can arrive without a browser reload.
const FINAL_LOG_REFRESH_GRACE_MS = 30 * 1000;
const SLS_UNAVAILABLE_BACKOFF_MS = 60 * 1000;

const isSlsUnavailableError = (err: any): boolean => {
  const statusCode = err?.status || err?.response?.status;
  const code = err?.data?.code || err?.response?.data?.code;
  const details = String(
    err?.data?.details || err?.response?.data?.details || err?.message || ''
  ).toLowerCase();
  return (
    code === 'sls_temporarily_unavailable' ||
    (statusCode === 503 && details.includes('sls')) ||
    details.includes('nameresolutionerror') ||
    details.includes('failed to resolve') ||
    details.includes('temporary failure in name resolution')
  );
};

const getRenderedLogTimestampSortKey = (line: string): string => {
  const separatorIndex = line.indexOf(' | ');
  if (separatorIndex < 0) {
    return '';
  }
  return line.slice(0, separatorIndex);
};

const sortRenderedLogLines = (lines: string[]): string[] =>
  lines
    .map((line, index) => ({
      line,
      index,
      timestampSortKey: getRenderedLogTimestampSortKey(line),
    }))
    .sort((a, b) => {
      if (a.timestampSortKey !== b.timestampSortKey) {
        return a.timestampSortKey < b.timestampSortKey ? -1 : 1;
      }
      return a.index - b.index;
    })
    .map(item => item.line);

const TaskLogs: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [logSource] = useState<'engine' | 'backend'>('engine');
  const [loading, setLoading] = useState(true);
  const [logLoading, setLogLoading] = useState(false);
  const [hasLogLoadCompleted, setHasLogLoadCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string>('');
  const [filteredLogs, setFilteredLogs] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [fullscreen, setFullscreen] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tailLines, setTailLines] = useState<number>(100);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [task, setTask] = useState<Job | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [isStatusRefreshing, setIsStatusRefreshing] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(480);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const lastLogScrollTopRef = useRef(0);
  const autoRefreshTimerRef = useRef<number | null>(null);
  const errorRetryTimerRef = useRef<number | null>(null);
  const shouldScrollToBottom = useRef(true);
  const taskRef = useRef<Job | null>(null);
  const fetchErrorRef = useRef<string | null>(null);
  const fetchLogsRef = useRef<(showLoading?: boolean) => Promise<void>>(null!);
  const fetchOlderLogsRef = useRef<() => Promise<void>>(null!);
  const fetchLogsInFlightRef = useRef(false);
  const fetchTaskStatusInFlightRef = useRef(false);
  const historyFetchInFlightRef = useRef(false);
  const historyOffsetRef = useRef(0);
  const historyEndTimeRef = useRef<number | null>(null);
  const hasMoreHistoryRef = useRef(false);
  const logEntryKeysRef = useRef<Set<string>>(new Set());
  const logRequestGenerationRef = useRef(0);
  const fetchTaskStatusRef = useRef<
    (
      isInitialLoad?: boolean,
      showRefreshing?: boolean
    ) => Promise<Job | null | undefined>
  >(null!);
  const slsCursorRef = useRef<number | null>(null);
  const slsPausedUntilRef = useRef(0);
  const finalLogRefreshDeadlineRef = useRef<number | null>(null);
  const searchTermRef = useRef('');
  const lineHeight = 24;

  const resetSlsLogState = () => {
    logRequestGenerationRef.current += 1;
    fetchLogsInFlightRef.current = false;
    historyFetchInFlightRef.current = false;
    historyOffsetRef.current = 0;
    historyEndTimeRef.current = null;
    hasMoreHistoryRef.current = false;
    slsCursorRef.current = null;
    logEntryKeysRef.current.clear();
    setHasLogLoadCompleted(false);
    setIsHistoryLoading(false);
    setHasMoreHistory(false);
    setLogs('');
    setFilteredLogs('');
    setScrollTop(0);
    lastLogScrollTopRef.current = 0;
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = 0;
      setViewportHeight(logContainerRef.current.clientHeight || 480);
    }
  };

  const getSlsLogEntryKey = (entry: any): string => {
    const timestamp = entry.raw?.time || String(entry.timestamp || '');
    const level = entry.level || entry.raw?.level || '';
    const message = entry.message || entry.raw?.message || '';
    const service = entry.service || entry.raw?.service || '';
    const taskId = entry.task_id || entry.raw?.task_id || '';
    const engineId = entry.engine_id || entry.raw?.engine_id || '';
    const clusterId = entry.cluster_id || entry.raw?.cluster_id || '';
    return [
      timestamp,
      level,
      service,
      taskId,
      engineId,
      clusterId,
      message,
    ].join('|');
  };

  const filterLocalLogContent = (content: string): string => {
    const keyword = searchTermRef.current.trim();
    if (!keyword) {
      return content;
    }
    return content
      .split('\n')
      .filter(line => line.includes(keyword))
      .join('\n');
  };

  const fetchLocalTaskLogs = async (
    requestGeneration = logRequestGenerationRef.current
  ): Promise<string> => {
    if (!id) {
      return '';
    }

    const response = await logApi.getTaskLogContent(
      id,
      0,
      tailLines,
      logSource
    );
    const content = filterLocalLogContent(response.data?.content || '');
    if (requestGeneration !== logRequestGenerationRef.current) {
      return '';
    }
    slsCursorRef.current = null;
    historyOffsetRef.current = 0;
    historyEndTimeRef.current = null;
    hasMoreHistoryRef.current = false;
    logEntryKeysRef.current.clear();
    setHasMoreHistory(false);
    setLogs(content);
    setFilteredLogs(content);
    return content;
  };

  const getTaskLogTimeRange = () => {
    const now = Math.floor(Date.now() / 1000);
    const currentTask = taskRef.current;

    if (currentTask) {
      const createdAt = Date.parse(currentTask.created_at || '');
      const updatedAt = Date.parse(currentTask.updated_at || '');
      const from = Number.isFinite(createdAt)
        ? Math.floor(createdAt / 1000) - COMPLETED_TASK_LOG_PADDING_SECONDS
        : now - ALL_LOG_LOOKBACK_SECONDS;
      const to =
        isTaskInFinalState(currentTask.status) && Number.isFinite(updatedAt)
          ? Math.floor(updatedAt / 1000) +
            COMPLETED_TASK_LOG_PADDING_SECONDS * 5
          : now + 5;

      return {
        startTime: Math.max(0, from),
        endTime: Math.max(to, now + 5),
      };
    }

    const lookbackSeconds =
      tailLines === 0 ? ALL_LOG_LOOKBACK_SECONDS : INITIAL_LOG_LOOKBACK_SECONDS;
    return {
      startTime: now - lookbackSeconds,
      endTime: now + 5,
    };
  };

  const getLogContainerHeight = () => {
    if (fullscreen) {
      return 'calc(100vh - 170px)';
    }
    return 'calc(100vh - 250px)';
  };

  const scrollToBottom = (force = false) => {
    const container = logContainerRef.current;
    if ((force || shouldScrollToBottom.current) && container) {
      container.scrollTop = container.scrollHeight;
      setScrollTop(container.scrollTop);
      setViewportHeight(container.clientHeight || 480);
    }
  };

  const detachFromBottomFollow = useCallback(() => {
    shouldScrollToBottom.current = false;
    setShowScrollToBottom(prev => (!prev ? true : prev));
  }, []);

  const handleLogContainerRef = useCallback((node: HTMLDivElement | null) => {
    logContainerRef.current = node;
    if (node) {
      const currentScrollTop = node.scrollTop;
      lastLogScrollTopRef.current = currentScrollTop;
      setScrollTop(currentScrollTop);
      setViewportHeight(node.clientHeight || 480);
    }
  }, []);

  const handleLogWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      if (event.deltaY < 0) {
        detachFromBottomFollow();
      }
    },
    [detachFromBottomFollow]
  );

  const handleLogScroll = useCallback(() => {
    const container = logContainerRef.current;
    if (!container) {
      return;
    }

    const currentScrollTop = container.scrollTop;
    setScrollTop(currentScrollTop);
    setViewportHeight(container.clientHeight || 480);

    const scrollDirection =
      currentScrollTop > lastLogScrollTopRef.current ? 'down' : 'up';
    lastLogScrollTopRef.current = currentScrollTop <= 0 ? 0 : currentScrollTop;

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;

    if (scrollDirection === 'up' && distanceFromBottom > 50) {
      detachFromBottomFollow();
    }

    if (distanceFromBottom < 10) {
      shouldScrollToBottom.current = true;
      setShowScrollToBottom(prev => (prev ? false : prev));
    }

    if (
      tailLines === 0 &&
      scrollDirection === 'up' &&
      currentScrollTop <= HISTORY_LOAD_SCROLL_THRESHOLD
    ) {
      fetchOlderLogsRef.current?.();
    }
  }, [detachFromBottomFollow, tailLines]);

  const fetchLogs = async (showLoading = false) => {
    if (!id) return;
    if (fetchLogsInFlightRef.current) return;

    fetchLogsInFlightRef.current = true;
    const requestGeneration = logRequestGenerationRef.current;
    if (showLoading) {
      setLogLoading(true);
    }

    try {
      if (fetchError) setFetchError(null);

      const cursor = slsCursorRef.current;
      const { startTime, endTime } = getTaskLogTimeRange();
      const isInitialLoad = !cursor;
      // Freeze the history window so newly appended logs cannot shift
      // reverse-offset pages while the user scrolls toward older entries.
      const queryEndTime =
        isInitialLoad && tailLines === 0
          ? historyEndTimeRef.current ||
            Math.min(endTime, Math.floor(Date.now() / 1000))
          : endTime;
      if (isInitialLoad && tailLines === 0) {
        historyEndTimeRef.current = queryEndTime;
      }
      let pageOffset = 0;
      let nextCursor = cursor;
      let hasSlsLines = false;
      const lines: string[] = [];

      if (Date.now() < slsPausedUntilRef.current) {
        return;
      }

      do {
        // eslint-disable-next-line no-await-in-loop -- SLS pagination must follow the previous page cursor.
        const contentResponse = await logApi.queryRealtimeTaskLogs(id, {
          start_time: cursor ? Math.max(0, cursor - 1) : startTime,
          end_time: queryEndTime,
          limit: cursor
            ? INCREMENTAL_LOG_LIMIT
            : tailLines || HISTORY_LOG_PAGE_SIZE,
          offset: isInitialLoad ? pageOffset : undefined,
          keyword: searchTermRef.current.trim() || undefined,
          reverse: !cursor,
        });

        if (requestGeneration !== logRequestGenerationRef.current) {
          return;
        }

        if (!contentResponse.data) {
          resetSlsLogState();
          return;
        }

        const lineCountBeforePage = lines.length;
        (contentResponse.data.logs || []).reduce(
          (acc: string[], entry: any) => {
            const key = getSlsLogEntryKey(entry);
            if (logEntryKeysRef.current.has(key)) {
              return acc;
            }
            logEntryKeysRef.current.add(key);

            acc.push(
              ...buildSlsLogLine(entry, decodeUnicodeEscapes)
                .split('\n')
                .filter(Boolean)
            );
            return acc;
          },
          lines
        );
        if (lines.length > lineCountBeforePage) {
          hasSlsLines = true;
        }
        if (contentResponse.data.next_cursor) {
          nextCursor = Math.max(
            nextCursor || 0,
            contentResponse.data.next_cursor
          );
        }
        pageOffset = contentResponse.data.next_offset || 0;
      } while (
        isInitialLoad &&
        tailLines !== 0 &&
        pageOffset > 0 &&
        lines.length < tailLines
      );

      if (isInitialLoad && tailLines === 0) {
        historyOffsetRef.current = pageOffset;
        hasMoreHistoryRef.current = pageOffset > 0;
        setHasMoreHistory(pageOffset > 0);
      }

      if (hasSlsLines) {
        slsCursorRef.current = nextCursor;
        setLogs(prev => {
          const baseLines = cursor ? prev.split('\n').filter(Boolean) : [];
          const next = Array.from(new Set([...baseLines, ...lines]));
          const sortedLines = sortRenderedLogLines(next);
          const trimmed = (
            tailLines === 0 ? sortedLines : sortedLines.slice(-tailLines)
          ).join('\n');
          setFilteredLogs(trimmed);
          return trimmed;
        });
      } else if (cursor) {
        slsCursorRef.current = nextCursor;
      }
      if (error) setError(null);
    } catch (err: any) {
      const slsUnavailable = isSlsUnavailableError(err);
      if (slsUnavailable) {
        slsPausedUntilRef.current = Date.now() + SLS_UNAVAILABLE_BACKOFF_MS;
      }

      // If 404 (log file not found), treat as "no logs" instead of error
      const statusCode = err?.status || err?.response?.status;
      if (statusCode === 404) {
        try {
          await fetchLocalTaskLogs(requestGeneration);
          if (requestGeneration !== logRequestGenerationRef.current) {
            return;
          }
          if (error) setError(null);
          if (fetchError) setFetchError(null);
          return;
        } catch (fallbackErr) {
          setLogs('');
          setFilteredLogs('');
          if (error) setError(null);
          return;
        }
      }

      try {
        await fetchLocalTaskLogs(requestGeneration);
        if (requestGeneration !== logRequestGenerationRef.current) {
          return;
        }
        if (error) setError(null);
        if (fetchError) setFetchError(null);
        return;
      } catch (fallbackErr) {
        // Keep the original SLS error when the local/OSS fallback is unavailable.
      }

      if (slsUnavailable) {
        setLogs('');
        setFilteredLogs('');
        if (error) setError(null);
        if (fetchError) setFetchError(null);
        return;
      }

      const errorMsg =
        err?.data?.error ||
        err?.response?.data?.error ||
        err?.message ||
        'Failed to fetch task logs from SLS';
      if (loading) {
        setError(errorMsg);
      } else {
        setFetchError(errorMsg);
      }
    } finally {
      fetchLogsInFlightRef.current = false;
      if (requestGeneration === logRequestGenerationRef.current) {
        setHasLogLoadCompleted(true);
        if (showLoading) {
          setLogLoading(false);
        }
      }
      if (showLoading) {
        shouldScrollToBottom.current = true;
        setShowScrollToBottom(false);
        setTimeout(() => scrollToBottom(true), 100);
      } else if (shouldScrollToBottom.current) {
        setTimeout(scrollToBottom, 100);
      }
    }
  };

  const fetchOlderLogs = async () => {
    if (
      !id ||
      tailLines !== 0 ||
      historyFetchInFlightRef.current ||
      !hasMoreHistoryRef.current ||
      !historyEndTimeRef.current
    ) {
      return;
    }

    const requestGeneration = logRequestGenerationRef.current;
    const container = logContainerRef.current;
    const previousScrollHeight = container?.scrollHeight || 0;
    const previousScrollTop = container?.scrollTop || 0;
    historyFetchInFlightRef.current = true;
    setIsHistoryLoading(true);

    try {
      const { startTime } = getTaskLogTimeRange();
      const contentResponse = await logApi.queryRealtimeTaskLogs(id, {
        start_time: startTime,
        end_time: historyEndTimeRef.current,
        limit: HISTORY_LOG_PAGE_SIZE,
        offset: historyOffsetRef.current,
        keyword: searchTermRef.current.trim() || undefined,
        reverse: true,
      });

      if (
        requestGeneration !== logRequestGenerationRef.current ||
        !contentResponse.data
      ) {
        return;
      }

      const olderLines: string[] = [];
      (contentResponse.data.logs || []).forEach((entry: any) => {
        const key = getSlsLogEntryKey(entry);
        if (logEntryKeysRef.current.has(key)) {
          return;
        }
        logEntryKeysRef.current.add(key);
        olderLines.push(
          ...buildSlsLogLine(entry, decodeUnicodeEscapes)
            .split('\n')
            .filter(Boolean)
        );
      });

      const nextOffset = contentResponse.data.next_offset || 0;
      historyOffsetRef.current = nextOffset;
      hasMoreHistoryRef.current = nextOffset > 0;
      setHasMoreHistory(nextOffset > 0);

      if (olderLines.length > 0) {
        setLogs(prev => {
          const next = sortRenderedLogLines([
            ...olderLines,
            ...prev.split('\n').filter(Boolean),
          ]).join('\n');
          setFilteredLogs(next);
          return next;
        });

        requestAnimationFrame(() => {
          const currentContainer = logContainerRef.current;
          if (!currentContainer) {
            return;
          }
          const restoredScrollTop =
            previousScrollTop +
            currentContainer.scrollHeight -
            previousScrollHeight;
          currentContainer.scrollTop = restoredScrollTop;
          lastLogScrollTopRef.current = restoredScrollTop;
          setScrollTop(restoredScrollTop);
          setViewportHeight(currentContainer.clientHeight || 480);
        });
      }
    } catch (err) {
      message.error(
        t('pages.taskLog.loadHistoryFailed', '历史日志加载失败，请重试')
      );
    } finally {
      if (requestGeneration === logRequestGenerationRef.current) {
        historyFetchInFlightRef.current = false;
        setIsHistoryLoading(false);
      }
    }
  };

  const fetchTaskStatus = async (
    isInitialLoad = false,
    showRefreshing = true
  ) => {
    if (!id) return;
    if (fetchTaskStatusInFlightRef.current) {
      return taskRef.current;
    }

    fetchTaskStatusInFlightRef.current = true;

    if (!isInitialLoad && showRefreshing) {
      setIsStatusRefreshing(true);
    }

    try {
      if (isInitialLoad) {
        const taskResponse = await jobApi.getJob(id);
        if (taskResponse.data) {
          const currentTask = taskResponse.data;
          if (isTaskInFinalState(currentTask.status)) {
            finalLogRefreshDeadlineRef.current ??=
              Date.now() + FINAL_LOG_REFRESH_GRACE_MS;
          } else {
            finalLogRefreshDeadlineRef.current = null;
          }
          taskRef.current = currentTask;
          setTask(currentTask);
          return currentTask;
        }
      } else {
        const taskResponse = await jobApi.getJobStatus(id);
        if (taskResponse.data) {
          const currentTaskStatus = taskResponse.data;
          const updatedTask = {
            ...taskRef.current,
            id: currentTaskStatus.id,
            name: currentTaskStatus.name,
            status: currentTaskStatus.status,
            error_message: currentTaskStatus.error_message,
            updated_at: currentTaskStatus.updated_at,
          } as Job;

          if (isTaskInFinalState(currentTaskStatus.status)) {
            finalLogRefreshDeadlineRef.current ??=
              Date.now() + FINAL_LOG_REFRESH_GRACE_MS;
          } else {
            finalLogRefreshDeadlineRef.current = null;
          }
          taskRef.current = updatedTask;
          setTask(updatedTask);
          return updatedTask;
        }
      }
    } catch (err) {
      try {
        const taskResponse = await jobApi.getJob(id);
        if (taskResponse.data) {
          const currentTask = taskResponse.data;
          if (isTaskInFinalState(currentTask.status)) {
            finalLogRefreshDeadlineRef.current ??=
              Date.now() + FINAL_LOG_REFRESH_GRACE_MS;
          } else {
            finalLogRefreshDeadlineRef.current = null;
          }
          taskRef.current = currentTask;
          setTask(currentTask);
          return currentTask;
        }
      } catch (fallbackErr) {
        // Failed to fetch task info as fallback
      }
    } finally {
      fetchTaskStatusInFlightRef.current = false;
      if (!isInitialLoad && showRefreshing) {
        setIsStatusRefreshing(false);
      }
    }
    return null;
  };

  // Keep function refs in sync for stable auto-refresh callbacks
  useEffect(() => {
    fetchLogsRef.current = fetchLogs;
    fetchOlderLogsRef.current = fetchOlderLogs;
    fetchTaskStatusRef.current = fetchTaskStatus;
  });

  useEffect(() => {
    taskRef.current = task;
  }, [task]);

  useEffect(() => {
    fetchErrorRef.current = fetchError;
  }, [fetchError]);

  useEffect(() => {
    if (!id) {
      setError('Task ID not provided.');
      setLoading(false);
      return;
    }

    shouldScrollToBottom.current = true;
    setSearchTerm('');

    const load = async () => {
      setLoading(true);
      setError(null);
      setFetchError(null);
      resetSlsLogState();

      await fetchTaskStatus(true);
      // A newly-created/queued task may already have scheduler or engine logs.
      // Query immediately and let polling pick up logs as soon as they arrive.
      setLogLoading(true);
      setLoading(false);
      await fetchLogs(true);
    };

    load();
  }, [id, tailLines, logSource]);

  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
    }

    if (autoRefresh && !loading) {
      autoRefreshTimerRef.current = window.setInterval(async () => {
        // Use refs to access latest values without adding them as effect deps,
        // preventing the interval from being constantly recreated
        if (!fetchErrorRef.current) {
          const updatedTask = await fetchTaskStatusRef.current?.(false, false);
          // Poll logs for every non-final status. This covers created/queuing
          // tasks and avoids missing very short runs between status polls.
          await fetchLogsRef.current?.();

          const currentTask = updatedTask || taskRef.current;
          const finalRefreshDeadline = finalLogRefreshDeadlineRef.current;
          if (
            isTaskInFinalState(currentTask?.status) &&
            finalRefreshDeadline !== null &&
            Date.now() >= finalRefreshDeadline
          ) {
            setAutoRefresh(false);
          }
        }
      }, 3000);
    }

    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [autoRefresh, loading, id, tailLines, logSource]);

  useEffect(() => {
    const handleResize = () => {
      if (logContainerRef.current) {
        const currentHeight = logContainerRef.current.style.height;
        logContainerRef.current.style.height = '0px';
        setTimeout(() => {
          if (logContainerRef.current) {
            logContainerRef.current.style.height = currentHeight;
          }
        }, 0);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    searchTermRef.current = value;
    resetSlsLogState();
    setLogLoading(true);
    setTimeout(() => {
      fetchLogsRef.current?.(true);
    }, 0);
  };

  const handleDownload = () => {
    if (!id) {
      message.warning(t('pages.taskLog.logEmpty'));
      return;
    }
    window.location.href = logApi.getTaskLogDownloadUrl(id, logSource);
  };

  const toggleFullscreen = () => {
    setFullscreen(!fullscreen);
  };

  const getLevelClass = (level: string): string => {
    switch (level) {
      case 'ERROR':
      case 'FATAL':
      case 'CRITICAL':
        return 'error';
      case 'WARN':
      case 'WARNING':
        return 'warning';
      case 'INFO':
        return 'info';
      case 'DEBUG':
        return 'debug';
      default:
        return 'default';
    }
  };

  const formatLogLine = (line: string, lineNumber: number) => {
    // Handle empty lines
    if (line.trim() === '') {
      return (
        <div className='log-line'>
          <span className='log-line-number'>{lineNumber}</span>
          <span className='log-content'>&nbsp;</span>
        </div>
      );
    }

    const structuredMatch = line.match(STRUCTURED_LOG_REGEX);

    if (structuredMatch) {
      const [, rawTimestamp, level, msg] = structuredMatch;
      const timestamp = normalizeLogTimestamp(rawTimestamp);
      const levelClass = getLevelClass(level.toUpperCase());

      return (
        <div className={`log-line log-line-${levelClass}`}>
          <span className='log-line-number'>{lineNumber}</span>
          <span className='log-content'>
            <span className='log-timestamp'>{timestamp}</span>
            <span className='log-separator'> | </span>
            <span className={`log-level-badge log-level-${levelClass}`}>
              {level.toUpperCase().padEnd(8)}
            </span>
            <span className='log-separator'> | </span>
            <span className='log-message'>{stripNestedLogPrefix(msg)}</span>
          </span>
        </div>
      );
    }

    const locustMatch = line.match(LOCUST_LOG_REGEX);

    if (locustMatch) {
      const [, rawTimestamp, level, msg] = locustMatch;
      const timestamp = normalizeLogTimestamp(rawTimestamp);
      const levelClass = getLevelClass(level.toUpperCase());

      return (
        <div className={`log-line log-line-${levelClass}`}>
          <span className='log-line-number'>{lineNumber}</span>
          <span className='log-content'>
            <span className='log-timestamp'>{timestamp}</span>
            <span className='log-separator'> | </span>
            <span className={`log-level-badge log-level-${levelClass}`}>
              {level.toUpperCase().padEnd(8)}
            </span>
            <span className='log-separator'> | </span>
            <span className='log-message'>{msg}</span>
          </span>
        </div>
      );
    }

    const levelMatch = line.match(LEVEL_REGEX);

    if (levelMatch) {
      const level = levelMatch[2].toUpperCase();
      const levelClass = getLevelClass(level);
      const fullMatchIndex = line.indexOf(levelMatch[0]);
      const levelIndex = fullMatchIndex + levelMatch[1].length;
      const levelEnd = levelIndex + levelMatch[2].length;

      return (
        <div className={`log-line log-line-${levelClass}`}>
          <span className='log-line-number'>{lineNumber}</span>
          <span className='log-content'>
            <span className='log-message'>{line.substring(0, levelIndex)}</span>
            <span className={`log-level-badge log-level-${levelClass}`}>
              {line.substring(levelIndex, levelEnd)}
            </span>
            <span className='log-message'>{line.substring(levelEnd)}</span>
          </span>
        </div>
      );
    }

    // Plain text lines (HTML content, continuation lines, etc.)
    return (
      <div className='log-line'>
        <span className='log-line-number'>{lineNumber}</span>
        <span className='log-content log-plain-text'>{line}</span>
      </div>
    );
  };

  const handleScrollToBottomClick = () => {
    shouldScrollToBottom.current = true;
    scrollToBottom(true);
    requestAnimationFrame(() => scrollToBottom(true));
    setShowScrollToBottom(false);
  };

  const handleManualRefresh = async () => {
    if (!id) return;

    const refresh = async () => {
      setLogLoading(true);
      setError(null);
      setFetchError(null);
      // A user-triggered refresh must bypass a previous transient SLS backoff;
      // otherwise only remounting the page would issue a new request.
      slsPausedUntilRef.current = 0;
      resetSlsLogState();
      const currentTask = await fetchTaskStatus();
      if (isTaskInFinalState(currentTask?.status)) {
        finalLogRefreshDeadlineRef.current =
          Date.now() + FINAL_LOG_REFRESH_GRACE_MS;
        setAutoRefresh(true);
      }
      await fetchLogs(true);
      message.success(t('pages.taskLog.refreshLogs'));
    };

    try {
      await refresh();
    } catch (error) {
      setLogLoading(false);
    }
  };

  const logLines = useMemo(
    () => filteredLogs.split('\n').filter(Boolean),
    [filteredLogs]
  );

  useEffect(() => {
    if (!loading && shouldScrollToBottom.current) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [logLines.length, loading, fullscreen]);

  const virtualWindow = useMemo(() => {
    if (logLines.length <= VIRTUAL_LOG_LINE_THRESHOLD) {
      return {
        start: 0,
        end: logLines.length,
        top: 0,
        height: undefined,
        visible: logLines,
      };
    }

    const overscan = 12;
    const visibleCount = Math.ceil(viewportHeight / lineHeight) + overscan * 2;
    const maxStart = Math.max(0, logLines.length - visibleCount);
    const start = Math.min(
      maxStart,
      Math.max(0, Math.floor(scrollTop / lineHeight) - overscan)
    );
    const end = Math.min(logLines.length, start + visibleCount);
    return {
      start,
      end,
      top: start * lineHeight,
      height: logLines.length * lineHeight,
      visible: logLines.slice(start, end),
    };
  }, [logLines, scrollTop, viewportHeight]);

  // Render toolbar with only task ID (for error states)
  const renderTaskIdOnly = () => {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '16px 0',
          marginBottom: '16px',
          borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Text type='secondary' style={{ fontSize: '14px' }}>
            {t('pages.taskLog.taskId', '任务ID')}:{' '}
          </Text>
          <Text style={{ fontSize: '14px' }}>{id}</Text>
        </div>
      </div>
    );
  };

  // Render toolbar
  const renderToolbar = () => {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 0',
          marginBottom: '16px',
          borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Text type='secondary' style={{ fontSize: '14px' }}>
            {t('pages.taskLog.taskId', '任务ID')}:{' '}
          </Text>
          <Text style={{ fontSize: '14px' }}>{id}</Text>
        </div>
        <Space wrap size='middle'>
          <Select
            value={tailLines}
            onChange={value => setTailLines(value)}
            className='w-140'
            style={{ minWidth: '140px' }}
          >
            <Select.Option value={100}>
              {t('pages.taskLog.last100Lines')}
            </Select.Option>
            <Select.Option value={500}>
              {t('pages.taskLog.last500Lines')}
            </Select.Option>
            <Select.Option value={1000}>
              {t('pages.taskLog.last1000Lines')}
            </Select.Option>
            <Select.Option value={0}>
              {t('pages.taskLog.allLogs')}
            </Select.Option>
          </Select>
          <Switch
            checkedChildren={t('pages.taskLog.autoRefresh')}
            unCheckedChildren={t('pages.taskLog.stopRefresh')}
            checked={autoRefresh}
            onChange={checked => {
              setAutoRefresh(checked);
              if (checked) {
                setFetchError(null);
              }
            }}
            disabled={isTaskInFinalState(task?.status)}
          />
          <Button icon={<SyncOutlined />} onClick={handleManualRefresh}>
            {t('pages.taskLog.refreshLogs')}
          </Button>
          <Search
            placeholder={t('pages.taskLog.searchLogContent')}
            allowClear
            enterButton={<SearchOutlined />}
            onSearch={handleSearch}
            className='w-250'
            style={{ minWidth: '250px' }}
          />
          <Button
            type='primary'
            icon={<DownloadOutlined />}
            onClick={handleDownload}
          >
            {t('pages.taskLog.downloadLogs')}
          </Button>
          <Button
            icon={
              fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />
            }
            onClick={toggleFullscreen}
          >
            {fullscreen
              ? t('pages.taskLog.exitFullscreen')
              : t('pages.taskLog.fullscreen')}
          </Button>
        </Space>
      </div>
    );
  };

  // Render log container
  const renderLogContainer = () => {
    return (
      <div style={{ position: 'relative' }}>
        {searchTerm && (
          <Alert
            message={t('pages.taskLog.searchResults', { searchTerm })}
            type='info'
            showIcon
            closable
            onClose={() => {
              setSearchTerm('');
              searchTermRef.current = '';
              resetSlsLogState();
              setLogLoading(true);
              setTimeout(() => {
                fetchLogsRef.current?.(true);
              }, 0);
            }}
            className='mb-16'
          />
        )}

        {fetchError && (
          <Alert
            message={t('pages.taskLog.autoRefreshError')}
            description={
              <div>
                <p>{fetchError}</p>
                <p>{t('pages.taskLog.autoRefreshPaused')}</p>
              </div>
            }
            type='warning'
            showIcon
            icon={<WarningOutlined />}
            closable
            action={
              <Button size='small' type='primary' onClick={handleManualRefresh}>
                {t('pages.taskLog.refreshNow')}
              </Button>
            }
            onClose={() => setFetchError(null)}
            className='mb-16'
          />
        )}

        {logLoading && logLines.length === 0 ? (
          <div
            className='log-viewer flex justify-center align-center'
            style={{ height: getLogContainerHeight() }}
          >
            <LoadingSpinner
              text={t('pages.taskLog.loadingLogs', '日志加载中...')}
              size='large'
            />
          </div>
        ) : logLines.length === 0 && hasLogLoadCompleted ? (
          <div
            className='flex justify-center align-center flex-column'
            style={{ minHeight: '200px', backgroundColor: '#ffffff' }}
          >
            <Alert
              description={t('pages.taskLog.logEmpty')}
              type='info'
              showIcon
              style={{ background: 'transparent', border: 'none' }}
            />
          </div>
        ) : (
          <div className='log-viewer'>
            <div
              ref={handleLogContainerRef}
              className='log-viewer-scrollbar'
              onScroll={handleLogScroll}
              onWheel={handleLogWheel}
              style={{
                height: getLogContainerHeight(),
                overflow: 'auto',
                fontFamily:
                  '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace',
                fontSize: '13px',
                lineHeight: `${lineHeight}px`,
                position: 'relative',
              }}
            >
              {tailLines === 0 && (hasMoreHistory || isHistoryLoading) && (
                <div
                  style={{
                    position: 'absolute',
                    top: '8px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    zIndex: 6,
                    padding: '4px 12px',
                    borderRadius: '12px',
                    color: '#cdd6f4',
                    background: 'rgba(26, 27, 46, 0.88)',
                    pointerEvents: 'none',
                  }}
                >
                  {isHistoryLoading
                    ? t('pages.taskLog.loadingHistory', '正在加载历史日志...')
                    : t(
                        'pages.taskLog.scrollUpForHistory',
                        '向上滚动加载更早日志'
                      )}
                </div>
              )}
              {logLoading && (
                <div
                  style={{
                    position: 'sticky',
                    top: 0,
                    zIndex: 5,
                    display: 'flex',
                    justifyContent: 'center',
                    padding: '8px 0',
                    background: 'rgba(26, 27, 46, 0.88)',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
                  }}
                >
                  <LoadingSpinner
                    text={t('pages.taskLog.loadingLogs', '日志加载中...')}
                    size='small'
                  />
                </div>
              )}
              <div
                style={{
                  height: virtualWindow.height,
                  position: 'relative',
                }}
              >
                <div
                  style={{
                    position:
                      virtualWindow.height === undefined
                        ? 'relative'
                        : 'absolute',
                    top: virtualWindow.top,
                    left: 0,
                    right: 0,
                  }}
                >
                  {virtualWindow.visible.map((line, index) => (
                    <React.Fragment key={virtualWindow.start + index}>
                      {formatLogLine(line, virtualWindow.start + index + 1)}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {showScrollToBottom && (
          <Button
            type='text'
            onClick={handleScrollToBottomClick}
            style={{
              position: 'absolute',
              bottom: '24px',
              right: '24px',
              zIndex: 10,
              borderRadius: '50%',
              width: '40px',
              height: '40px',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
              backgroundColor: 'rgba(30, 30, 46, 0.9)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
            }}
            icon={
              <DownOutlined style={{ fontSize: '20px', color: '#89b4fa' }} />
            }
          />
        )}
      </div>
    );
  };

  // Get container style
  const getContainerStyle = () => {
    if (fullscreen) {
      return {
        padding: '0',
        height: '100vh',
        width: '100vw',
        position: 'fixed' as const,
        top: 0,
        left: 0,
        zIndex: 1000,
        backgroundColor: '#ffffff',
      };
    }
    return {};
  };

  useEffect(() => {
    return () => {
      if (errorRetryTimerRef.current) {
        clearTimeout(errorRetryTimerRef.current);
      }
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, []);

  if (loading) {
    return (
      <div style={{ height: '80vh' }}>
        <LoadingSpinner
          text={t('pages.taskLog.loadingTask', '任务信息加载中...')}
          size='large'
          className='flex justify-center align-center'
        />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={fullscreen ? '' : 'page-container'}
        style={{
          padding: fullscreen ? '0' : undefined,
          height: fullscreen ? '100vh' : 'auto',
          width: fullscreen ? '100vw' : 'auto',
          position: fullscreen ? 'fixed' : 'relative',
          top: fullscreen ? 0 : 'auto',
          left: fullscreen ? 0 : 'auto',
          zIndex: fullscreen ? 1000 : 'auto',
          backgroundColor: '#ffffff',
        }}
      >
        {!fullscreen && (
          <div className='page-header-wrapper'>
            <PageHeader
              title={t('pages.taskLog.title', '任务日志')}
              icon={<MonitorOutlined />}
              level={3}
              extra={
                isStatusRefreshing && (
                  <Tooltip title='refreshing...'>
                    <span className='ml-8'>
                      <LoadingSpinner size='small' showText={false} />
                    </span>
                  </Tooltip>
                )
              }
            />
          </div>
        )}
        <div
          className={fullscreen ? '' : 'jobs-content-wrapper'}
          style={{ backgroundColor: '#ffffff' }}
        >
          {renderTaskIdOnly()}
          <div
            className='flex justify-center align-center'
            style={{ minHeight: '60vh', backgroundColor: '#ffffff' }}
          >
            <Alert
              description={error}
              type='error'
              showIcon
              style={{ background: 'transparent', border: 'none' }}
            />
          </div>
        </div>
      </div>
    );
  }

  if (fullscreen) {
    return (
      <div style={getContainerStyle()}>
        {renderToolbar()}
        {renderLogContainer()}
      </div>
    );
  }

  return (
    <div className='page-container'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.taskLog.title', '任务日志')}
          icon={<MonitorOutlined />}
          level={3}
          extra={
            isStatusRefreshing && (
              <Tooltip title='refreshing...'>
                <span className='ml-8'>
                  <LoadingSpinner size='small' showText={false} />
                </span>
              </Tooltip>
            )
          }
        />
      </div>
      <div className='jobs-content-wrapper'>
        {renderToolbar()}
        {renderLogContainer()}
      </div>
    </div>
  );
};

export default TaskLogs;
