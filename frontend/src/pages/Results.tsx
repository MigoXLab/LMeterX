/**
 * @file Results.tsx
 * @description Results page component
 * @author Charm
 * @copyright 2025
 * */
import {
  DownloadOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  StopOutlined,
  UnorderedListOutlined,
  UpOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Col,
  message,
  Modal,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tooltip,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import html2canvas from 'html2canvas';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { analysisApi, jobApi, monitoringApi, resultApi } from '../api/services';
import { CopyButton } from '../components/ui/CopyButton';
import { IconTooltip } from '../components/ui/IconTooltip';
import { LoadingSpinner } from '../components/ui/LoadingState';
import MarkdownRenderer from '../components/ui/MarkdownRenderer';
import { PageHeader } from '../components/ui/PageHeader';
import { useLanguage } from '../contexts/LanguageContext';
import { RealtimeMetricPoint } from '../types/job';
import { getStoredUser } from '../utils/auth';
import { formatDate } from '../utils/date';

const SUMMARY_METRIC_TYPES = new Set([
  'token_metrics',
  'Total_time',
  'Time_to_first_reasoning_token',
  'Time_to_first_output_token',
  'Time_to_reasoning_completion',
  'Time_to_output_completion',
  'failure',
  'total_tokens_per_second',
  'completion_tokens_per_second',
]);

const statisticWrapperStyle: React.CSSProperties = {
  textAlign: 'left',
};

const statisticValueStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-start',
  width: '100%',
  textAlign: 'left',
};

const TaskResults: React.FC = () => {
  const { t } = useTranslation();
  const { currentLanguage } = useLanguage();
  const { id } = useParams<{ id: string }>();
  const getTabStorageKey = useCallback(
    (jobId?: string) => `results-active-tab:${jobId || 'unknown'}`,
    []
  );
  const getStoredActiveTab = useCallback(
    (jobId?: string) => {
      if (typeof window === 'undefined') return 'statistics';
      const saved = window.localStorage.getItem(getTabStorageKey(jobId));
      return saved === 'charts' || saved === 'statistics'
        ? saved
        : 'statistics';
    },
    [getTabStorageKey]
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<any[]>([]);
  const [taskInfo, setTaskInfo] = useState<any>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisModalVisible, setAnalysisModalVisible] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [showAnalysisReport, setShowAnalysisReport] = useState(false);
  const [isAnalysisExpanded, setIsAnalysisExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState(() => getStoredActiveTab(id));
  const [metricsData, setMetricsData] = useState<RealtimeMetricPoint[]>([]);
  const [validatedEngineId, setValidatedEngineId] = useState<string | null>(
    null
  );
  const [isStopping, setIsStopping] = useState(false);
  const lastMetricTs = useRef<number>(0);
  const fetchingRef = useRef(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevStatusRef = useRef<string | undefined>();
  const configCardRef = useRef<HTMLDivElement | null>(null);
  const overviewCardRef = useRef<HTMLDivElement | null>(null);
  const detailsCardRef = useRef<HTMLDivElement | null>(null);
  const metricsDetailCardRef = useRef<HTMLDivElement | null>(null);
  const chartsRef = useRef<HTMLDivElement | null>(null);

  const getNumericValue = (item: any, fields: string[]): number | undefined => {
    if (!item) {
      return undefined;
    }

    for (let index = 0; index < fields.length; index += 1) {
      const field = fields[index];
      if (field in item) {
        const rawValue = item[field];
        if (rawValue !== null && rawValue !== undefined && rawValue !== '') {
          const numericValue = Number(rawValue);
          if (Number.isFinite(numericValue)) {
            return numericValue;
          }
        }
      }
    }

    return undefined;
  };

  const getRequestCountValue = (item?: any): number | undefined =>
    getNumericValue(item, ['num_requests', 'request_count']);

  const getFailureCountValue = (item?: any): number | undefined =>
    getNumericValue(item, ['num_failures', 'failure_count']);

  const getBuiltInDatasetLabel = (value?: number | null) => {
    switch (value) {
      case 1:
        return t('pages.results.datasetOptionShareGPTPartial');
      case 2:
        return t('pages.results.datasetOptionVisionSelfBuilt');
      default:
        return t('pages.results.datasetOptionTextSelfBuilt');
    }
  };

  // Function to fetch analysis result
  const fetchAnalysisResult = async () => {
    if (!id) return;

    try {
      const response = await analysisApi.getAnalysis(id);
      if (response.data?.status === 'success' && response.data?.data) {
        setAnalysisResult(response.data.data);
        // if there is analysis result, show the report and expand it
        setShowAnalysisReport(true);
        setIsAnalysisExpanded(true);
      } else if (response.data?.status === 'error') {
        // Log the error but don't show to user as this is just fetching existing analysis
        console.warn('Failed to fetch analysis result:', response.data?.error);
      }
    } catch (err: any) {
      // Analysis not found or other error - ignore for fetching
      console.warn('Error fetching analysis result:', err);
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;

      try {
        setLoading(true);
        setError(null);

        // Handle task information acquisition separately
        try {
          const taskResponse = await jobApi.getJob(id);
          setTaskInfo(taskResponse.data);
        } catch (err: any) {
          // Failed to get task info - continue with results
        }

        // Try to get results
        try {
          const resultsResponse = await resultApi.getJobResult(id);

          if (resultsResponse.data?.status === 'error') {
            throw new Error(
              resultsResponse.data.error || t('common.fetchTasksFailed')
            );
          }

          if (Array.isArray(resultsResponse.data)) {
            setResults(resultsResponse.data);
          } else if (
            resultsResponse.data &&
            Array.isArray(resultsResponse.data.results)
          ) {
            setResults(resultsResponse.data.results);
          } else if (
            resultsResponse.data &&
            Array.isArray(resultsResponse.data.data)
          ) {
            setResults(resultsResponse.data.data);
          } else {
            setResults([]);
            setError(t('pages.results.noData'));
          }
        } catch (err: any) {
          setError(err.message || t('common.fetchTasksFailed'));
        }
      } finally {
        setLoading(false);
      }
    };

    fetchData();

    // Fetch analysis result if available
    fetchAnalysisResult();
  }, [id]);

  // Restore active tab when navigating to a different task ID.
  useEffect(() => {
    setActiveTab(getStoredActiveTab(id));
  }, [id, getStoredActiveTab]);

  // Validate task engine id against monitoring engine list.
  // Old task snapshots may contain stale ids (e.g. engine-01).
  useEffect(() => {
    const rawEngineId = taskInfo?.engine_id;
    if (!rawEngineId) {
      setValidatedEngineId(null);
      return;
    }

    let cancelled = false;
    const validateEngineId = async () => {
      try {
        const resp = await monitoringApi.getEngines();
        const engines = ((resp.data as any)?.data ?? []) as Array<{
          engine_id?: string;
        }>;
        const exists = engines.some(engine => engine.engine_id === rawEngineId);
        if (!cancelled) {
          setValidatedEngineId(exists ? rawEngineId : null);
        }
      } catch {
        if (!cancelled) {
          // Fallback to "-" when engine list cannot be resolved.
          setValidatedEngineId(null);
        }
      }
    };

    validateEngineId();
    return () => {
      cancelled = true;
    };
  }, [taskInfo?.engine_id]);

  // Fetch real-time metrics incrementally (with lock to prevent concurrent fetches)
  const fetchMetrics = useCallback(async () => {
    if (!id || fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const since = lastMetricTs.current;
      const res = await jobApi.getRealtimeMetrics(id, since);
      const body: any = res.data;
      const points: RealtimeMetricPoint[] = body?.data ?? [];
      if (points.length > 0) {
        // Filter out duplicate points: VM query_range is inclusive on start
        // boundary, so the point at `since` may be returned again.
        const newPoints =
          since > 0 ? points.filter(p => p.timestamp > since) : points;
        if (newPoints.length > 0) {
          setMetricsData(prev => [...prev, ...newPoints]);
          lastMetricTs.current = Math.max(...newPoints.map(p => p.timestamp));
        }
      }
    } catch {
      // Silently ignore fetch errors during polling
    } finally {
      fetchingRef.current = false;
    }
  }, [id]);

  // Poll task status while task is running/pending to detect completion
  useEffect(() => {
    if (!id || !taskInfo) return;
    const isActive =
      taskInfo.status === 'running' || taskInfo.status === 'pending';
    if (!isActive) return;

    const interval = setInterval(async () => {
      try {
        const statusRes = await jobApi.getJobStatus(id);
        const statusData = statusRes.data as any;
        if (statusData) {
          setTaskInfo((prev: any) => ({
            ...prev,
            status: statusData.status,
            error_message: statusData.error_message,
            updated_at: statusData.updated_at,
          }));
          // Refresh results when task completes
          if (
            statusData.status !== 'running' &&
            statusData.status !== 'pending'
          ) {
            try {
              const resultsResponse = await resultApi.getJobResult(id);
              if (
                resultsResponse.data &&
                Array.isArray(resultsResponse.data.results)
              ) {
                setResults(resultsResponse.data.results);
              }
            } catch {
              // ignore
            }
          }
        }
      } catch {
        // ignore
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [id, taskInfo?.status]);

  // Poll real-time metrics when charts tab is active.
  // - Active tasks (running/pending): poll every 2 s.
  // - On transition from active → terminal: schedule a delayed final fetch
  //   so that late-arriving VM data is captured.
  // - Completed tasks opened fresh: single fetch to load all historical data.
  useEffect(() => {
    if (!taskInfo) return;

    const currentStatus = taskInfo.status;
    const prev = prevStatusRef.current;
    prevStatusRef.current = currentStatus;

    const isActive = currentStatus === 'running' || currentStatus === 'pending';
    const wasActive = prev === 'running' || prev === 'pending';

    let completionTimer: ReturnType<typeof setTimeout> | null = null;

    if (activeTab === 'charts' && id) {
      // Seed lastMetricTs from task creation time so the backend queries
      // a precise window instead of a wide fallback (e.g. 2 h).
      if (lastMetricTs.current === 0 && taskInfo.created_at) {
        const createdTs = new Date(taskInfo.created_at).getTime() / 1000;
        if (createdTs > 0) {
          lastMetricTs.current = createdTs;
        }
      }

      // Always do an initial / incremental fetch when switching to charts tab
      fetchMetrics();

      if (isActive) {
        // Keep polling while the task is active
        pollingRef.current = setInterval(fetchMetrics, 2000);
      } else if (wasActive) {
        // Task just finished – schedule a delayed final fetch to capture
        // metrics that may still be ingested by VictoriaMetrics.
        completionTimer = setTimeout(() => {
          // Reset to task creation time for a full re-fetch
          const createdTs = taskInfo.created_at
            ? new Date(taskInfo.created_at).getTime() / 1000
            : 0;
          lastMetricTs.current = createdTs;
          setMetricsData([]);
          fetchMetrics();
        }, 3000);
      }
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      if (completionTimer) {
        clearTimeout(completionTimer);
      }
    };
  }, [activeTab, taskInfo?.status, id, fetchMetrics]);

  // Whether the task is currently in a stoppable state
  const isTaskRunning =
    taskInfo?.status === 'running' || taskInfo?.status === 'pending';
  const currentUsername = useMemo(() => getStoredUser()?.username || '', []);
  const canStopTask = useMemo(() => {
    const creator = taskInfo?.created_by;
    // Backward compatibility: legacy anonymous tasks use "-" as creator.
    if (creator === '-') return true;
    if (!creator || !currentUsername) return false;
    return creator === currentUsername;
  }, [taskInfo?.created_by, currentUsername]);

  // Handle stop test with confirmation dialog
  const handleStopTest = useCallback(() => {
    if (!id) return;
    if (!canStopTask) {
      message.warning(t('pages.jobs.ownerOnly'));
      return;
    }
    Modal.confirm({
      title: t('pages.jobs.stopConfirmTitle'),
      icon: <ExclamationCircleOutlined />,
      content: t('pages.jobs.stopConfirmContent'),
      okText: t('pages.jobs.confirmStop'),
      okButtonProps: {
        style: {
          backgroundColor: '#fa8c16',
          borderColor: '#fa8c16',
        },
      },
      cancelText: t('common.cancel'),
      onOk: async () => {
        setIsStopping(true);
        try {
          await jobApi.stopJob(id);
          message.success(t('pages.jobs.stopSuccess'));
          const taskRes = await jobApi.getJob(id);
          setTaskInfo(taskRes.data);
        } catch {
          message.error(t('pages.jobs.stopFailed'));
        } finally {
          setIsStopping(false);
        }
      },
    });
  }, [id, t, canStopTask]);

  // Format timestamp for chart x-axis display (HH:mm:ss)
  const formatChartTime = useCallback((ts: number) => {
    const d = new Date(ts * 1000);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  }, []);

  // Format timestamp for tooltip header (YYYY/M/D HH:mm:ss)
  const formatTooltipTime = useCallback((ts: number) => {
    const d = new Date(ts * 1000);
    return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  }, []);

  // Shared tooltip config
  const chartTooltip = useMemo(
    () => ({
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const list = Array.isArray(params) ? params : [params];
        if (list.length === 0) return '';
        const header = `<div style="margin-bottom:4px;font-weight:600">${formatTooltipTime(Number(list[0].axisValue))}</div>`;
        const rows = list
          .map(
            (p: any) =>
              `<div>${p.marker} ${p.seriesName}<span style="float:right;margin-left:20px;font-weight:600">${p.value ?? '-'}</span></div>`
          )
          .join('');
        return header + rows;
      },
    }),
    [formatTooltipTime]
  );

  // --- LLM per-metric names and color palette for response time chart ---
  type LLMMetricName =
    | 'Total_time'
    | 'Time_to_first_reasoning_token'
    | 'Time_to_first_output_token'
    | 'Time_to_reasoning_completion'
    | 'Time_to_output_completion';

  const LLM_METRIC_NAMES: LLMMetricName[] = [
    'Total_time',
    'Time_to_first_reasoning_token',
    'Time_to_first_output_token',
    'Time_to_reasoning_completion',
    'Time_to_output_completion',
  ];

  const LLM_METRIC_COLORS: Record<LLMMetricName, string> = {
    Total_time: '#1890ff',
    Time_to_first_reasoning_token: '#faad14',
    Time_to_first_output_token: '#52c41a',
    Time_to_reasoning_completion: '#eb2f96',
    Time_to_output_completion: '#722ed1',
  };

  // Discover which LLM metric names actually have data across all snapshots
  const availableMetricNames = useMemo(() => {
    const found = new Set<string>();
    metricsData.forEach(p => {
      if (p.metrics) {
        LLM_METRIC_NAMES.forEach(name => {
          if (p.metrics![name]) {
            found.add(name);
          }
        });
      }
    });
    return LLM_METRIC_NAMES.filter(n => found.has(n));
  }, [metricsData]);

  // ECharts: Response Time chart
  const responseTimeOption = useMemo(() => {
    if (metricsData.length === 0) return {};
    const timestamps = metricsData.map(p => p.timestamp);

    // Build one series per available LLM metric (avg only, no P95)
    const series: Array<{
      name: string;
      type: 'line';
      data: (number | null)[];
      smooth: boolean;
      symbol: string;
      symbolSize: number;
      showSymbol: boolean;
      connectNulls: boolean;
      itemStyle: { color: string };
      lineStyle: { color: string };
    }> = availableMetricNames.map(metricName => ({
      name: metricName,
      type: 'line' as const,
      data: metricsData.map(p => {
        const val = p.metrics?.[metricName]?.avg_response_time;
        return val != null ? Number(val.toFixed(1)) : null;
      }),
      smooth: true,
      symbol: 'emptyCircle',
      symbolSize: 4,
      showSymbol: false,
      connectNulls: true,
      itemStyle: { color: LLM_METRIC_COLORS[metricName] ?? '#1890ff' },
      lineStyle: { color: LLM_METRIC_COLORS[metricName] ?? '#1890ff' },
    }));

    // Fallback if no per-metric detail: show aggregate avg (backward compat)
    if (series.length === 0) {
      series.push({
        name: t('pages.results.chartAvgRT', 'Avg Response Time'),
        type: 'line' as const,
        data: metricsData.map(p =>
          p.avg_response_time != null
            ? Number(p.avg_response_time.toFixed(1))
            : null
        ),
        smooth: true,
        symbol: 'emptyCircle',
        symbolSize: 4,
        showSymbol: false,
        connectNulls: true,
        itemStyle: { color: '#1890ff' },
        lineStyle: { color: '#1890ff' },
      });
    }

    return {
      tooltip: chartTooltip,
      legend: {
        data: series.map(s => s.name),
        bottom: 0,
        type: 'scroll' as const,
      },
      grid: { top: 40, right: 30, bottom: 60, left: 60 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: {
          formatter: (val: number) => formatChartTime(val),
          rotate: 0,
          hideOverlap: true,
        },
      },
      yAxis: { type: 'value' as const, name: 'ms' },
      series,
    };
  }, [metricsData, formatChartTime, chartTooltip, t, availableMetricNames]);

  // ECharts: RPS & Failures chart
  // RPS: prefer Total_time metric, fallback to api_path metric, then aggregate
  // Failures/s: prefer failure metric, fallback to api_path metric, then aggregate
  const rpsOption = useMemo(() => {
    if (metricsData.length === 0) return {};
    const timestamps = metricsData.map(p => p.timestamp);

    // Resolve api_path for fallback lookup
    const apiPath = taskInfo?.api_path || '';

    const rpsData = metricsData.map(p => {
      if (p.metrics) {
        // Prefer Total_time's rps
        const totalEntry = p.metrics.Total_time;
        if (totalEntry?.current_rps != null) {
          return Number(totalEntry.current_rps.toFixed(2));
        }
        // Fallback: api_path metric
        const apiEntry = apiPath ? p.metrics[apiPath] : undefined;
        if (apiEntry?.current_rps != null) {
          return Number(apiEntry.current_rps.toFixed(2));
        }
      }
      // Final fallback: aggregate rps
      return p.current_rps != null ? Number(p.current_rps.toFixed(2)) : 0;
    });

    const failData = metricsData.map(p => {
      if (p.metrics) {
        // Prefer failure metric's fail_per_sec
        const failEntry = p.metrics.failure;
        if (failEntry?.current_fail_per_sec != null) {
          return Number(failEntry.current_fail_per_sec.toFixed(2));
        }
        // Fallback: api_path metric
        const apiEntry = apiPath ? p.metrics[apiPath] : undefined;
        if (apiEntry?.current_fail_per_sec != null) {
          return Number(apiEntry.current_fail_per_sec.toFixed(2));
        }
      }
      // Final fallback: aggregate fail_per_sec
      return p.current_fail_per_sec != null
        ? Number(p.current_fail_per_sec.toFixed(2))
        : 0;
    });

    return {
      tooltip: chartTooltip,
      legend: {
        data: ['RPS', t('pages.results.chartFailPerSec', 'Failures/s')],
        bottom: 0,
      },
      grid: { top: 40, right: 30, bottom: 50, left: 60 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: {
          formatter: (val: number) => formatChartTime(val),
          hideOverlap: true,
        },
      },
      yAxis: { type: 'value' as const, name: 'req/s' },
      series: [
        {
          name: 'RPS',
          type: 'line',
          data: rpsData,
          smooth: true,
          symbol: 'emptyCircle',
          symbolSize: 4,
          showSymbol: false,
          itemStyle: { color: '#52c41a' },
          lineStyle: { color: '#52c41a' },
          areaStyle: { opacity: 0.15, color: '#52c41a' },
        },
        {
          name: t('pages.results.chartFailPerSec', 'Failures/s'),
          type: 'line',
          data: failData,
          smooth: true,
          symbol: 'emptyCircle',
          symbolSize: 4,
          showSymbol: false,
          itemStyle: { color: '#f5222d' },
        },
      ],
    };
  }, [metricsData, formatChartTime, chartTooltip, t, taskInfo?.api_path]);

  // ECharts: Concurrent Users chart
  const usersOption = useMemo(() => {
    if (metricsData.length === 0) return {};
    const timestamps = metricsData.map(p => p.timestamp);
    return {
      tooltip: chartTooltip,
      legend: {
        data: [t('pages.results.chartConcurrentUsers', 'Concurrent Users')],
        bottom: 0,
      },
      grid: { top: 40, right: 30, bottom: 50, left: 60 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: {
          formatter: (val: number) => formatChartTime(val),
          hideOverlap: true,
        },
      },
      yAxis: { type: 'value' as const, name: 'users' },
      series: [
        {
          name: t('pages.results.chartConcurrentUsers', 'Concurrent Users'),
          type: 'line',
          data: metricsData.map(p => p.current_users),
          smooth: false,
          symbol: 'emptyCircle',
          symbolSize: 4,
          showSymbol: metricsData.length <= 60,
          step: 'end' as const,
          areaStyle: { opacity: 0.1 },
          itemStyle: { color: '#b37feb' },
          lineStyle: { color: '#b37feb' },
        },
      ],
    };
  }, [metricsData, formatChartTime, chartTooltip, t]);

  // Handle manual refresh of real-time metrics
  const [isRefreshingMetrics, setIsRefreshingMetrics] = useState(false);
  const handleRefreshMetrics = useCallback(async () => {
    if (!id) return;
    setIsRefreshingMetrics(true);
    try {
      // Reset to task creation time for a full re-fetch
      const createdTs = taskInfo?.created_at
        ? new Date(taskInfo.created_at).getTime() / 1000
        : 0;
      lastMetricTs.current = createdTs;
      setMetricsData([]);
      await fetchMetrics();
    } finally {
      setIsRefreshingMetrics(false);
    }
  }, [id, taskInfo?.created_at, fetchMetrics]);

  // Render the Charts tab content
  const renderChartsContent = () => {
    if (metricsData.length === 0) {
      const isRunning =
        taskInfo?.status === 'running' || taskInfo?.status === 'pending';
      return (
        <div
          className='flex justify-center align-center'
          style={{ minHeight: '30vh' }}
        >
          <Alert
            description={
              isRunning
                ? t(
                    'pages.results.chartsWaiting',
                    'Waiting for real-time metrics data...'
                  )
                : t(
                    'pages.results.chartsNoData',
                    'No real-time metrics data available for this task.'
                  )
            }
            type='info'
            showIcon
            style={{ background: 'transparent', border: 'none' }}
          />
        </div>
      );
    }

    return (
      <>
        {/* Retention tip – outside chartsRef so it is excluded from download screenshots */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            marginBottom: 4,
          }}
        >
          <span style={{ fontSize: 12, color: '#faad14' }}>
            <ExclamationCircleOutlined style={{ marginRight: 4 }} />
            {t(
              'pages.results.chartsRetentionTip',
              'Please download the report in time. Real-time metrics data will be automatically cleaned up after 7 days.'
            )}
          </span>
        </div>

        <div
          ref={chartsRef}
          style={{ display: 'flex', flexDirection: 'column', gap: 0 }}
        >
          {/* Response Time Chart */}
          <div className='results-section unified-section'>
            <div className='section-header'>
              <span className='section-title'>
                {t('pages.results.chartResponseTime', 'Response Time')}
              </span>
            </div>
            <div className='section-content'>
              <ReactECharts
                option={responseTimeOption}
                style={{ height: 300 }}
                notMerge
                lazyUpdate
              />
            </div>
          </div>

          {/* RPS & Failures Chart */}
          <div className='results-section unified-section'>
            <div className='section-header'>
              <span className='section-title'>
                {t('pages.results.chartRps', 'RPS & Failures')}
              </span>
            </div>
            <div className='section-content'>
              <ReactECharts
                option={rpsOption}
                style={{ height: 260 }}
                notMerge
                lazyUpdate
              />
            </div>
          </div>

          {/* Concurrent Users Chart */}
          <div className='results-section unified-section'>
            <div className='section-header'>
              <span className='section-title'>
                {t('pages.results.chartConcurrentUsers', 'Concurrent Users')}
              </span>
            </div>
            <div className='section-content'>
              <ReactECharts
                option={usersOption}
                style={{ height: 240 }}
                notMerge
                lazyUpdate
              />
            </div>
          </div>
        </div>
      </>
    );
  };

  // Define metric results
  const TpsResult = results.find(item => item.metric_type === 'token_metrics');
  const CompletionResult = results.find(
    item => item.metric_type === 'Total_time'
  );
  const firstReasoningToken = results.find(
    item => item.metric_type === 'Time_to_first_reasoning_token'
  );
  const firstOutputToken = results.find(
    item => item.metric_type === 'Time_to_first_output_token'
  );
  // Use Time_to_first_reasoning_token if available, otherwise use Time_to_first_output_token
  const firstTokenResult = firstReasoningToken || firstOutputToken;
  const outputCompletionResult = results.find(
    item => item.metric_type === 'Time_to_output_completion'
  );
  const failResult = results.find(item => item.metric_type === 'failure');

  const requestMetricTypeSet = useMemo(() => {
    const typeSet = new Set<string>();

    if (taskInfo?.api_path) {
      typeSet.add(taskInfo.api_path);
    }

    results.forEach(item => {
      const hasRequestStats =
        getRequestCountValue(item) !== undefined ||
        getFailureCountValue(item) !== undefined;

      if (
        item?.metric_type &&
        !SUMMARY_METRIC_TYPES.has(item.metric_type) &&
        hasRequestStats
      ) {
        typeSet.add(item.metric_type);
      }
    });

    return typeSet;
  }, [results, taskInfo?.api_path]);

  const calculateFailedRequests = () => {
    const failureRequests = getRequestCountValue(failResult);
    if (failureRequests !== undefined) {
      return failureRequests;
    }

    const fallbackFailures = getFailureCountValue(failResult);
    if (fallbackFailures !== undefined) {
      return fallbackFailures;
    }

    return 0;
  };

  // Check if we have any valid test results
  const hasValidResults =
    CompletionResult || firstTokenResult || outputCompletionResult || TpsResult;

  // Prepare table column definitions
  const metricExplanations: Record<string, string> = t(
    'pages.results.metricExplanations',
    { returnObjects: true }
  ) as Record<string, string>;
  const statisticExplanations: Record<string, string> = t(
    'pages.results.statisticExplanations',
    { returnObjects: true }
  ) as Record<string, string>;

  const columns = [
    {
      title: t('pages.results.metricType'),
      dataIndex: 'metric_type',
      key: 'metric_type',
      width: 200,
      ellipsis: true,
      render: (text: string) => {
        const explanation = metricExplanations[text];
        if (explanation) {
          return (
            <span>
              {text}{' '}
              <Tooltip title={explanation}>
                <InfoCircleOutlined className='ml-4' />
              </Tooltip>
            </span>
          );
        }
        return text;
      },
    },
    {
      title: t('pages.results.totalRequests'),
      dataIndex: 'request_count',
      key: 'request_count',
      width: 110,
      align: 'right' as const,
      render: (_: number, record: any) => {
        const requestCount = getRequestCountValue(record);
        return requestCount !== undefined ? requestCount.toLocaleString() : '0';
      },
    },
    {
      title: t('pages.results.avgResponseTime'),
      dataIndex: 'avg_response_time',
      key: 'avg_response_time',
      width: 120,
      align: 'right' as const,
      render: (text: number, record: any) => {
        if (!text) return '0.000';
        if (record.metric_type === 'Time_to_output_completion' && text < 10) {
          return text.toFixed(3);
        }
        return (text / 1000).toFixed(3);
      },
    },
    {
      title: t('pages.results.maxResponseTime'),
      dataIndex: 'max_response_time',
      key: 'max_response_time',
      width: 120,
      align: 'right' as const,
      render: (text: number, record: any) => {
        if (!text) return '0.000';
        if (record.metric_type === 'Time_to_output_completion' && text < 10) {
          return text.toFixed(3);
        }
        return (text / 1000).toFixed(3);
      },
    },
    {
      title: t('pages.results.minResponseTime'),
      dataIndex: 'min_response_time',
      key: 'min_response_time',
      width: 120,
      align: 'right' as const,
      render: (text: number, record: any) => {
        if (!text) return '0.000';
        if (record.metric_type === 'Time_to_output_completion' && text < 10) {
          return text.toFixed(3);
        }
        return (text / 1000).toFixed(3);
      },
    },
    {
      title: t('pages.results.p95ResponseTime'),
      dataIndex: 'percentile_95_response_time',
      key: 'percentile_95_response_time',
      width: 120,
      align: 'right' as const,
      render: (text: number, record: any) => {
        if (!text) return '0.000';
        if (record.metric_type === 'Time_to_output_completion' && text < 10) {
          return text.toFixed(3);
        }
        return (text / 1000).toFixed(3);
      },
    },
    {
      title: t('pages.results.medianResponseTime'),
      dataIndex: 'median_response_time',
      key: 'median_response_time',
      width: 120,
      align: 'right' as const,
      render: (text: number, record: any) => {
        if (!text) return '0.000';
        if (record.metric_type === 'Time_to_output_completion' && text < 10) {
          return text.toFixed(3);
        }
        return (text / 1000).toFixed(3);
      },
    },
    {
      title: t('pages.results.rps'),
      dataIndex: 'rps',
      key: 'rps',
      width: 100,
      align: 'right' as const,
      render: (text: number) => (text ? text.toFixed(2) : '0.00'),
    },
  ];

  type OverviewMetric = {
    key: string;
    title: React.ReactNode;
    value: string | number;
    suffix?: React.ReactNode;
  };

  const renderOverviewMetrics = () => {
    if (!hasValidResults) {
      return (
        <Alert
          message={t('pages.results.noValidResults')}
          type='warning'
          showIcon
          className='btn-transparent'
        />
      );
    }

    const failedRequestCount = calculateFailedRequests();
    const apiPathMetric = taskInfo?.api_path
      ? results.find(item => item.metric_type === taskInfo.api_path)
      : undefined;
    const apiPathRequestCount = getRequestCountValue(apiPathMetric);
    const completionRequests = getRequestCountValue(CompletionResult);
    const firstTokenRequests = getRequestCountValue(firstTokenResult);
    const outputCompletionRequests = getRequestCountValue(
      outputCompletionResult
    );

    const successCandidates = [
      completionRequests,
      firstTokenRequests,
      outputCompletionRequests,
    ].filter((count): count is number => count !== undefined);

    const fallbackSuccessRequests =
      successCandidates.find(count => count > 0) ??
      (successCandidates.length > 0 ? successCandidates[0] : 0) ??
      0;

    const totalRequestCount =
      apiPathRequestCount !== undefined
        ? apiPathRequestCount
        : fallbackSuccessRequests + failedRequestCount;

    const successfulRequestCount = Math.max(
      totalRequestCount - failedRequestCount,
      0
    );

    const actualSuccessRate =
      totalRequestCount > 0
        ? (successfulRequestCount / totalRequestCount) * 100
        : 0;

    const formatMetricValue = (
      value: number | null | undefined,
      decimals?: number
    ): string | number => {
      if (value === null || value === undefined) {
        return '-';
      }

      const numericValue = Number(value);
      if (!Number.isFinite(numericValue)) {
        return '-';
      }

      if (decimals !== undefined) {
        return numericValue.toFixed(decimals);
      }

      return numericValue;
    };

    // Smart format success rate: if close to 100% but not 100%, show more decimal places
    const formatSuccessRate = (
      rate: number | null | undefined
    ): string | number => {
      if (rate === null || rate === undefined) {
        return '-';
      }

      const numericValue = Number(rate);
      if (!Number.isFinite(numericValue)) {
        return '-';
      }

      // If close to 100% but not 100%, show 5 decimal places; otherwise show 2 decimal places
      if (numericValue >= 99.99 && numericValue < 100) {
        return numericValue.toFixed(5);
      }
      return numericValue.toFixed(2);
    };

    const createTitleWithTooltip = (
      label: string,
      tooltipKey?: string
    ): React.ReactNode => {
      if (!tooltipKey || !statisticExplanations[tooltipKey]) {
        return label;
      }

      return (
        <span>
          {label}
          <IconTooltip
            title={statisticExplanations[tooltipKey]}
            className='ml-4'
            color='#667eea'
          />
        </span>
      );
    };

    const isMeaningfulValue = (value: any): boolean => {
      if (value === null || value === undefined || value === '-') {
        return false;
      }
      if (typeof value === 'number') {
        return value !== 0;
      }
      if (typeof value === 'string') {
        const trimmed = value.trim();
        return trimmed !== '' && trimmed !== '0';
      }
      return true;
    };

    const ttftSeconds =
      firstTokenResult?.avg_response_time !== undefined &&
      firstTokenResult?.avg_response_time !== null
        ? firstTokenResult.avg_response_time / 1000
        : null;

    const ttftDisplay = formatMetricValue(ttftSeconds, 3);
    const hasTtft =
      isMeaningfulValue(ttftDisplay) &&
      isMeaningfulValue(firstTokenResult?.avg_response_time);

    const rpsValue = CompletionResult?.rps ?? firstTokenResult?.rps;
    const qpmValue =
      rpsValue !== null && rpsValue !== undefined
        ? Number(rpsValue) * 60
        : null;

    const firstRowMetrics: (OverviewMetric | null)[] = [
      {
        key: 'totalRequests',
        title: t('pages.results.totalRequests'),
        value: formatMetricValue(totalRequestCount),
      },
      {
        key: 'successRate',
        title: t('pages.results.successRate'),
        value: formatSuccessRate(actualSuccessRate),
        suffix: '%',
      },
      {
        key: 'qpm',
        title: 'QPM',
        value: formatMetricValue(qpmValue, 2),
      },
    ];

    if (hasTtft) {
      firstRowMetrics.push({
        key: 'ttft',
        title: t('pages.results.ttft'),
        value: ttftDisplay,
      });
    }

    const secondRowMetrics: (OverviewMetric | null)[] = [];

    if (isMeaningfulValue(TpsResult?.total_tps)) {
      secondRowMetrics.push({
        key: 'totalTps',
        title: createTitleWithTooltip(
          t('pages.results.totalTps'),
          'Total TPS (tokens/s)'
        ),
        value: formatMetricValue(TpsResult?.total_tps, 3),
      });
    }

    if (isMeaningfulValue(TpsResult?.completion_tps)) {
      secondRowMetrics.push({
        key: 'completionTps',
        title: createTitleWithTooltip(
          t('pages.results.completionTps'),
          'Completion TPS (tokens/s)'
        ),
        value: formatMetricValue(TpsResult?.completion_tps, 3),
      });
    }

    if (isMeaningfulValue(TpsResult?.avg_total_tokens_per_req)) {
      secondRowMetrics.push({
        key: 'avgTotalTpr',
        title: createTitleWithTooltip(
          t('pages.results.avgTotalTpr'),
          'Avg. Total TPR (tokens/req)'
        ),
        value: formatMetricValue(TpsResult?.avg_total_tokens_per_req, 3),
      });
    }

    if (isMeaningfulValue(TpsResult?.avg_completion_tokens_per_req)) {
      secondRowMetrics.push({
        key: 'avgCompletionTpr',
        title: createTitleWithTooltip(
          t('pages.results.avgCompletionTpr'),
          'Avg. Completion TPR (tokens/req)'
        ),
        value: formatMetricValue(TpsResult?.avg_completion_tokens_per_req, 3),
      });
    }

    const columnCount = Math.max(
      firstRowMetrics.length,
      secondRowMetrics.length,
      1
    );
    const colSpan = Math.max(Math.floor(24 / columnCount), 1);

    const paddedFirstRow = [...firstRowMetrics];
    while (paddedFirstRow.length < columnCount) {
      paddedFirstRow.push(null);
    }

    const paddedSecondRow = [...secondRowMetrics];
    while (paddedSecondRow.length < columnCount) {
      paddedSecondRow.push(null);
    }

    const hasSecondRow = secondRowMetrics.some(metric => metric);

    const renderRow = (metrics: (OverviewMetric | null)[], rowKey: string) => (
      <Row
        key={rowKey}
        gutter={16}
        className={rowKey === 'first' ? 'mb-16' : undefined}
        style={{ justifyContent: 'flex-start' }}
      >
        {metrics.map((metric, index) => (
          <Col span={colSpan} key={`${rowKey}-${metric?.key ?? index}`}>
            {metric ? (
              <Statistic
                title={metric.title}
                value={metric.value}
                suffix={metric.value === '-' ? undefined : metric.suffix}
                style={statisticWrapperStyle}
                valueStyle={statisticValueStyle}
              />
            ) : (
              <div style={{ minHeight: '1px' }} />
            )}
          </Col>
        ))}
      </Row>
    );

    return (
      <>
        {renderRow(paddedFirstRow, 'first')}
        {hasSecondRow && renderRow(paddedSecondRow, 'second')}
      </>
    );
  };

  // Function to handle AI Summary
  const handleAnalysis = async () => {
    if (!id) return;

    setIsAnalyzing(true);
    try {
      const response = await analysisApi.analyzeTasks([id], currentLanguage);

      // Check if the response indicates an error
      if (
        response.data?.status === 'error' ||
        response.data?.status === 'failed'
      ) {
        // Extract the most specific error message
        const errorMessage =
          response.data?.error_message || t('pages.results.analysisFailed');

        // If backend returns error_message, show it directly without prefix
        if (response.data?.error_message) {
          message.error(errorMessage);
        } else {
          // Only add prefix for generic errors
          message.error(
            t('pages.results.analysisFailedWithError', { error: errorMessage })
          );
        }
        return;
      }

      setAnalysisResult(response.data);
      setAnalysisModalVisible(false);
      setShowAnalysisReport(true);
      setIsAnalysisExpanded(true);
      message.success(t('pages.results.analysisCompleted'));

      // Fetch the analysis result to display
      await fetchAnalysisResult();
    } catch (err: any) {
      // Handle different types of errors
      let errorMessage = t('pages.results.analysisFailed');

      // Check for timeout errors specifically
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMessage =
          t('pages.results.analysisTimeout') ||
          'AI analysis timeout, please try again later';
      } else if (err.data) {
        // API error response - prioritize error_message over error
        if (err.data.error_message) {
          errorMessage = err.data.error_message;
        } else if (err.data.error) {
          errorMessage = err.data.error;
        } else if (err.data.detail) {
          errorMessage = err.data.detail;
        }
      } else if (err.message) {
        // Network or other error
        errorMessage = err.message;
      }

      // If backend returns error_message, show it directly without prefix
      if (err.data?.error_message) {
        message.error(errorMessage);
      } else {
        // Only add prefix for generic errors
        message.error(
          t('pages.results.analysisFailedWithError', { error: errorMessage })
        );
      }

      // Log the error for debugging
      console.error('AI analysis error:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Function to handle report download
  const handleDownloadReport = async () => {
    setIsDownloading(true);
    message.loading({
      content: 'Generating report...',
      key: 'downloadReport',
      duration: 0,
    });

    try {
      const elementsToCapture: {
        ref: React.RefObject<HTMLDivElement | null>;
        title: string;
      }[] = [];

      if (activeTab === 'charts') {
        if (!chartsRef.current) {
          message.error(t('pages.results.reportComponentsNotLoaded'));
          return;
        }
        elementsToCapture.push({
          ref: chartsRef,
          title: t('pages.results.tabCharts', 'Charts'),
        });
      } else {
        if (
          !configCardRef.current ||
          !overviewCardRef.current ||
          !metricsDetailCardRef.current
        ) {
          message.error(t('pages.results.reportComponentsNotLoaded'));
          return;
        }
        elementsToCapture.push(
          { ref: configCardRef, title: t('pages.results.taskInfo') },
          { ref: overviewCardRef, title: t('pages.results.resultsOverview') },
          {
            ref: metricsDetailCardRef,
            title: t('pages.results.metricsDetail'),
          }
        );
      }

      const canvases = await Promise.all(
        elementsToCapture.map(async elementInfo => {
          if (elementInfo.ref.current) {
            // Use html2canvas to convert DOM elements to canvas
            return html2canvas(elementInfo.ref.current, {
              useCORS: true, // This option is needed if there are cross-origin images in the Card
              scale: 2, // Increase image clarity, can be adjusted as needed
              backgroundColor: '#ffffff',
            } as any); // Add type assertion as any
          }
          return null;
        })
      );

      const validCanvases = canvases.filter(
        (canvas): canvas is HTMLCanvasElement =>
          canvas !== null && canvas.width > 0 && canvas.height > 0
      );
      if (validCanvases.length === 0) {
        throw new Error('Unable to capture any report content.');
      }

      // Calculate the total height and maximum width of the merged Canvas
      const padding = 30; // Vertical spacing between image blocks
      const horizontalPadding = 80; // Horizontal padding for left and right
      let totalHeight = 0; // Initialize total height
      let maxWidth = 0;

      validCanvases.forEach(canvas => {
        totalHeight += canvas.height;
        if (canvas.width > maxWidth) {
          maxWidth = canvas.width;
        }
      });
      // Add spacing between canvases
      if (validCanvases.length > 0) {
        totalHeight += (validCanvases.length - 1) * padding;
      }

      // Create a new Canvas for merging with horizontal padding
      const mergedCanvas = document.createElement('canvas');
      mergedCanvas.width = maxWidth + horizontalPadding * 2;
      mergedCanvas.height = totalHeight;
      const ctx = mergedCanvas.getContext('2d');

      if (!ctx) {
        throw new Error(t('pages.results.unableToCreateCanvas'));
      }

      // Set the background color of the merged image
      ctx.fillStyle = 'white';
      ctx.fillRect(0, 0, mergedCanvas.width, mergedCanvas.height);

      let currentY = 0;
      for (let i = 0; i < validCanvases.length; i++) {
        const canvas = validCanvases[i];

        // Draw screenshot with horizontal padding
        const offsetX = horizontalPadding;
        ctx.drawImage(canvas, offsetX, currentY);
        currentY += canvas.height;

        // Add block spacing
        if (i < validCanvases.length - 1) {
          currentY += padding;
        }
      }

      // Convert merged Canvas to image and download
      const image = mergedCanvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = image;
      const suffix = activeTab === 'charts' ? 'charts' : 'results';
      link.download = `task-${suffix}-${taskInfo?.name || taskInfo?.id || ''}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      message.success({
        content: t('pages.results.downloadSuccessful'),
        key: 'downloadReport',
        duration: 3,
      });
    } catch (err: any) {
      message.error({
        content: t('pages.results.downloadFailedWithError', {
          error: err.message || t('common.unknown'),
        }),
        key: 'downloadReport',
        duration: 4,
      });
    } finally {
      setIsDownloading(false);
    }
  };

  const renderTaskInfoSection = () => (
    <div className='results-section unified-section' ref={configCardRef}>
      <div className='section-header'>
        <span className='section-title'>{t('pages.results.taskInfo')}</span>
      </div>
      <div className='section-content'>
        <div className='info-grid'>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.taskId')}</span>
            <span className='info-value'>{taskInfo?.id || id}</span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.taskName')}</span>
            <span className='info-value'>
              {taskInfo?.name || t('pages.results.taskName')}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.targetUrl')}</span>
            <Tooltip
              title={
                taskInfo?.target_host && taskInfo?.api_path
                  ? `${taskInfo.target_host}${taskInfo.api_path}`
                  : taskInfo?.target_host || 'N/A'
              }
            >
              <span className='info-value info-value-ellipsis'>
                {taskInfo?.target_host && taskInfo?.api_path
                  ? `${taskInfo.target_host}${taskInfo.api_path}`
                  : taskInfo?.target_host || 'N/A'}
              </span>
            </Tooltip>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.createdTime')}</span>
            <span className='info-value'>
              {taskInfo?.created_at ? formatDate(taskInfo.created_at) : 'N/A'}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>
              {t('pages.results.datasetSource')}
            </span>
            <span className='info-value'>
              {(() => {
                if (taskInfo?.test_data === 'default') {
                  return t('pages.results.builtInDataset');
                }
                if (taskInfo?.test_data && taskInfo.test_data !== 'default') {
                  return t('pages.results.customDataset');
                }
                return '-';
              })()}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.datasetType')}</span>
            <span className='info-value'>
              {(() => {
                if (taskInfo?.test_data === 'default') {
                  return getBuiltInDatasetLabel(taskInfo?.chat_type);
                }
                return '-';
              })()}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.modelName')}</span>
            <span className='info-value'>{taskInfo?.model || 'none'}</span>
          </div>
          {(taskInfo?.load_mode || 'fixed') === 'fixed' ? (
            <>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.concurrentUsers')}
                </span>
                <span className='info-value'>
                  {taskInfo?.user_count || taskInfo?.concurrent_users || 0}
                </span>
              </div>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.testDuration')}
                </span>
                <span className='info-value'>{taskInfo?.duration || 0} s</span>
              </div>
            </>
          ) : (
            <>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.stepStartUsers', 'Start Users')}
                </span>
                <span className='info-value'>{taskInfo?.step_start_users}</span>
              </div>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.stepIncrement', 'Increment')}
                </span>
                <span className='info-value'>+{taskInfo?.step_increment}</span>
              </div>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.stepDuration', 'Step Duration')}
                </span>
                <span className='info-value'>{taskInfo?.step_duration} s</span>
              </div>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.stepMaxUsers', 'Max Users')}
                </span>
                <span className='info-value'>{taskInfo?.step_max_users}</span>
              </div>
              <div className='info-grid-item'>
                <span className='info-label'>
                  {t('pages.results.stepSustainDuration', 'Sustain Duration')}
                </span>
                <span className='info-value'>
                  {taskInfo?.step_sustain_duration} s
                </span>
              </div>
            </>
          )}
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.engineId')}</span>
            <span className='info-value'>
              {validatedEngineId ? (
                <Tooltip title={t('pages.results.viewEngineMonitor')}>
                  <a
                    href={`/system-monitor?engine_id=${encodeURIComponent(validatedEngineId)}`}
                    target='_blank'
                    rel='noopener noreferrer'
                    style={{ color: '#1677ff' }}
                  >
                    {validatedEngineId}
                  </a>
                </Tooltip>
              ) : (
                '-'
              )}
            </span>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className='page-container results-page'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.results.title', 'Test Results')}
          icon={<FileTextOutlined />}
          level={3}
        />
      </div>

      {loading ? (
        <div className='loading-container'>
          <LoadingSpinner
            text={t('pages.results.loadingResultData')}
            size='large'
            className='text-center'
          />
        </div>
      ) : error && !taskInfo ? (
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
      ) : (
        <div className='results-content'>
          <Tabs
            activeKey={activeTab}
            onChange={key => {
              setActiveTab(key);
              if (typeof window !== 'undefined') {
                window.localStorage.setItem(getTabStorageKey(id), key);
              }
            }}
            tabBarExtraContent={
              <Space>
                {isTaskRunning && canStopTask && (
                  <Tooltip title={t('pages.results.stopTest', 'Stop Test')}>
                    <Button
                      icon={<StopOutlined />}
                      onClick={handleStopTest}
                      loading={isStopping}
                      className='modern-button-stop-test'
                    >
                      {t('pages.results.stopTest', 'Stop Test')}
                    </Button>
                  </Tooltip>
                )}
                {activeTab === 'statistics' && (
                  <Button
                    icon={<RobotOutlined />}
                    onClick={() => setAnalysisModalVisible(true)}
                    loading={isAnalyzing}
                    disabled={
                      loading || !!error || !results || results.length === 0
                    }
                    className='modern-button-ai-summary'
                  >
                    {t('pages.results.aiSummary')}
                  </Button>
                )}
                <Button
                  type='primary'
                  icon={<DownloadOutlined />}
                  onClick={handleDownloadReport}
                  loading={isDownloading}
                  disabled={
                    loading ||
                    (activeTab === 'charts'
                      ? metricsData.length === 0
                      : !!error || !results || results.length === 0)
                  }
                  className='modern-button-primary-light'
                >
                  {t('pages.results.downloadReport')}
                </Button>
                <Button
                  type='primary'
                  icon={<UnorderedListOutlined />}
                  onClick={() => {
                    if (id) {
                      window.open(`/logs/task/${id}`, '_blank');
                    }
                  }}
                  disabled={!id}
                >
                  {t('pages.results.viewLogs')}
                </Button>
                {activeTab === 'charts' && (
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={handleRefreshMetrics}
                    loading={isRefreshingMetrics}
                  >
                    {t('pages.results.refreshCharts', 'Refresh')}
                  </Button>
                )}
              </Space>
            }
            items={[
              {
                key: 'statistics',
                label: (
                  <span className='tab-label'>
                    {t('pages.results.tabStatistics', 'Statistics')}
                  </span>
                ),
                children:
                  !results || results.length === 0 ? (
                    <div>
                      {renderTaskInfoSection()}
                      <div
                        className='flex justify-center align-center'
                        style={{
                          minHeight: '30vh',
                          backgroundColor: '#ffffff',
                        }}
                      >
                        <Alert
                          description={
                            error || t('pages.results.noTestResultsAvailable')
                          }
                          type={error ? 'error' : 'info'}
                          showIcon
                          style={{
                            background: 'transparent',
                            border: 'none',
                          }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div>
                      {/* AI Summary Report */}
                      {showAnalysisReport && analysisResult && (
                        <div className='results-section'>
                          <div className='section-header'>
                            <span className='section-title'>
                              {t('pages.results.aiSummary')}
                            </span>
                            <Space>
                              <CopyButton
                                text={analysisResult.analysis_report}
                                successMessage={t(
                                  'pages.results.analysisCopied'
                                )}
                                tooltip={t('pages.results.copyAnalysis')}
                              />
                              <Button
                                type='text'
                                size='small'
                                icon={
                                  isAnalysisExpanded ? (
                                    <UpOutlined />
                                  ) : (
                                    <DownOutlined />
                                  )
                                }
                                onClick={() =>
                                  setIsAnalysisExpanded(!isAnalysisExpanded)
                                }
                                style={{ padding: '4px 8px' }}
                              >
                                {isAnalysisExpanded
                                  ? t('pages.results.collapse')
                                  : t('pages.results.expand')}
                              </Button>
                            </Space>
                          </div>
                          {isAnalysisExpanded && (
                            <div className='section-content'>
                              <MarkdownRenderer
                                content={analysisResult.analysis_report}
                                className='analysis-content'
                              />
                            </div>
                          )}
                        </div>
                      )}

                      {/* Task Info */}
                      {renderTaskInfoSection()}

                      {/* Results Overview */}
                      <div
                        className='results-section unified-section'
                        ref={overviewCardRef}
                      >
                        <div className='section-header'>
                          <span className='section-title'>
                            {t('pages.results.resultsOverview')}
                          </span>
                        </div>
                        <div className='section-content'>
                          {renderOverviewMetrics()}
                        </div>
                      </div>

                      {/* Metrics Detail */}
                      <div
                        className='results-section unified-section'
                        ref={metricsDetailCardRef}
                      >
                        <div className='section-header'>
                          <span className='section-title'>
                            {t('pages.results.metricsDetail')}
                          </span>
                        </div>
                        <div className='section-content'>
                          <Table
                            dataSource={results.filter(
                              item =>
                                item.metric_type !==
                                  'total_tokens_per_second' &&
                                item.metric_type !==
                                  'completion_tokens_per_second' &&
                                item.metric_type !== 'token_metrics' &&
                                (results.length <= 1 ||
                                  !requestMetricTypeSet.has(item.metric_type))
                            )}
                            columns={columns}
                            rowKey='metric_type'
                            pagination={false}
                            scroll={{ x: 1000 }}
                            className='modern-table'
                          />
                        </div>
                      </div>

                      {/* Test Result Details */}
                      <div className='results-section' ref={detailsCardRef}>
                        <div className='section-header'>
                          <span className='section-title'>
                            {t('pages.results.resultDetails')}
                          </span>
                        </div>
                        <div className='section-content'>
                          <div style={{ position: 'relative' }}>
                            <pre
                              className='modal-pre'
                              style={{
                                backgroundColor: '#f5f5f5',
                                padding: '16px',
                                borderRadius: '8px',
                                overflow: 'auto',
                                maxHeight: '500px',
                              }}
                            >
                              <code>{JSON.stringify(results, null, 2)}</code>
                            </pre>
                            <div
                              style={{
                                position: 'absolute',
                                top: '8px',
                                right: '8px',
                              }}
                            >
                              <CopyButton
                                text={JSON.stringify(results, null, 2)}
                                successMessage={t(
                                  'pages.results.resultsCopied'
                                )}
                                tooltip={t('pages.results.copyResults')}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ),
              },
              {
                key: 'charts',
                label: (
                  <span className='tab-label'>
                    {t('pages.results.tabCharts', 'Charts')}
                  </span>
                ),
                children: renderChartsContent(),
              },
            ]}
            className='unified-tabs'
          />
        </div>
      )}

      {/* AI Summary Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <RobotOutlined style={{ color: 'var(--brand-primary)' }} />
            {t('pages.results.aiSummary')}
          </div>
        }
        open={analysisModalVisible}
        onCancel={() => setAnalysisModalVisible(false)}
        footer={null}
        width={500}
      >
        <div style={{ padding: '20px 0' }}>
          <Alert
            description={t('pages.results.pleaseEnsureCompleteResults')}
            type='info'
            showIcon
            style={{ marginBottom: '16px' }}
          />
        </div>
        <div style={{ textAlign: 'center', marginTop: '20px' }}>
          <Space>
            <Button
              type='primary'
              onClick={handleAnalysis}
              loading={isAnalyzing}
              icon={<RobotOutlined />}
              className='modern-button-primary-light'
            >
              {t('pages.results.startAnalysis')}
            </Button>
            <Button onClick={() => setAnalysisModalVisible(false)}>
              {t('common.cancel')}
            </Button>
          </Space>
        </div>
      </Modal>
    </div>
  );
};

export default TaskResults;
