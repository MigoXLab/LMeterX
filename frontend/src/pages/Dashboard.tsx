/**
 * @file Dashboard.tsx
 * @description Attractive dashboard homepage component for LMeterX with statistics, weekly task charts, and running/recent tasks summary.
 * @author Charm
 * @copyright 2026
 */
import {
  ArrowRightOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FireOutlined,
  ReloadOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  Avatar,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  List,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { systemApi } from '../api/services';
import { HttpTask, LlmTask } from '../types/job';
import { getLdapEnabled } from '../utils/runtimeConfig';

const { Title, Paragraph } = Typography;

interface DashboardStats {
  totalTasks: number;
  pendingTasks: number;
  runningTasks: number;
  completedTasks: number;
  partialFailedTasks: number;
  exceptionTasks: number;
  failedTasks: number;
  totalCollections: number;
  totalProjects: number;
  totalModels: number;
  llmTasksCount: number;
  httpTasksCount: number;
  myTasksCount: number;
  totalUsers?: number;
}

interface WeeklyStat {
  week: string;
  count: number;
}

const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const LDAP_ENABLED = getLdapEnabled();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats>({
    totalTasks: 0,
    pendingTasks: 0,
    runningTasks: 0,
    completedTasks: 0,
    partialFailedTasks: 0,
    exceptionTasks: 0,
    failedTasks: 0,
    totalCollections: 0,
    totalProjects: 0,
    totalModels: 0,
    llmTasksCount: 0,
    httpTasksCount: 0,
    myTasksCount: 0,
    totalUsers: 0,
  });

  const [weeklyStats, setWeeklyStats] = useState<WeeklyStat[]>([]);
  const [runningLlmTasks, setRunningLlmTasks] = useState<LlmTask[]>([]);
  const [runningHttpTasks, setRunningHttpTasks] = useState<HttpTask[]>([]);

  const fetchDashboardData = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setLoading(true);
    }
    try {
      const response = await systemApi.getDashboardStats();
      if (response.data && response.data.status === 'success') {
        const payload = response.data;
        setStats(payload.stats);
        setWeeklyStats(payload.weeklyStats || []);
        setRunningLlmTasks(payload.runningLlmTasks || []);
        setRunningHttpTasks(payload.runningHttpTasks || []);
      }
    } catch (error) {
      console.error('Error fetching dashboard stats:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData(true);
    // Note: Auto-refresh/polling is completely disabled here per user's request.
    // The user prefers manual refresh or no polling on this page.
  }, [fetchDashboardData]);

  // Task distribution pie chart
  const distributionOption = useMemo(
    () => ({
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c} ({d}%)',
      },
      legend: {
        bottom: '0%',
        left: 'center',
        icon: 'circle',
        textStyle: {
          color: '#545983',
        },
      },
      color: ['#667eea', '#00b4d8', '#764ba2', '#ffb703'],
      series: [
        {
          name: 'Task Type Distribution',
          type: 'pie',
          radius: ['50%', '75%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 8,
          },
          label: {
            show: false,
            position: 'center',
          },
          emphasis: {
            scale: false,
            label: {
              show: true,
              fontSize: 14,
              fontWeight: 'bold',
              formatter: '{b}\n{c}',
            },
          },
          labelLine: {
            show: false,
          },
          data: [
            { value: stats.llmTasksCount, name: t('pages.jobs.llmTab') },
            { value: stats.httpTasksCount, name: t('pages.jobs.httpApiTab') },
          ],
        },
      ],
    }),
    [stats.llmTasksCount, stats.httpTasksCount, t]
  );

  // Task status summary bar chart
  const statusChartOption = useMemo(
    () => ({
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '10%',
        top: '10%',
        containLabel: true,
      },
      xAxis: [
        {
          type: 'category',
          data: [
            t('pages.dashboard.pending'),
            t('pages.dashboard.running'),
            t('pages.dashboard.completed'),
            t('pages.dashboard.failedRequests'),
            t('pages.dashboard.exception'),
          ],
          axisTick: {
            alignWithLabel: true,
          },
          axisLine: {
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.15)',
            },
          },
          axisLabel: {
            color: '#545983',
            interval: 0,
          },
        },
      ],
      yAxis: [
        {
          type: 'value',
          splitLine: {
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.08)',
            },
          },
          axisLabel: {
            color: '#545983',
          },
        },
      ],
      series: [
        {
          name: t('pages.dashboard.quantity'),
          type: 'bar',
          barWidth: '40%',
          emphasis: {
            focus: 'self',
            itemStyle: {
              shadowBlur: 0,
              borderWidth: 0,
            },
          },
          data: [
            {
              value: stats.pendingTasks,
              itemStyle: {
                color: '#faad14',
                borderRadius: [4, 4, 0, 0],
              },
            },
            {
              value: stats.runningTasks,
              itemStyle: {
                color: '#667eea',
                borderRadius: [4, 4, 0, 0],
              },
            },
            {
              value: stats.completedTasks,
              itemStyle: {
                color: '#52c41a',
                borderRadius: [4, 4, 0, 0],
              },
            },
            {
              value: stats.partialFailedTasks,
              itemStyle: {
                color: '#eb2f96',
                borderRadius: [4, 4, 0, 0],
              },
            },
            {
              value: stats.exceptionTasks,
              itemStyle: {
                color: '#ff4d4f',
                borderRadius: [4, 4, 0, 0],
              },
            },
          ],
        },
      ],
    }),
    [
      stats.pendingTasks,
      stats.runningTasks,
      stats.completedTasks,
      stats.partialFailedTasks,
      stats.exceptionTasks,
      t,
    ]
  );

  // Weekly new tasks bar chart option
  const weeklyNewTasksOption = useMemo(() => {
    const weeks = weeklyStats.map(item => {
      try {
        const parts = item.week.split('-');
        if (parts.length === 3) {
          return `${parts[1]}/${parts[2]}`;
        }
      } catch (e) {
        return item.week;
      }
      return item.week;
    });
    const counts = weeklyStats.map(item => item.count);

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '10%',
        top: '15%',
        containLabel: true,
      },
      xAxis: [
        {
          type: 'category',
          data: weeks,
          axisTick: {
            alignWithLabel: true,
          },
          axisLine: {
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.15)',
            },
          },
          axisLabel: {
            color: '#545983',
          },
        },
      ],
      yAxis: [
        {
          type: 'value',
          minInterval: 1,
          splitLine: {
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.08)',
            },
          },
          axisLabel: {
            color: '#545983',
          },
        },
      ],
      series: [
        {
          name: t('pages.dashboard.quantity'),
          type: 'bar',
          barWidth: '40%',
          emphasis: {
            focus: 'self',
            itemStyle: {
              shadowBlur: 0,
              borderWidth: 0,
            },
          },
          itemStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: '#667eea' },
                { offset: 1, color: '#764ba2' },
              ],
            },
            borderRadius: [4, 4, 0, 0],
          },
          data: counts,
        },
      ],
    };
  }, [weeklyStats, t]);

  return (
    <div className='page-container'>
      {/* Welcome Area */}
      <div
        style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          borderRadius: '16px',
          padding: '32px 40px',
          color: '#ffffff',
          marginBottom: '24px',
          boxShadow: '0 10px 25px -5px rgba(102, 126, 234, 0.3)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            zIndex: 2,
            position: 'relative',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Space align='center' size={12}>
            <Avatar
              size={54}
              style={{
                background: 'rgba(255,255,255,0.2)',
                backdropFilter: 'blur(10px)',
              }}
              icon={
                <DashboardOutlined style={{ color: '#fff', fontSize: 24 }} />
              }
            />
            <div>
              <Title
                level={2}
                style={{ color: '#fff', margin: 0, fontWeight: 700 }}
              >
                {t('pages.dashboard.welcomeTitle')}
              </Title>
              <Paragraph
                style={{
                  color: 'rgba(255,255,255,0.85)',
                  margin: '8px 0 0 0',
                  fontSize: '15px',
                }}
              >
                {t('pages.dashboard.welcomeSubtitle')}
              </Paragraph>
            </div>
          </Space>
          <Button
            type='text'
            icon={<ReloadOutlined style={{ color: '#fff' }} />}
            onClick={() => fetchDashboardData(true)}
            style={{
              background: 'rgba(255, 255, 255, 0.15)',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              height: '36px',
              padding: '0 16px',
            }}
          >
            {t('pages.jobs.refresh')}
          </Button>
        </div>
        {/* Background Glow Decoration */}
        <div
          style={{
            position: 'absolute',
            right: '-10%',
            top: '-20%',
            width: '300px',
            height: '300px',
            borderRadius: '50%',
            background:
              'radial-gradient(circle, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0) 70%)',
            filter: 'blur(30px)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '40%',
            bottom: '-50%',
            width: '250px',
            height: '250px',
            borderRadius: '50%',
            background:
              'radial-gradient(circle, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0) 70%)',
            filter: 'blur(25px)',
          }}
        />
      </div>

      {loading ? (
        <div
          style={{
            height: '400px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Spin size='large' tip={t('pages.dashboard.loading')} />
        </div>
      ) : (
        <>
          {/* Dashboard Statistics */}
          <Row
            className='dashboard-stat-row'
            gutter={[20, 20]}
            align='stretch'
            style={{ marginBottom: '24px' }}
          >
            {/* Total Tasks */}
            <Col
              className='dashboard-stat-col'
              style={{
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                bordered={false}
                style={{
                  borderRadius: '12px',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
                bodyStyle={{
                  padding: '20px 24px',
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <Statistic
                  title={
                    <Space size={6}>
                      <ExperimentOutlined style={{ color: '#667eea' }} />
                      <span style={{ color: '#64748b', fontWeight: 500 }}>
                        {t('pages.dashboard.totalTasks')}
                      </span>
                    </Space>
                  }
                  value={stats.totalTasks}
                  valueStyle={{
                    fontSize: '28px',
                    fontWeight: 700,
                    color: '#1e293b',
                  }}
                />
                <div
                  style={{
                    marginTop: '12px',
                    fontSize: '13px',
                    color: '#64748b',
                    lineHeight: '20px',
                  }}
                >
                  {t('pages.jobs.llmTab')}:{' '}
                  <strong style={{ color: '#475569' }}>
                    {stats.llmTasksCount}
                  </strong>{' '}
                  | {t('pages.jobs.httpApiTab')}:{' '}
                  <strong style={{ color: '#475569' }}>
                    {stats.httpTasksCount}
                  </strong>
                </div>
              </Card>
            </Col>

            {/* Total Projects */}
            <Col
              className='dashboard-stat-col'
              style={{
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                bordered={false}
                style={{
                  borderRadius: '12px',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
                bodyStyle={{
                  padding: '20px 24px',
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <Statistic
                  title={
                    <Space size={6}>
                      <DatabaseOutlined style={{ color: '#10b981' }} />
                      <span style={{ color: '#64748b', fontWeight: 500 }}>
                        {t('pages.dashboard.totalProjects')}
                      </span>
                    </Space>
                  }
                  value={stats.totalProjects}
                  valueStyle={{
                    fontSize: '28px',
                    fontWeight: 700,
                    color: '#10b981',
                  }}
                />
              </Card>
            </Col>

            {/* Total Users */}
            <Col
              className='dashboard-stat-col'
              style={{
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                bordered={false}
                style={{
                  borderRadius: '12px',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
                bodyStyle={{
                  padding: '20px 24px',
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <Statistic
                  title={
                    <Space size={6}>
                      <TeamOutlined style={{ color: '#8b5cf6' }} />
                      <span style={{ color: '#64748b', fontWeight: 500 }}>
                        {t('pages.dashboard.totalUsers')}
                      </span>
                    </Space>
                  }
                  value={LDAP_ENABLED ? (stats.totalUsers ?? 0) : '-'}
                  valueStyle={{
                    fontSize: '28px',
                    fontWeight: 700,
                    color: '#8b5cf6',
                  }}
                />
              </Card>
            </Col>

            {/* Running Tasks */}
            <Col
              className='dashboard-stat-col'
              style={{
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                bordered={false}
                style={{
                  borderRadius: '12px',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
                bodyStyle={{
                  padding: '20px 24px',
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <Statistic
                  title={
                    <Space size={6}>
                      <FireOutlined style={{ color: '#3b82f6' }} />
                      <span style={{ color: '#64748b', fontWeight: 500 }}>
                        {t('pages.dashboard.runningTasks')}
                      </span>
                    </Space>
                  }
                  value={stats.runningTasks}
                  valueStyle={{
                    fontSize: '28px',
                    fontWeight: 700,
                    color: '#3b82f6',
                  }}
                  suffix={
                    stats.runningTasks > 0 ? (
                      <Badge status='processing' style={{ marginLeft: 8 }} />
                    ) : null
                  }
                />
              </Card>
            </Col>

            {/* My Created Tasks */}
            <Col
              className='dashboard-stat-col'
              style={{
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                bordered={false}
                style={{
                  borderRadius: '12px',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
                bodyStyle={{
                  padding: '20px 24px',
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <Statistic
                  title={
                    <Space size={6}>
                      <UserOutlined style={{ color: '#ec4899' }} />
                      <span style={{ color: '#64748b', fontWeight: 500 }}>
                        {t('pages.dashboard.createdByMe')}
                      </span>
                    </Space>
                  }
                  value={stats.myTasksCount}
                  valueStyle={{
                    fontSize: '28px',
                    fontWeight: 700,
                    color: '#ec4899',
                  }}
                />
              </Card>
            </Col>
          </Row>

          {/* Dashboard Charts */}
          <Row gutter={[20, 20]} style={{ marginBottom: '24px' }}>
            <Col xs={24} md={24} lg={8}>
              <Card
                title={t('pages.dashboard.weeklyNewTasks')}
                bordered={false}
                style={{
                  height: '100%',
                  borderRadius: '12px',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
              >
                <div style={{ height: '230px' }}>
                  {weeklyStats.length > 0 ? (
                    <ReactECharts
                      option={weeklyNewTasksOption}
                      style={{ height: '100%', width: '100%' }}
                    />
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('pages.dashboard.noTasks')}
                      style={{ paddingTop: '40px' }}
                    />
                  )}
                </div>
              </Card>
            </Col>

            <Col xs={24} md={12} lg={8}>
              <Card
                title={t('pages.dashboard.taskTypeDist')}
                bordered={false}
                style={{
                  height: '100%',
                  borderRadius: '12px',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
              >
                <div style={{ height: '230px' }}>
                  {stats.totalTasks > 0 ? (
                    <ReactECharts
                      option={distributionOption}
                      style={{ height: '100%', width: '100%' }}
                    />
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('pages.dashboard.noTasks')}
                      style={{ paddingTop: '40px' }}
                    />
                  )}
                </div>
              </Card>
            </Col>

            <Col xs={24} md={12} lg={8}>
              <Card
                title={t('pages.dashboard.taskStatusSummary')}
                bordered={false}
                style={{
                  height: '100%',
                  borderRadius: '12px',
                  boxShadow:
                    '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
                }}
              >
                <div style={{ height: '230px' }}>
                  {stats.totalTasks > 0 ? (
                    <ReactECharts
                      option={statusChartOption}
                      style={{ height: '100%', width: '100%' }}
                    />
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('pages.dashboard.noStatusData')}
                      style={{ paddingTop: '40px' }}
                    />
                  )}
                </div>
              </Card>
            </Col>
          </Row>

          {/* Active Running Tasks */}
          {(runningLlmTasks.length > 0 || runningHttpTasks.length > 0) && (
            <Card
              title={
                <Space>
                  <Badge status='processing' />
                  <span style={{ fontWeight: 600 }}>
                    {t('pages.dashboard.activeRunningTasks')}
                  </span>
                </Space>
              }
              bordered={false}
              style={{
                borderRadius: '12px',
                marginBottom: '24px',
                borderLeft: '4px solid #3b82f6',
                boxShadow:
                  '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)',
              }}
            >
              <List
                itemLayout='horizontal'
                dataSource={[
                  ...runningLlmTasks.map(task => ({ ...task, type: 'LLM' })),
                  ...runningHttpTasks.map(task => ({
                    ...task,
                    type: 'HTTP',
                  })),
                ]}
                renderItem={item => (
                  <List.Item
                    actions={[
                      <Button
                        key='monitor'
                        type='link'
                        icon={<ArrowRightOutlined />}
                        onClick={() =>
                          navigate(
                            item.type === 'LLM'
                              ? `/llm-results/${item.id}?tab=charts`
                              : `/http-results/${item.id}?tab=charts`
                          )
                        }
                      >
                        {t('pages.dashboard.realtimeMonitor')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={
                        <Avatar
                          style={{
                            backgroundColor:
                              item.type === 'LLM' ? '#667eea' : '#00b4d8',
                          }}
                        >
                          {item.type}
                        </Avatar>
                      }
                      title={
                        <Space>
                          <span style={{ fontWeight: 600 }}>{item.name}</span>
                          <Tag color='processing'>
                            {t('pages.dashboard.concurrency')}:{' '}
                            {item.concurrent_users} {t('pages.dashboard.vu')}
                          </Tag>
                        </Space>
                      }
                      description={`${t('pages.dashboard.taskId')}: ${item.id} | ${t('pages.dashboard.duration')}: ${item.duration}s | ${t('pages.dashboard.createdBy')}: ${item.created_by || '-'}`}
                    />
                  </List.Item>
                )}
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
};

export default Dashboard;
