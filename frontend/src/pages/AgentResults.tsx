/**
 * @file AgentResults.tsx
 * @description Results page for A2A / MCP agent protocol tasks
 */
import {
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  StopOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  message,
  Modal,
  Space,
  Statistic,
  Table,
  Tabs,
  Tooltip,
} from 'antd';
import html2canvas from 'html2canvas';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { agentTaskApi, clusterApi, monitoringApi } from '@/api/services';
import { IconTooltip } from '@/components/ui/IconTooltip';
import { LoadingSpinner } from '@/components/ui/LoadingState';
import { PageHeader } from '@/components/ui/PageHeader';
import { AgentTask, Cluster } from '@/types/job';
import { getStoredUser } from '@/utils/auth';
import { getFixedTableProps, UI_CONFIG } from '@/utils/constants';
import { formatDate } from '@/utils/date';

const ACTIVE_STATUSES = new Set(['created', 'queuing', 'running', 'stopping']);

const statisticWrapperStyle: React.CSSProperties = {
  textAlign: 'left',
};

const statisticValueStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-start',
  width: '100%',
  textAlign: 'left',
};

type SampleSummary = {
  count?: number;
  avg?: number;
  min?: number;
  p50?: number;
  p95?: number;
  p99?: number;
  max?: number;
};

type OverviewMetric = {
  key: string;
  title: React.ReactNode;
  value: string | number;
  suffix?: React.ReactNode;
};

const toFiniteNumber = (value: unknown): number | undefined => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : undefined;
};

const msToSeconds = (value: unknown): number | undefined => {
  const numeric = toFiniteNumber(value);
  return numeric === undefined ? undefined : numeric / 1000;
};

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
  if (numericValue >= 99.99 && numericValue < 100) {
    return numericValue.toFixed(5);
  }
  return numericValue.toFixed(2);
};

const formatSeconds = (value: unknown): string => {
  const seconds = msToSeconds(value);
  return seconds === undefined ? '-' : seconds.toFixed(3);
};

const AgentResults: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<AgentTask | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<Record<string, any>>({});
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [validatedEngineId, setValidatedEngineId] = useState<string | null>(
    null
  );
  const configCardRef = useRef<HTMLDivElement | null>(null);
  const overviewCardRef = useRef<HTMLDivElement | null>(null);
  const metricsDetailCardRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setError(null);
      const [taskResponse, resultResponse] = await Promise.all([
        agentTaskApi.get(id),
        agentTaskApi.getResults(id),
      ]);
      setTask(taskResponse.data);
      const resultBody: any = resultResponse.data;
      setRows(
        Array.isArray(resultBody?.results)
          ? resultBody.results.filter(
              (item: any) => item.metric_type !== 'protocol_summary'
            )
          : []
      );
      setMetrics(resultBody?.protocol_metrics || {});
    } catch (err: any) {
      const nextError =
        err?.response?.data?.message ||
        t('pages.results.fetchProtocolMetricsFailed');
      setError(nextError);
      message.error(nextError);
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (!id || !task || !ACTIVE_STATUSES.has(task.status)) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const statusRes = await agentTaskApi.getStatus(id);
        const statusData = statusRes.data as any;
        if (statusData) {
          setTask(prev =>
            prev
              ? {
                  ...prev,
                  status: statusData.status,
                  error_message: statusData.error_message,
                  updated_at: statusData.updated_at,
                }
              : prev
          );
          if (!ACTIVE_STATUSES.has(statusData.status)) {
            load();
          }
        }
      } catch {
        // ignore polling errors
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [id, load, task?.status]);

  useEffect(() => {
    const rawEngineId = task?.engine_id;
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
          setValidatedEngineId(null);
        }
      }
    };

    validateEngineId();
    return () => {
      cancelled = true;
    };
  }, [task?.engine_id]);

  useEffect(() => {
    const fetchClusters = async () => {
      try {
        const res = await clusterApi.getAllClusters();
        const list = Array.isArray(res)
          ? res
          : Array.isArray((res as any)?.data)
            ? (res as any).data
            : Array.isArray((res as any)?.data?.clusters)
              ? (res as any).data.clusters
              : [];
        setClusters(list);
      } catch (err) {
        console.error('Failed to fetch clusters:', err);
      }
    };
    fetchClusters();
  }, []);

  const clusterName = useMemo(() => {
    if (!task?.cluster_id) return '';
    const cluster = clusters.find(c => c.id === task.cluster_id);
    return cluster ? cluster.name : task.cluster_id;
  }, [clusters, task?.cluster_id]);

  const isA2A = task?.protocol === 'a2a';
  const hasMetrics = Object.keys(metrics).length > 0;
  const isTaskRunning = task?.status === 'running';
  const currentUsername = useMemo(() => getStoredUser()?.username || '', []);
  const canStopTask = useMemo(() => {
    const creator = task?.created_by;
    if (creator === '-') return true;
    if (!creator || !currentUsername) return false;
    return creator === currentUsername;
  }, [task?.created_by, currentUsername]);

  const metricExplanations: Record<string, string> = t(
    'pages.results.metricExplanations',
    { returnObjects: true }
  ) as Record<string, string>;
  const metricLabels: Record<string, string> = t('pages.results.metricLabels', {
    returnObjects: true,
  }) as Record<string, string>;
  const statisticExplanations: Record<string, string> = t(
    'pages.results.statisticExplanations',
    { returnObjects: true }
  ) as Record<string, string>;

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

  const renderMetricType = (text: string) => {
    const label = metricLabels[text] || text;
    const explanation = metricExplanations[text];
    if (!explanation) return label;
    return (
      <span>
        {label}{' '}
        <Tooltip title={explanation}>
          <InfoCircleOutlined className='ml-4' />
        </Tooltip>
      </span>
    );
  };

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
          await agentTaskApi.stop(id);
          message.success(t('pages.jobs.stopSuccess'));
          const taskRes = await agentTaskApi.get(id);
          setTask(taskRes.data);
        } catch {
          message.error(t('pages.jobs.stopFailed'));
        } finally {
          setIsStopping(false);
        }
      },
    });
  }, [canStopTask, id, t]);

  const handleDownloadReport = async () => {
    setIsDownloading(true);
    message.loading({
      content: t('pages.results.generatingReport'),
      key: 'downloadReport',
      duration: 0,
    });

    try {
      if (
        !configCardRef.current ||
        !overviewCardRef.current ||
        !metricsDetailCardRef.current
      ) {
        message.error(t('pages.results.reportComponentsNotLoaded'));
        return;
      }

      const elementsToCapture = [
        { ref: configCardRef, title: t('pages.results.taskInfo') },
        { ref: overviewCardRef, title: t('pages.results.resultsOverview') },
        {
          ref: metricsDetailCardRef,
          title: t('pages.results.metricsDetail'),
        },
      ];

      const canvases = await Promise.all(
        elementsToCapture.map(async elementInfo => {
          if (elementInfo.ref.current) {
            return html2canvas(elementInfo.ref.current, {
              useCORS: true,
              scale: 2,
              backgroundColor: '#ffffff',
            } as any);
          }
          return null;
        })
      );

      const validCanvases = canvases.filter(
        (canvas): canvas is HTMLCanvasElement =>
          canvas !== null && canvas.width > 0 && canvas.height > 0
      );
      if (validCanvases.length === 0) {
        throw new Error(t('pages.results.unableToCaptureContent'));
      }

      const padding = 30;
      const horizontalPadding = 80;
      let totalHeight = 0;
      let maxWidth = 0;
      validCanvases.forEach(canvas => {
        totalHeight += canvas.height;
        if (canvas.width > maxWidth) {
          maxWidth = canvas.width;
        }
      });
      if (validCanvases.length > 0) {
        totalHeight += (validCanvases.length - 1) * padding;
      }

      const mergedCanvas = document.createElement('canvas');
      mergedCanvas.width = maxWidth + horizontalPadding * 2;
      mergedCanvas.height = totalHeight;
      const ctx = mergedCanvas.getContext('2d');
      if (!ctx) {
        throw new Error(t('pages.results.unableToCreateCanvas'));
      }

      ctx.fillStyle = 'white';
      ctx.fillRect(0, 0, mergedCanvas.width, mergedCanvas.height);

      let currentY = 0;
      validCanvases.forEach((canvas, index) => {
        ctx.drawImage(canvas, horizontalPadding, currentY);
        currentY += canvas.height;
        if (index < validCanvases.length - 1) {
          currentY += padding;
        }
      });

      const image = mergedCanvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = image;
      link.download = `task-results-${task?.name || task?.id || ''}.png`;
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

  const transitions = useMemo(
    () =>
      Object.entries(metrics.state_transition_latency_ms || {}).map(
        ([transition, summary]) => ({
          metric_type: transition,
          request_count: (summary as SampleSummary).count,
          avg_response_time: (summary as SampleSummary).avg,
          min_response_time: (summary as SampleSummary).min,
          max_response_time: (summary as SampleSummary).max,
          percentile_95_response_time: (summary as SampleSummary).p95,
        })
      ),
    [metrics.state_transition_latency_ms]
  );

  const scenarioDistribution = useMemo(() => {
    const configuredScenarios = isA2A
      ? task?.a2a_scenarios || []
      : task?.mcp_calls || [];
    const configuredWeights = Object.fromEntries(
      configuredScenarios.map(scenario => [
        String(scenario.id || ''),
        Number(scenario.weight || 1),
      ])
    );
    const scenarioNames = Object.fromEntries(
      configuredScenarios.map(scenario => [
        String(scenario.id || ''),
        String(scenario.name || scenario.id || ''),
      ])
    );
    const weights = Object.keys(configuredWeights).length
      ? configuredWeights
      : metrics.scenario_weights || {};
    const selections = metrics.scenario_selections || {};
    const totalWeight = Object.values(weights).reduce<number>(
      (sum, value) => sum + Number(value || 0),
      0
    );
    const totalSelections = Object.values(selections).reduce<number>(
      (sum, value) => sum + Number(value || 0),
      0
    );
    return Object.entries(weights).map(([scenarioId, weight]) => ({
      scenarioId,
      scenarioName: scenarioNames[scenarioId] || scenarioId,
      weight: Number(weight),
      expectedRate: totalWeight ? Number(weight) / totalWeight : 0,
      selections: Number(selections[scenarioId] || 0),
      actualRate: totalSelections
        ? Number(selections[scenarioId] || 0) / totalSelections
        : undefined,
    }));
  }, [isA2A, metrics.scenario_selections, metrics.scenario_weights, task]);

  const latencyRows = useMemo(() => {
    const items: Array<{ metric_type: string; sample?: SampleSummary }> = [];
    if (!isA2A) {
      const ttfe = metrics.time_to_first_event_ms || metrics.ttft_ms;
      const endToEnd =
        metrics.end_to_end_latency_ms || metrics.response_time_ms;
      if (ttfe) {
        items.push({ metric_type: 'TTFE', sample: ttfe });
      }
      if (endToEnd) {
        items.push({ metric_type: 'End_to_end', sample: endToEnd });
      }
    }
    return items.filter(item => item.sample?.count);
  }, [isA2A, metrics]);

  const a2aRequestRows = useMemo(
    () => rows.filter(row => String(row.metric_type || '').startsWith('A2A ')),
    [rows]
  );

  const executionModeLabel = useMemo(() => {
    switch (task?.a2a_mode) {
      case 'async_poll':
        return t('components.createAgentTaskForm.asyncPoll');
      case 'stream':
        return t('components.createAgentTaskForm.streamSse');
      case 'sync':
        return t('components.createAgentTaskForm.sync');
      default:
        return '-';
    }
  }, [t, task?.a2a_mode]);

  const { RESULTS_COL } = UI_CONFIG;

  const latencyColumns = [
    {
      title: t('pages.results.metricType'),
      dataIndex: 'metric_type',
      key: 'metric_type',
      width: RESULTS_COL.METRIC_TYPE,
      ellipsis: true,
      render: renderMetricType,
    },
    {
      title: t('pages.results.sampleCount'),
      dataIndex: 'count',
      key: 'count',
      width: RESULTS_COL.COUNT,
      align: 'left' as const,
      render: (_: unknown, record: { sample?: SampleSummary }) =>
        record.sample?.count != null
          ? Number(record.sample.count).toLocaleString()
          : '0',
    },
    {
      title: t('pages.results.meanLatency'),
      dataIndex: 'avg',
      key: 'avg',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: (_: unknown, record: { sample?: SampleSummary }) =>
        formatSeconds(record.sample?.avg),
    },
    {
      title: t('pages.results.maxLatency'),
      dataIndex: 'max',
      key: 'max',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: (_: unknown, record: { sample?: SampleSummary }) =>
        formatSeconds(record.sample?.max),
    },
    {
      title: t('pages.results.minLatency'),
      dataIndex: 'min',
      key: 'min',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: (_: unknown, record: { sample?: SampleSummary }) =>
        formatSeconds(record.sample?.min),
    },
    {
      title: t('pages.results.p95Latency'),
      dataIndex: 'p95',
      key: 'p95',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: (_: unknown, record: { sample?: SampleSummary }) =>
        formatSeconds(record.sample?.p95),
    },
    {
      title: t('pages.results.medianLatency'),
      dataIndex: 'p50',
      key: 'p50',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: (_: unknown, record: { sample?: SampleSummary }) =>
        formatSeconds(record.sample?.p50),
    },
  ];

  const operationColumns = [
    {
      title: t('pages.results.metricType'),
      dataIndex: 'metric_type',
      key: 'metric_type',
      width: RESULTS_COL.METRIC_TYPE,
      ellipsis: true,
      render: renderMetricType,
    },
    {
      title: t('pages.results.sampleCount'),
      dataIndex: 'request_count',
      key: 'request_count',
      width: RESULTS_COL.COUNT,
      align: 'left' as const,
      render: (value: number | undefined) =>
        value != null ? value.toLocaleString() : '-',
    },
    {
      title: t('pages.results.failureCount'),
      dataIndex: 'failure_count',
      key: 'failure_count',
      width: RESULTS_COL.FAILURE,
      align: 'left' as const,
      render: (value: number | undefined) => {
        if (value == null) return '-';
        const num = value;
        return (
          <span style={num > 0 ? { color: 'var(--color-error)' } : undefined}>
            {num.toLocaleString()}
          </span>
        );
      },
    },
    {
      title: t('pages.results.meanLatency'),
      dataIndex: 'avg_response_time',
      key: 'avg_response_time',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: formatSeconds,
    },
    {
      title: t('pages.results.minLatency'),
      dataIndex: 'min_response_time',
      key: 'min_response_time',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: formatSeconds,
    },
    {
      title: t('pages.results.maxLatency'),
      dataIndex: 'max_response_time',
      key: 'max_response_time',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: formatSeconds,
    },
    {
      title: t('pages.results.p95Latency'),
      dataIndex: 'percentile_95_response_time',
      key: 'percentile_95_response_time',
      width: RESULTS_COL.LATENCY,
      align: 'left' as const,
      render: formatSeconds,
    },
  ];

  const transitionColumns = [
    ...operationColumns.filter(column => column.key !== 'failure_count'),
    {
      title: '',
      key: '_spacer',
      width: RESULTS_COL.FAILURE,
      render: () => null,
      onHeaderCell: () => ({ className: 'results-table-spacer' }),
      onCell: () => ({ className: 'results-table-spacer' }),
    },
  ];
  const a2aTableProps = getFixedTableProps(operationColumns);

  const renderOverviewMetrics = () => {
    const ratioToPercent = (value: unknown) => {
      const numeric = toFiniteNumber(value);
      return numeric === undefined ? undefined : numeric * 100;
    };

    const overviewMetrics: OverviewMetric[] = [];

    if (isA2A) {
      const elapsed = toFiniteNumber(metrics.elapsed_seconds);
      const submissions = toFiniteNumber(metrics.submissions);
      const terminalTasks = toFiniteNumber(metrics.terminal_tasks);
      const completedTasks = toFiniteNumber(metrics.completed_tasks);

      // Task submission rate mirrors the A2A SendMessage / SendStreamingMessage
      // event rate from the response-latency table (Locust `rps`), so the value
      // and unit stay consistent with that row. Fall back to the backend-derived
      // submission rate only when the Locust rows are not yet available.
      const sendMessageEventRate = a2aRequestRows
        .filter(
          row =>
            String(row.metric_type || '').startsWith('A2A SendMessage') ||
            String(row.metric_type || '').startsWith('A2A SendStreamingMessage')
        )
        .reduce((sum, row) => {
          const rps = toFiniteNumber(row.rps);
          return rps !== undefined ? sum + rps : sum;
        }, 0);
      const submissionRate =
        sendMessageEventRate > 0
          ? sendMessageEventRate
          : (toFiniteNumber(metrics.task_submission_rate) ??
            (elapsed && submissions !== undefined
              ? submissions / elapsed
              : undefined));

      // Terminal task throughput mirrors the A2A end-to-end event rate from the
      // response-latency table (Locust `rps`), since that event fires once per
      // task reaching a terminal state. Fall back to the backend-derived rate
      // only when the Locust rows are not yet available.
      const endToEndEventRate = a2aRequestRows
        .filter(row =>
          String(row.metric_type || '').startsWith('A2A end-to-end')
        )
        .reduce((sum, row) => {
          const rps = toFiniteNumber(row.rps);
          return rps !== undefined ? sum + rps : sum;
        }, 0);
      const terminalThroughput =
        endToEndEventRate > 0
          ? endToEndEventRate
          : (toFiniteNumber(metrics.terminal_task_throughput) ??
            (elapsed && terminalTasks !== undefined
              ? terminalTasks / elapsed
              : undefined));

      // Completed task throughput has no Locust row counterpart (the end-to-end
      // event covers all terminal states, not just `completed`). Derive it from
      // the Locust-based terminal throughput × completion rate so the two
      // throughput cards stay internally consistent (e.g. equal when completion
      // is 100%); fall back to the backend-derived value when unavailable.
      const completionRate = toFiniteNumber(
        metrics.terminal_task_completion_rate ??
          metrics.terminal_completion_rate
      );
      const completedThroughput =
        terminalThroughput !== undefined && completionRate !== undefined
          ? terminalThroughput * completionRate
          : (toFiniteNumber(metrics.completed_task_throughput) ??
            (elapsed && completedTasks !== undefined
              ? completedTasks / elapsed
              : undefined));

      overviewMetrics.push(
        {
          key: 'submissionRate',
          title: createTitleWithTooltip(
            t('pages.results.taskSubmissionRate'),
            'Task Submission Rate'
          ),
          value: formatMetricValue(submissionRate, 2),
        },
        {
          key: 'completedThroughput',
          title: createTitleWithTooltip(
            t('pages.results.completedTaskThroughput'),
            'Completed Task Throughput'
          ),
          value: formatMetricValue(completedThroughput, 2),
        },
        {
          key: 'terminalThroughput',
          title: createTitleWithTooltip(
            t('pages.results.terminalTaskThroughput'),
            'Terminal Task Throughput'
          ),
          value: formatMetricValue(terminalThroughput, 2),
        },
        {
          key: 'submissionSuccessRate',
          title: createTitleWithTooltip(
            t('pages.results.taskAcceptanceRate'),
            'Task Acceptance Rate'
          ),
          value: formatSuccessRate(
            ratioToPercent(
              metrics.task_acceptance_rate ??
                metrics.task_submission_success_rate
            )
          ),
          suffix: '%',
        },
        {
          key: 'terminalTaskCompletionRate',
          title: createTitleWithTooltip(
            t('pages.results.terminalTaskCompletionRate'),
            'Terminal Task Completion Rate'
          ),
          value: formatSuccessRate(
            ratioToPercent(
              metrics.terminal_task_completion_rate ??
                metrics.terminal_completion_rate
            )
          ),
          suffix: '%',
        },
        {
          key: 'compositeFailureRate',
          title: createTitleWithTooltip(
            t('pages.results.compositeFailureRate'),
            'Composite Failure Rate'
          ),
          value: formatSuccessRate(
            ratioToPercent(
              metrics.composite_failure_rate ?? metrics.total_failure_rate
            )
          ),
          suffix: '%',
        }
      );
    } else {
      const elapsed = toFiniteNumber(metrics.elapsed_seconds);
      const toolCalls = toFiniteNumber(metrics.tool_calls);
      const completedCalls =
        toFiniteNumber(metrics.completed_tool_calls) ?? toolCalls;
      const successfulCalls = toFiniteNumber(metrics.successful_tool_calls);
      const toolCallRequestRate =
        toFiniteNumber(metrics.tool_call_request_rate) ??
        toFiniteNumber(metrics.tool_call_rps) ??
        toFiniteNumber(metrics.tool_calls_per_second);
      const toolCallThroughput =
        toFiniteNumber(metrics.tool_call_throughput) ??
        toFiniteNumber(metrics.completion_throughput) ??
        (elapsed && completedCalls !== undefined
          ? completedCalls / elapsed
          : undefined);
      const successfulToolCallThroughput =
        toFiniteNumber(metrics.successful_tool_call_throughput) ??
        toFiniteNumber(metrics.successful_throughput) ??
        (elapsed && successfulCalls !== undefined
          ? successfulCalls / elapsed
          : undefined);

      overviewMetrics.push(
        {
          key: 'successRate',
          title: createTitleWithTooltip(
            t('pages.results.toolCallSuccessRate'),
            'Tool Call Success Rate'
          ),
          value: formatSuccessRate(
            ratioToPercent(metrics.tool_call_success_rate)
          ),
          suffix: '%',
        },
        {
          key: 'toolCallRequestRate',
          title: createTitleWithTooltip(
            t('pages.results.toolCallRequestRate'),
            'Tool Call Request Rate'
          ),
          value: formatMetricValue(toolCallRequestRate, 2),
        },
        {
          key: 'toolCallThroughput',
          title: createTitleWithTooltip(
            t('pages.results.toolCallThroughput'),
            'Tool Call Throughput'
          ),
          value: formatMetricValue(toolCallThroughput, 2),
        },
        {
          key: 'successfulToolCallThroughput',
          title: createTitleWithTooltip(
            t('pages.results.successfulToolCallThroughput'),
            'Successful Tool Call Throughput'
          ),
          value: formatMetricValue(successfulToolCallThroughput, 2),
        },
        {
          key: 'contentThroughput',
          title: createTitleWithTooltip(
            t('pages.results.contentThroughput'),
            'Content Throughput (B/s)'
          ),
          value: formatMetricValue(
            metrics.content_throughput_bytes_per_second,
            2
          ),
        }
      );
    }

    return (
      <div className='results-overview-grid'>
        {overviewMetrics.map(metric => (
          <Statistic
            key={metric.key}
            title={metric.title}
            value={metric.value}
            suffix={metric.value === '-' ? undefined : metric.suffix}
            style={statisticWrapperStyle}
            valueStyle={statisticValueStyle}
          />
        ))}
      </div>
    );
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
            <span className='info-value'>{task?.id || id}</span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.taskName')}</span>
            <span className='info-value'>
              {task?.name || t('pages.results.taskName')}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.targetUrl')}</span>
            <Tooltip title={task?.target_url || 'N/A'}>
              <span className='info-value info-value-ellipsis'>
                {task?.target_url || 'N/A'}
              </span>
            </Tooltip>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.createdTime')}</span>
            <span className='info-value'>
              {task?.created_at ? formatDate(task.created_at) : 'N/A'}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.protocol')}</span>
            <span className='info-value'>
              {task?.protocol ? task.protocol.toUpperCase() : '-'}
            </span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>
              {t('pages.results.protocolVersion')}
            </span>
            <span className='info-value'>{task?.protocol_version || '-'}</span>
          </div>
          {isA2A && (
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.executionMode')}
              </span>
              <span className='info-value'>{executionModeLabel}</span>
            </div>
          )}
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.datasetFile')}</span>
            {task?.dataset_file ? (
              <Tooltip title={task.dataset_file}>
                <span className='info-value info-value-ellipsis'>
                  {task.dataset_file.split('/').pop() || task.dataset_file}
                </span>
              </Tooltip>
            ) : (
              <span className='info-value'>-</span>
            )}
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>
              {t('pages.results.concurrentUsers')}
            </span>
            <span className='info-value'>{task?.concurrent_users ?? 0}</span>
          </div>
          <div className='info-grid-item'>
            <span className='info-label'>
              {t('pages.results.testDuration')}
            </span>
            <span className='info-value'>{task?.duration || 0} s</span>
          </div>
          {!isA2A && (
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.tokenCountPath')}
              </span>
              <span className='info-value'>
                {task?.token_count_path || '-'}
              </span>
            </div>
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
          <div className='info-grid-item'>
            <span className='info-label'>{t('pages.results.env')}</span>
            <span className='info-value'>
              {clusterName || task?.cluster_id || '-'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );

  const renderScenarioWeightSection = () => {
    if (!scenarioDistribution.length) return null;

    return (
      <div className='results-section unified-section'>
        <div className='section-header'>
          <span className='section-title'>
            {t('pages.results.scenarioWeights')}
          </span>
        </div>
        <div className='section-content'>
          <div className='scenario-weight-list'>
            {scenarioDistribution.map(scenario => {
              const expectedPercent = scenario.expectedRate * 100;
              const actualPercent =
                scenario.actualRate === undefined
                  ? undefined
                  : scenario.actualRate * 100;

              return (
                <div className='scenario-weight-card' key={scenario.scenarioId}>
                  <div className='scenario-weight-card-header'>
                    <div className='scenario-weight-identity'>
                      <span className='scenario-weight-name'>
                        {scenario.scenarioName}
                      </span>
                      <span className='scenario-weight-id'>
                        {t('pages.results.scenarioId')}: {scenario.scenarioId}
                      </span>
                    </div>
                    <span className='scenario-weight-badge'>
                      {t('pages.results.configuredWeight')} {scenario.weight}
                    </span>
                  </div>

                  <div className='scenario-share-row'>
                    <div className='scenario-share-meta'>
                      <span>{t('pages.results.expectedShare')}</span>
                      <strong>{expectedPercent.toFixed(2)}%</strong>
                    </div>
                    <div
                      className='scenario-share-track'
                      role='progressbar'
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={expectedPercent}
                      aria-label={t('pages.results.expectedShare')}
                    >
                      <span
                        className='scenario-share-fill scenario-share-fill-expected'
                        style={{
                          width: `${Math.min(expectedPercent, 100)}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div className='scenario-share-row'>
                    <div className='scenario-share-meta'>
                      <span>
                        {t('pages.results.actualShare')}
                        <small>
                          {t('pages.results.actualSelections')}:{' '}
                          {scenario.selections > 0
                            ? scenario.selections.toLocaleString()
                            : '-'}
                        </small>
                      </span>
                      <strong>
                        {actualPercent === undefined
                          ? '-'
                          : `${actualPercent.toFixed(2)}%`}
                      </strong>
                    </div>
                    <div
                      className='scenario-share-track'
                      role='progressbar'
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={actualPercent ?? 0}
                      aria-label={t('pages.results.actualShare')}
                    >
                      {actualPercent !== undefined && (
                        <span
                          className='scenario-share-fill scenario-share-fill-actual'
                          style={{
                            width: `${Math.min(actualPercent, 100)}%`,
                          }}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const renderStatisticsContent = () => {
    if (!hasMetrics && !rows.length) {
      return (
        <div>
          {renderTaskInfoSection()}
          <div
            className='flex justify-center align-center'
            style={{ minHeight: '30vh', backgroundColor: '#ffffff' }}
          >
            <Alert
              description={error || t('pages.results.noTestResultsAvailable')}
              type={error ? 'error' : 'info'}
              showIcon
              style={{ background: 'transparent', border: 'none' }}
            />
          </div>
        </div>
      );
    }

    return (
      <div>
        {renderTaskInfoSection()}

        <div
          className='results-section unified-section results-overview'
          ref={overviewCardRef}
        >
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.results.resultsOverview')}
            </span>
          </div>
          <div className='section-content'>
            {hasMetrics ? (
              renderOverviewMetrics()
            ) : (
              <Alert
                message={t('pages.results.noValidResults')}
                type='warning'
                showIcon
                className='btn-transparent'
              />
            )}
          </div>
        </div>

        <div ref={metricsDetailCardRef}>
          {!isA2A && (
            <div className='results-section unified-section'>
              <div className='section-header'>
                <span className='section-title'>
                  {t('pages.results.responseTime')}
                </span>
              </div>
              <div className='section-content'>
                <Table
                  dataSource={latencyRows}
                  columns={latencyColumns}
                  rowKey='metric_type'
                  pagination={false}
                  className='modern-table'
                  {...getFixedTableProps(latencyColumns)}
                />
              </div>
            </div>
          )}

          {isA2A && (
            <div className='results-section unified-section'>
              <div className='section-header'>
                <span className='section-title'>
                  {t('pages.results.responseTime')}
                </span>
              </div>
              <div className='section-content'>
                <Table
                  className='modern-table'
                  rowKey={(record, index) =>
                    String(record.id || record.metric_type || index)
                  }
                  dataSource={a2aRequestRows}
                  pagination={false}
                  columns={operationColumns}
                  {...a2aTableProps}
                />
              </div>
            </div>
          )}

          {isA2A && (
            <div className='results-section unified-section'>
              <div className='section-header'>
                <span className='section-title'>
                  {t('pages.results.stateTransitionLatency')}
                </span>
              </div>
              <div className='section-content'>
                <Table
                  className='modern-table'
                  pagination={false}
                  rowKey='metric_type'
                  dataSource={transitions}
                  columns={transitionColumns}
                  {...a2aTableProps}
                />
              </div>
            </div>
          )}

          {renderScenarioWeightSection()}
        </div>
      </div>
    );
  };

  return (
    <div className='page-container results-page'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.results.title', 'Test Results')}
          icon={<FileTextOutlined />}
          level={3}
          onBack={() =>
            navigate(`/jobs?tab=${task?.protocol === 'mcp' ? 'mcp' : 'a2a'}`)
          }
          backText={t('pages.results.backToJobs')}
        />
      </div>

      {loading && !task ? (
        <div className='loading-container'>
          <LoadingSpinner
            text={t('pages.results.loadingResultData')}
            size='large'
            className='text-center'
          />
        </div>
      ) : error && !task ? (
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
            defaultActiveKey='statistics'
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
                <Button
                  type='primary'
                  icon={<DownloadOutlined />}
                  onClick={handleDownloadReport}
                  loading={isDownloading}
                  disabled={loading || (!hasMetrics && !rows.length)}
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
                children: renderStatisticsContent(),
              },
            ]}
            className='unified-tabs'
          />
        </div>
      )}
    </div>
  );
};

export default AgentResults;
