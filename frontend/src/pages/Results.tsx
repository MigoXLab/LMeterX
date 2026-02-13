/**
 * @file Results.tsx
 * @description Results page component
 * @author Charm
 * @copyright 2025
 * */
import {
  DownloadOutlined,
  DownOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  RobotOutlined,
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
  Tooltip,
} from 'antd';
import html2canvas from 'html2canvas';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { analysisApi, jobApi, resultApi } from '../api/services';
import { CopyButton } from '../components/ui/CopyButton';
import { IconTooltip } from '../components/ui/IconTooltip';
import { LoadingSpinner } from '../components/ui/LoadingState';
import MarkdownRenderer from '../components/ui/MarkdownRenderer';
import { PageHeader } from '../components/ui/PageHeader';
import { useLanguage } from '../contexts/LanguageContext';
import { formatDate } from '../utils/date';

const SUMMARY_METRIC_TYPES = new Set([
  'token_metrics',
  'Total_time',
  'Time_to_first_reasoning_token',
  'Time_to_first_output_token',
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
  const configCardRef = useRef<HTMLDivElement | null>(null);
  const overviewCardRef = useRef<HTMLDivElement | null>(null);
  const detailsCardRef = useRef<HTMLDivElement | null>(null);
  const metricsDetailCardRef = useRef<HTMLDivElement | null>(null);

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
        title: createTitleWithTooltip(t('pages.results.ttft'), 'TTFT (s)'),
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
    if (
      !configCardRef.current ||
      !overviewCardRef.current ||
      !metricsDetailCardRef.current
    ) {
      message.error(t('pages.results.reportComponentsNotLoaded'));
      return;
    }

    setIsDownloading(true);
    message.loading({
      content: 'Generating report...',
      key: 'downloadReport',
      duration: 0,
    });

    try {
      const elementsToCapture = [
        { ref: configCardRef, title: t('pages.results.taskInfo') },
        { ref: overviewCardRef, title: t('pages.results.resultsOverview') },
        { ref: metricsDetailCardRef, title: t('pages.results.metricsDetail') },
      ];

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
        canvas => canvas !== null
      ) as HTMLCanvasElement[];
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
      link.download = `task-results-${taskInfo?.name || taskInfo?.id || ''}.png`;
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
        </div>
      </div>
    </div>
  );

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
            <Button
              icon={<RobotOutlined />}
              onClick={() => setAnalysisModalVisible(true)}
              loading={isAnalyzing}
              disabled={loading || !!error || !results || results.length === 0}
              className='modern-button-ai-summary'
            >
              {t('pages.results.aiSummary')}
            </Button>
            <Button
              type='primary'
              icon={<DownloadOutlined />}
              onClick={handleDownloadReport}
              loading={isDownloading}
              disabled={loading || !!error || !results || results.length === 0}
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
      ) : !results || results.length === 0 ? (
        <div className='results-content'>
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
      ) : (
        <div className='results-content'>
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
                    successMessage={t('pages.results.analysisCopied')}
                    tooltip={t('pages.results.copyAnalysis')}
                  />
                  <Button
                    type='text'
                    size='small'
                    icon={
                      isAnalysisExpanded ? <UpOutlined /> : <DownOutlined />
                    }
                    onClick={() => setIsAnalysisExpanded(!isAnalysisExpanded)}
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

          {/* Task Info - Converted to table format */}
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
            <div className='section-content'>{renderOverviewMetrics()}</div>
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
                    item.metric_type !== 'total_tokens_per_second' &&
                    item.metric_type !== 'completion_tokens_per_second' &&
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
                    successMessage={t('pages.results.resultsCopied')}
                    tooltip={t('pages.results.copyResults')}
                  />
                </div>
              </div>
            </div>
          </div>
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
