/**
 * @file CommonResults.tsx
 * @description Results page for common API jobs
 */
import { DownloadOutlined, FileTextOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Col,
  Empty,
  Row,
  Statistic,
  Table,
  Tooltip,
} from 'antd';
import html2canvas from 'html2canvas';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { commonJobApi } from '@/api/services';
import { LoadingSpinner } from '@/components/ui/LoadingState';
import { PageHeader } from '@/components/ui/PageHeader';
import { formatDate } from '@/utils/date';

const CommonResults: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [taskInfo, setTaskInfo] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDownloading, setIsDownloading] = useState(false);
  const overviewRef = useRef<HTMLDivElement | null>(null);
  const taskRef = useRef<HTMLDivElement | null>(null);

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
  // Format to 2 decimal places to match table display
  const rps = Number(rawRps.toFixed(2));
  const avgTimeSec =
    totalRow?.avg_response_time != null
      ? Number((totalRow.avg_response_time / 1000).toFixed(3))
      : 0;
  const p90TimeSec =
    totalRow?.percentile_90_response_time != null
      ? Number((totalRow.percentile_90_response_time / 1000).toFixed(3))
      : 0;

  const handleDownloadReport = async () => {
    if (!taskRef.current || !overviewRef.current) return;
    try {
      setIsDownloading(true);
      const elementsToCapture = [
        { ref: taskRef, title: t('pages.results.taskInfo') },
        { ref: overviewRef, title: t('pages.results.resultsOverview') },
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
      link.download = `common-task-results-${taskInfo?.name || taskInfo?.id || ''}.png`;
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

  return (
    <div className='page-container results-page'>
      <div className='page-header-wrapper'>
        <div className='flex justify-between align-center'>
          <PageHeader
            title={t('pages.results.title', 'Test Results')}
            icon={<FileTextOutlined />}
            level={3}
          />
          <Button
            type='primary'
            icon={<DownloadOutlined />}
            onClick={handleDownloadReport}
            loading={isDownloading}
            disabled={loading || !results || results.length === 0}
          >
            {t('pages.results.downloadReport')}
          </Button>
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
      ) : !results || results.length === 0 ? (
        <div className='flex justify-center p-24'>
          <Alert
            description={t('pages.results.noTestResultsAvailable')}
            type='info'
            showIcon
            className='btn-transparent'
          />
        </div>
      ) : (
        <div className='results-content'>
          {/* Task Info */}
          <div className='results-section unified-section' ref={taskRef}>
            <div className='section-header'>
              <span className='section-title'>
                {t('pages.results.taskInfo')}
              </span>
            </div>
            <div className='section-content'>
              {taskInfo ? (
                <div className='info-grid'>
                  <div className='info-grid-item'>
                    <span className='info-label'>
                      {t('pages.results.taskId')}
                    </span>
                    <span className='info-value'>{taskInfo.id}</span>
                  </div>
                  <div className='info-grid-item'>
                    <span className='info-label'>
                      {t('pages.results.taskName')}
                    </span>
                    <span className='info-value'>{taskInfo.name}</span>
                  </div>
                  <div className='info-grid-item'>
                    <span className='info-label'>
                      {t('pages.results.targetUrl')}
                    </span>
                    <Tooltip title={taskInfo.target_url}>
                      <span
                        className='info-value'
                        style={{
                          display: 'inline-block',
                          maxWidth: '100%',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {taskInfo.target_url}
                      </span>
                    </Tooltip>
                  </div>
                  <div className='info-grid-item'>
                    <span className='info-label'>
                      {t('pages.results.createdTime')}
                    </span>
                    <span className='info-value'>
                      {formatDate(taskInfo.created_at)}
                    </span>
                  </div>
                  <div className='info-grid-item'>
                    <span className='info-label'>
                      {t('pages.results.concurrentUsers')}
                    </span>
                    <span className='info-value'>
                      {taskInfo.concurrent_users}
                    </span>
                  </div>
                  <div className='info-grid-item'>
                    <span className='info-label'>
                      {t('pages.results.testDuration')}
                    </span>
                    <span className='info-value'>{taskInfo.duration} s</span>
                  </div>
                </div>
              ) : (
                <Empty />
              )}
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
                    title='RPS'
                    value={rps}
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
                {p90TimeSec > 0 && (
                  <Col span={6}>
                    <Statistic
                      title={t('pages.results.p90ResponseTime')}
                      value={p90TimeSec}
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

          {/* Metrics Detail */}
          <div className='results-section unified-section'>
            <div className='section-header'>
              <span className='section-title'>
                {t('pages.results.metricsDetail')}
              </span>
            </div>
            <div className='section-content'>
              <Table
                rowKey='id'
                dataSource={results}
                pagination={false}
                className='modern-table unified-table'
                locale={{
                  emptyText: (
                    <Empty description={t('common.noData', 'No Data')} />
                  ),
                }}
                columns={[
                  {
                    title: t('pages.results.metricType', 'Metric Type'),
                    dataIndex: 'metric_type',
                    key: 'metric_type',
                  },
                  {
                    title: t('pages.results.totalRequests', 'Requests'),
                    dataIndex: 'request_count',
                    key: 'request_count',
                  },
                  {
                    title: t('pages.results.failureCount', 'Failures'),
                    dataIndex: 'failure_count',
                    key: 'failure_count',
                  },
                  {
                    title: `${t('pages.results.avgResponseTime', 'Avg Time')} (s)`,
                    dataIndex: 'avg_response_time',
                    key: 'avg_response_time',
                    render: (value: number | undefined) =>
                      value != null ? (value / 1000).toFixed(3) : '-',
                  },
                  {
                    title: `${t('pages.results.p90ResponseTime', 'P90 Response Time')} (s)`,
                    dataIndex: 'percentile_90_response_time',
                    key: 'percentile_90_response_time',
                    render: (value: number | undefined) =>
                      value != null ? (value / 1000).toFixed(3) : '-',
                  },
                  {
                    title: `${t('pages.results.minResponseTime', 'Min Time')} (s)`,
                    dataIndex: 'min_response_time',
                    key: 'min_response_time',
                    render: (value: number | undefined) =>
                      value != null ? (value / 1000).toFixed(3) : '-',
                  },
                  {
                    title: `${t('pages.results.maxResponseTime', 'Max Time')} (s)`,
                    dataIndex: 'max_response_time',
                    key: 'max_response_time',
                    render: (value: number | undefined) =>
                      value != null ? (value / 1000).toFixed(3) : '-',
                  },
                  {
                    title: 'RPS',
                    dataIndex: 'rps',
                    key: 'rps',
                    render: (value: number | undefined) =>
                      value != null ? Number(value).toFixed(2) : '-',
                  },
                  {
                    title: t(
                      'pages.results.avgContentLength',
                      'Avg Content Length'
                    ),
                    dataIndex: 'avg_content_length',
                    key: 'avg_content_length',
                  },
                ]}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CommonResults;
