/**
 * @file CommonResults.tsx
 * @description Results page for common API jobs with Statistics and Charts tabs
 */
import {
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  StopOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Col,
  Empty,
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

import { commonJobApi } from '@/api/services';
import { LoadingSpinner } from '@/components/ui/LoadingState';
import { PageHeader } from '@/components/ui/PageHeader';
import { RealtimeMetricPoint } from '@/types/job';
import { formatDate } from '@/utils/date';

const CommonResults: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [taskInfo, setTaskInfo] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [activeTab, setActiveTab] = useState('charts');
  const [metricsData, setMetricsData] = useState<RealtimeMetricPoint[]>([]);
  const lastMetricTs = useRef<number>(0);
  const fetchingRef = useRef(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const overviewRef = useRef<HTMLDivElement | null>(null);
  const taskRef = useRef<HTMLDivElement | null>(null);
  const chartsRef = useRef<HTMLDivElement | null>(null);
  const metricsTableRef = useRef<HTMLDivElement | null>(null);

  // Fetch task info and results
  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      setLoading(true);
      try {
        const [taskRes, resultRes] = await Promise.all([
          commonJobApi.getJob(id),
          commonJobApi.getJobResult(id),
        ]);
        setTaskInfo(taskRes.data);
        const resBody: any = resultRes.data;
        if (Array.isArray(resBody?.results)) {
          setResults(resBody.results);
        } else if (Array.isArray(resBody?.data)) {
          setResults(resBody.data);
        } else {
          setResults([]);
        }
      } catch (e) {
        setResults([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  // Fetch real-time metrics incrementally (with lock to prevent concurrent fetches)
  const fetchMetrics = useCallback(async () => {
    if (!id || fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const res = await commonJobApi.getRealtimeMetrics(
        id,
        lastMetricTs.current
      );
      const body: any = res.data;
      const points: RealtimeMetricPoint[] = body?.data ?? [];
      if (points.length > 0) {
        setMetricsData(prev => [...prev, ...points]);
        lastMetricTs.current = Math.max(...points.map(p => p.timestamp));
      }
    } catch {
      // Silently ignore fetch errors during polling
    } finally {
      fetchingRef.current = false;
    }
  }, [id]);

  // Poll real-time metrics when task is running and charts tab is active
  // Guard: wait for taskInfo to load before fetching to avoid duplicate
  // fetches caused by taskInfo?.status changing from undefined → actual value.
  useEffect(() => {
    if (!taskInfo) return; // Don't fetch until task info is loaded

    const isRunning =
      taskInfo.status === 'running' || taskInfo.status === 'pending';
    if (activeTab === 'charts' && id) {
      // Always do an initial fetch when switching to charts tab
      fetchMetrics();

      if (isRunning) {
        pollingRef.current = setInterval(fetchMetrics, 2000);
      }
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [activeTab, taskInfo?.status, id, fetchMetrics]);

  const totalRow = useMemo(
    () => results.find(r => r.metric_type === 'total') || results[0],
    [results]
  );
  const totalRequests = totalRow?.request_count ?? 0;
  const failureCount = totalRow?.failure_count ?? 0;

  // Smart format success rate: if close to 100% but not 100%, show more decimal places
  const calculateSuccessRate = (total: number, failures: number): number => {
    if (total <= 0) return 0;
    const rate = ((total - failures) / total) * 100;
    return rate;
  };

  const rawSuccessRate = calculateSuccessRate(totalRequests, failureCount);
  // If close to 100% but not 100%, show 5 decimal places; otherwise show 2 decimal places
  const successRate =
    rawSuccessRate >= 99.99 && rawSuccessRate < 100
      ? Number(rawSuccessRate.toFixed(5))
      : Number(rawSuccessRate.toFixed(2));
  // Format RPS consistently with table display (2 decimal places)
  // Use the same formatting as table to ensure consistency
  const rawRps =
    totalRow?.rps != null && totalRow.rps !== undefined
      ? Number(totalRow.rps)
      : 0;
  const qpm = Number((rawRps * 60).toFixed(2));
  const avgTimeSec =
    totalRow?.avg_response_time != null
      ? Number((totalRow.avg_response_time / 1000).toFixed(3))
      : 0;
  const p95TimeSec =
    totalRow?.percentile_95_response_time != null
      ? Number((totalRow.percentile_95_response_time / 1000).toFixed(3))
      : 0;

  // Whether the task is currently in a stoppable state
  const isTaskRunning =
    taskInfo?.status === 'running' || taskInfo?.status === 'pending';

  // Handle stop test with confirmation dialog
  const handleStopTest = useCallback(() => {
    if (!id) return;
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
          await commonJobApi.stopJob(id);
          message.success(t('pages.jobs.stopSuccess'));
          // Refresh task info to update status
          const taskRes = await commonJobApi.getJob(id);
          setTaskInfo(taskRes.data);
        } catch {
          message.error(t('pages.jobs.stopFailed'));
        } finally {
          setIsStopping(false);
        }
      },
    });
  }, [id, t]);

  const handleDownloadReport = async () => {
    try {
      setIsDownloading(true);

      // Determine which elements to capture based on the active tab
      const elementsToCapture: {
        ref: React.RefObject<HTMLDivElement | null>;
        title: string;
      }[] = [];
      if (activeTab === 'charts') {
        if (!chartsRef.current) return;
        elementsToCapture.push({
          ref: chartsRef,
          title: t('pages.results.tabCharts', 'Charts'),
        });
      } else {
        if (!taskRef.current || !overviewRef.current) return;
        elementsToCapture.push(
          { ref: taskRef, title: t('pages.results.taskInfo') },
          { ref: overviewRef, title: t('pages.results.resultsOverview') }
        );
        if (metricsTableRef.current) {
          elementsToCapture.push({
            ref: metricsTableRef,
            title: t('pages.results.metricsDetail'),
          });
        }
      }

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
        canvas => canvas !== null
      ) as HTMLCanvasElement[];
      if (validCanvases.length === 0) {
        throw new Error('Unable to capture any report content.');
      }

      // Calculate the total height and maximum width of the merged Canvas
      const padding = 30; // Vertical spacing between image blocks
      const horizontalPadding = 80; // Horizontal padding for left and right
      let totalHeight = 0;
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
        throw new Error('Unable to create canvas context.');
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
      link.download = `common-task-${suffix}-${taskInfo?.name || taskInfo?.id || ''}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      console.error('Download failed:', e);
    } finally {
      setIsDownloading(false);
    }
  };

  const statisticWrapperStyle: React.CSSProperties = {
    textAlign: 'left',
  };

  const statisticValueStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'flex-start',
    width: '100%',
    textAlign: 'left',
  };

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

  // Shared tooltip config: format raw timestamp to absolute date-time
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

  // ECharts: Response Time chart
  const responseTimeOption = useMemo(() => {
    if (metricsData.length === 0) return {};
    const timestamps = metricsData.map(p => p.timestamp);
    return {
      tooltip: chartTooltip,
      legend: {
        data: [
          t('pages.results.chartAvgRT', 'Avg Response Time'),
          t('pages.results.chartP95RT', 'P95'),
        ],
        bottom: 0,
      },
      grid: { top: 40, right: 30, bottom: 50, left: 60 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: {
          formatter: (val: number) => formatChartTime(val),
          rotate: 0,
        },
      },
      yAxis: {
        type: 'value' as const,
        name: 'ms',
      },
      series: [
        {
          name: t('pages.results.chartAvgRT', 'Avg Response Time'),
          type: 'line',
          data: metricsData.map(p => p.avg_response_time?.toFixed(1)),
          smooth: true,
          symbol: 'emptyCircle',
          symbolSize: 6,
          showSymbol: true,
          itemStyle: { color: '#1890ff' },
          lineStyle: { color: '#1890ff' },
        },
        {
          name: t('pages.results.chartP95RT', 'P95'),
          type: 'line',
          data: metricsData.map(p => p.p95_response_time?.toFixed(1)),
          smooth: true,
          symbol: 'emptyCircle',
          symbolSize: 6,
          showSymbol: true,
          itemStyle: { color: '#faad14' },
          lineStyle: { color: '#faad14' },
        },
      ],
    };
  }, [metricsData, formatChartTime, chartTooltip, t]);

  // ECharts: RPS & Failures chart
  const rpsOption = useMemo(() => {
    if (metricsData.length === 0) return {};
    const timestamps = metricsData.map(p => p.timestamp);
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
        },
      },
      yAxis: { type: 'value' as const, name: 'req/s' },
      series: [
        {
          name: 'RPS',
          type: 'line',
          data: metricsData.map(p => p.current_rps?.toFixed(2)),
          smooth: true,
          symbol: 'emptyCircle',
          symbolSize: 6,
          showSymbol: true,
          itemStyle: { color: '#52c41a' },
          lineStyle: { color: '#52c41a' },
          areaStyle: { opacity: 0.15, color: '#52c41a' },
        },
        {
          name: t('pages.results.chartFailPerSec', 'Failures/s'),
          type: 'line',
          data: metricsData.map(p => p.current_fail_per_sec?.toFixed(2)),
          smooth: true,
          symbol: 'emptyCircle',
          symbolSize: 6,
          showSymbol: true,
          itemStyle: { color: '#f5222d' },
        },
      ],
    };
  }, [metricsData, formatChartTime, chartTooltip, t]);

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
          symbolSize: 6,
          showSymbol: true,
          step: 'end' as const,
          areaStyle: { opacity: 0.1 },
          itemStyle: { color: '#b37feb' },
          lineStyle: { color: '#b37feb' },
        },
      ],
    };
  }, [metricsData, formatChartTime, chartTooltip, t]);

  // Metrics detail table columns definition
  const metricsColumns = useMemo(
    () => [
      {
        title: t('pages.results.metricType', 'Metric Type'),
        dataIndex: 'metric_type',
        key: 'metric_type',
        width: 140,
        ellipsis: true,
        render: (text: string) => text,
      },
      {
        title: t('pages.results.totalRequests', 'Requests'),
        dataIndex: 'request_count',
        key: 'request_count',
        width: 110,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? value.toLocaleString() : '0',
      },
      {
        title: t('pages.results.failureCount', 'Failures'),
        dataIndex: 'failure_count',
        key: 'failure_count',
        width: 100,
        align: 'right' as const,
        render: (value: number | undefined) => {
          const num = value ?? 0;
          return (
            <span style={num > 0 ? { color: 'var(--color-error)' } : undefined}>
              {num.toLocaleString()}
            </span>
          );
        },
      },
      {
        title: t('pages.results.avgResponseTime', 'Avg Time'),
        dataIndex: 'avg_response_time',
        key: 'avg_response_time',
        width: 120,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? (value / 1000).toFixed(3) : '0.000',
      },
      {
        title: t('pages.results.minResponseTime', 'Min Time'),
        dataIndex: 'min_response_time',
        key: 'min_response_time',
        width: 120,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? (value / 1000).toFixed(3) : '0.000',
      },
      {
        title: t('pages.results.maxResponseTime', 'Max Time'),
        dataIndex: 'max_response_time',
        key: 'max_response_time',
        width: 120,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? (value / 1000).toFixed(3) : '0.000',
      },
      {
        title: t('pages.results.p95ResponseTime', 'P95'),
        dataIndex: 'percentile_95_response_time',
        key: 'percentile_95_response_time',
        width: 120,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? (value / 1000).toFixed(3) : '0.000',
      },
      {
        title: t('pages.results.rps', 'RPS'),
        dataIndex: 'rps',
        key: 'rps',
        width: 100,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? Number(value).toFixed(2) : '0.00',
      },
      {
        title: t('pages.results.avgContentLength', 'Avg Content Length'),
        dataIndex: 'avg_content_length',
        key: 'avg_content_length',
        width: 140,
        align: 'right' as const,
        render: (value: number | undefined) =>
          value != null ? Number(value).toLocaleString() : '-',
      },
    ],
    [t]
  );

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
    );
  };

  // Render task info grid (reusable helper)
  const renderTaskInfoGrid = () => {
    const loadMode = taskInfo?.load_mode || 'fixed';
    return (
      <div className='info-grid'>
        <div className='info-grid-item'>
          <span className='info-label'>{t('pages.results.taskId')}</span>
          <span className='info-value'>{taskInfo.id}</span>
        </div>
        <div className='info-grid-item'>
          <span className='info-label'>{t('pages.results.taskName')}</span>
          <span className='info-value'>{taskInfo.name}</span>
        </div>
        <div className='info-grid-item'>
          <span className='info-label'>{t('pages.results.targetUrl')}</span>
          <Tooltip title={taskInfo.target_url}>
            <span className='info-value info-value-ellipsis'>
              {taskInfo.target_url}
            </span>
          </Tooltip>
        </div>
        <div className='info-grid-item'>
          <span className='info-label'>{t('pages.results.createdTime')}</span>
          <span className='info-value'>{formatDate(taskInfo.created_at)}</span>
        </div>
        <div className='info-grid-item'>
          <span className='info-label'>
            {t('pages.results.loadMode', 'Load Mode')}
          </span>
          <span className='info-value'>
            {loadMode === 'stepped'
              ? t('pages.results.loadModeStepped', 'Stepped')
              : t('pages.results.loadModeFixed', 'Fixed')}
          </span>
        </div>
        {loadMode === 'fixed' ? (
          <>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.concurrentUsers')}
              </span>
              <span className='info-value'>{taskInfo.concurrent_users}</span>
            </div>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.testDuration')}
              </span>
              <span className='info-value'>{taskInfo.duration} s</span>
            </div>
          </>
        ) : (
          <>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.stepStartUsers', 'Start Users')}
              </span>
              <span className='info-value'>{taskInfo.step_start_users}</span>
            </div>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.stepIncrement', 'Increment')}
              </span>
              <span className='info-value'>+{taskInfo.step_increment}</span>
            </div>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.stepDuration', 'Step Duration')}
              </span>
              <span className='info-value'>{taskInfo.step_duration} s</span>
            </div>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.stepMaxUsers', 'Max Users')}
              </span>
              <span className='info-value'>{taskInfo.step_max_users}</span>
            </div>
            <div className='info-grid-item'>
              <span className='info-label'>
                {t('pages.results.stepSustainDuration', 'Sustain Duration')}
              </span>
              <span className='info-value'>
                {taskInfo.step_sustain_duration} s
              </span>
            </div>
          </>
        )}
      </div>
    );
  };

  // Render statistics content (existing task info + overview + table)
  const renderStatisticsContent = () => {
    if (!results || results.length === 0) {
      return (
        <>
          {/* Task Info (no results) */}
          <div className='results-section unified-section' ref={taskRef}>
            <div className='section-header'>
              <span className='section-title'>
                {t('pages.results.taskInfo')}
              </span>
            </div>
            <div className='section-content'>
              {taskInfo ? renderTaskInfoGrid() : <Empty />}
            </div>
          </div>
          <div
            className='flex justify-center align-center'
            style={{ minHeight: '30vh', backgroundColor: '#ffffff' }}
          >
            <Alert
              description={t('pages.results.noTestResultsAvailable')}
              type='info'
              showIcon
              style={{ background: 'transparent', border: 'none' }}
            />
          </div>
        </>
      );
    }

    return (
      <>
        {/* Task Info */}
        <div className='results-section unified-section' ref={taskRef}>
          <div className='section-header'>
            <span className='section-title'>{t('pages.results.taskInfo')}</span>
          </div>
          <div className='section-content'>
            {taskInfo ? renderTaskInfoGrid() : <Empty />}
          </div>
        </div>

        {/* Results Overview */}
        <div className='results-section unified-section' ref={overviewRef}>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.results.resultsOverview')}
            </span>
          </div>
          <div className='section-content'>
            <Row gutter={16} style={{ justifyContent: 'flex-start' }}>
              <Col span={6}>
                <Statistic
                  title={t('pages.results.totalRequests')}
                  value={totalRequests}
                  style={statisticWrapperStyle}
                  valueStyle={statisticValueStyle}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('pages.results.successRate')}
                  value={successRate}
                  suffix='%'
                  precision={
                    rawSuccessRate >= 99.99 && rawSuccessRate < 100 ? 5 : 2
                  }
                  style={statisticWrapperStyle}
                  valueStyle={statisticValueStyle}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title='QPM'
                  value={qpm}
                  style={statisticWrapperStyle}
                  valueStyle={statisticValueStyle}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('pages.results.avgResponseTime')}
                  value={avgTimeSec}
                  suffix='s'
                  precision={3}
                  style={statisticWrapperStyle}
                  valueStyle={statisticValueStyle}
                />
              </Col>
              {p95TimeSec > 0 && (
                <Col span={6}>
                  <Statistic
                    title={t('pages.results.p95ResponseTime')}
                    value={p95TimeSec}
                    suffix='s'
                    precision={3}
                    style={statisticWrapperStyle}
                    valueStyle={statisticValueStyle}
                  />
                </Col>
              )}
            </Row>
          </div>
        </div>

        {/* Metrics Detail Table */}
        <div className='results-section unified-section' ref={metricsTableRef}>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.results.metricsDetail')}
            </span>
          </div>
          <div className='section-content'>
            <Table
              rowKey='metric_type'
              dataSource={results}
              pagination={false}
              scroll={{ x: 1100 }}
              className='modern-table'
              locale={{
                emptyText: (
                  <Empty description={t('common.noData', 'No Data')} />
                ),
              }}
              columns={metricsColumns}
            />
          </div>
        </div>
      </>
    );
  };

  return (
    <div className='page-container results-page'>
      <div className='page-header-wrapper'>
        <div className='flex justify-between align-center'>
          <PageHeader
            title={t('pages.results.title', 'Test Results')}
            icon={<FileTextOutlined />}
            level={3}
          />
          <Space>
            {activeTab === 'charts' && (
              <Button
                icon={<StopOutlined />}
                onClick={handleStopTest}
                loading={isStopping}
                disabled={!isTaskRunning}
                className='modern-button-stop-test'
              >
                {t('pages.results.stopTest', 'Stop Test')}
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
                  : !results || results.length === 0)
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
          </Space>
        </div>
      </div>

      {loading ? (
        <div className='loading-container'>
          <LoadingSpinner
            text={t('pages.results.loadingResultData')}
            size='large'
            className='text-center'
          />
        </div>
      ) : (
        <div className='results-content'>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'charts',
                label: (
                  <span className='tab-label'>
                    {t('pages.results.tabCharts', 'Charts')}
                  </span>
                ),
                children: renderChartsContent(),
              },
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

export default CommonResults;
