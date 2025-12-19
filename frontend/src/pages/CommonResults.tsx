/**
 * @file CommonResults.tsx
 * @description Results page for common API jobs
 */
import { DownloadOutlined, FileTextOutlined } from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Space,
  Table,
  Tooltip,
} from 'antd';
import html2canvas from 'html2canvas';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { commonJobApi } from '@/api/services';
import PageHeader from '@/components/ui/PageHeader';
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
  const reportRef = useRef<HTMLDivElement | null>(null);

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
  const successRate =
    totalRequests > 0
      ? Number(
          (((totalRequests - failureCount) / totalRequests) * 100).toFixed(2)
        )
      : 0;
  const rps =
    totalRow?.rps != null && totalRow.rps !== undefined
      ? Number(totalRow.rps)
      : 0;
  const avgTimeSec =
    totalRow?.avg_response_time != null
      ? Number((totalRow.avg_response_time / 1000).toFixed(3))
      : 0;
  const p90TimeSec =
    totalRow?.percentile_90_response_time != null
      ? Number((totalRow.percentile_90_response_time / 1000).toFixed(3))
      : 0;

  const handleDownloadReport = async () => {
    if (!reportRef.current) return;
    try {
      setIsDownloading(true);
      const canvas = await html2canvas(reportRef.current, {
        useCORS: true,
        scale: 2,
        backgroundColor: '#ffffff',
      } as any);
      const image = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = image;
      link.download = `common-task-results-${taskInfo?.name || taskInfo?.id || ''}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      // silent
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className='page-container'>
      <div className='flex justify-between align-center mb-24'>
        <PageHeader
          title={t('pages.results.title', 'Test Results')}
          icon={<FileTextOutlined />}
          level={3}
          className='text-center w-full'
        />
        <Button
          type='primary'
          icon={<DownloadOutlined />}
          onClick={handleDownloadReport}
          loading={isDownloading}
        >
          {t('pages.results.downloadReport')}
        </Button>
      </div>
      <Space
        direction='vertical'
        size='middle'
        className='w-full'
        ref={reportRef}
      >
        <Card
          ref={taskRef}
          title={t('pages.results.taskInfo', 'Task Information')}
          loading={loading}
          variant='borderless'
          className='form-card'
        >
          {taskInfo ? (
            <Descriptions column={2} size='small'>
              <Descriptions.Item
                label={t('pages.results.taskName', 'Task Name')}
              >
                {taskInfo.name}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.results.taskId', 'Task ID')}>
                {taskInfo.id}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.results.targetUrl')}>
                <Tooltip title={taskInfo.target_url}>
                  <span
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
              </Descriptions.Item>
              <Descriptions.Item
                label={t('pages.results.createdTime', 'Created')}
              >
                {formatDate(taskInfo.created_at)}
              </Descriptions.Item>
              <Descriptions.Item
                label={t('pages.results.concurrentUsers', 'Concurrent Users')}
              >
                {taskInfo.concurrent_users}
              </Descriptions.Item>
              <Descriptions.Item
                label={t('pages.results.testDuration', 'Duration (s)')}
              >
                {taskInfo.duration} s
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Empty />
          )}
        </Card>

        <Card
          ref={overviewRef}
          title={t('pages.results.resultsOverview')}
          loading={loading}
          headStyle={{ marginBottom: 0 }}
          bodyStyle={{ paddingTop: 12 }}
          style={{
            border: '2px solid #1890ff',
            borderRadius: '12px',
            boxShadow: '0 4px 16px rgba(24, 144, 255, 0.15)',
            backgroundColor: '#f8fbff',
          }}
        >
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <div>
                <div style={{ color: '#666' }}>
                  {t('pages.results.totalRequests')}
                </div>
                <div style={{ fontSize: 24, fontWeight: 500 }}>
                  {totalRequests}
                </div>
              </div>
            </Col>
            <Col span={8}>
              <div>
                <div style={{ color: '#666' }}>
                  {t('pages.results.successRate')}
                </div>
                <div style={{ fontSize: 24, fontWeight: 500 }}>
                  {successRate}%
                </div>
              </div>
            </Col>
            <Col span={8}>
              <div>
                <div style={{ color: '#666' }}>RPS</div>
                <div style={{ fontSize: 24, fontWeight: 500 }}>
                  {rps.toFixed(2)}
                </div>
              </div>
            </Col>
            <Col span={8}>
              <div>
                <div style={{ color: '#666' }}>
                  {t('pages.results.avgResponseTime')}
                </div>
                <div style={{ fontSize: 24, fontWeight: 500 }}>
                  {avgTimeSec.toFixed(3)}
                </div>
              </div>
            </Col>
            <Col span={8}>
              <div>
                <div style={{ color: '#666' }}>
                  {t('pages.results.p90ResponseTime', 'P90 Response Time')}
                </div>
                <div style={{ fontSize: 24, fontWeight: 500 }}>
                  {p90TimeSec.toFixed(3)}
                </div>
              </div>
            </Col>
          </Row>
        </Card>

        <Card
          title={t('pages.results.metricsDetail', 'Metrics Detail')}
          loading={loading}
        >
          <Table
            rowKey='id'
            dataSource={results}
            pagination={false}
            locale={{
              emptyText: <Empty description={t('common.noData', 'No Data')} />,
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
        </Card>
      </Space>
    </div>
  );
};

export default CommonResults;
