/**
 * @file Jobs.tsx
 * @description Jobs page component
 * @author Charm
 * @copyright 2025
 * */
import {
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  App,
  Badge,
  Button,
  Dropdown,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tabs,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { commonJobApi } from '../api/services';
import CreateCommonJobForm from '../components/CreateCommonJobForm';
import CreateJobForm from '../components/CreateJobForm';
import CopyButton from '../components/ui/CopyButton';
import PageHeader from '../components/ui/PageHeader';
import StatusTag from '../components/ui/StatusTag';
import { useCommonJobs } from '../hooks/useCommonJobs';
import { useJobs } from '../hooks/useJobs';
import { CommonJob, Job } from '../types/job';
import { TASK_STATUS_MAP, UI_CONFIG } from '../utils/constants';
import { deepClone, safeJsonParse, safeJsonStringify } from '../utils/data';
import { formatDate, getTimestamp } from '../utils/date';

const { Search } = Input;
const { Text } = Typography;

const MODE_STORAGE_KEY = 'jobsActiveMode';

const JobsPage: React.FC = () => {
  const { t } = useTranslation();
  // State managed by the component
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [taskToCopy, setTaskToCopy] = useState<Partial<Job> | null>(null);
  const [commonTaskToCopy, setCommonTaskToCopy] =
    useState<Partial<CommonJob> | null>(null);
  const [activeMode, setActiveMode] = useState<'llm' | 'common'>(() => {
    const stored = localStorage.getItem(MODE_STORAGE_KEY);
    return stored === 'common' ? 'common' : 'llm';
  });

  // Get message instance from App context
  const { message: messageApi, modal } = App.useApp();

  // Using the custom hook to manage job-related logic
  const {
    filteredJobs,
    pagination,
    setPagination,
    loading,
    refreshing,
    error,
    lastRefreshTime,
    searchInput,
    statusFilter,
    createJob,
    stopJob,
    manualRefresh,
    performSearch,
    updateSearchInput,
    setStatusFilter,
  } = useJobs(messageApi);
  const {
    filteredJobs: commonFilteredJobs,
    pagination: commonPagination,
    setPagination: setCommonPagination,
    loading: commonLoading,
    refreshing: commonRefreshing,
    error: commonError,
    lastRefreshTime: commonLastRefresh,
    searchInput: commonSearchInput,
    statusFilter: commonStatusFilter,
    createJob: createCommonJob,
    stopJob: stopCommonJob,
    manualRefresh: commonManualRefresh,
    performSearch: commonPerformSearch,
    updateSearchInput: updateCommonSearchInput,
    setStatusFilter: setCommonStatusFilter,
  } = useCommonJobs(messageApi);

  /**
   * Handle copying a job template
   */
  const handleCopyJob = useCallback(
    (job: Job) => {
      const copiedName = job.name
        ? `${job.name} (Copy)`
        : `Copy Task ${job.id.substring(0, 8)}`;

      const jobToCopyData: Partial<Job> = {
        ...job,
        name: copiedName,
        id: undefined,
        status: undefined,
        created_at: undefined,
        updated_at: undefined,
      };

      // Handle headers using safe JSON parsing
      if (jobToCopyData.headers) {
        const headerObject =
          typeof jobToCopyData.headers === 'string'
            ? safeJsonParse(jobToCopyData.headers, [])
            : jobToCopyData.headers;
        jobToCopyData.headers = deepClone(headerObject) || [];
      }

      // Handle request_payload - preserve for custom APIs
      if (jobToCopyData.request_payload) {
        jobToCopyData.request_payload =
          typeof jobToCopyData.request_payload === 'string'
            ? jobToCopyData.request_payload
            : safeJsonStringify(jobToCopyData.request_payload);
      }

      // Handle field_mapping - preserve configuration with proper structure
      if (jobToCopyData.field_mapping) {
        const fieldMappingObject =
          typeof jobToCopyData.field_mapping === 'string'
            ? safeJsonParse(jobToCopyData.field_mapping, {})
            : jobToCopyData.field_mapping;

        // Ensure all required field_mapping properties exist
        const completeFieldMapping = {
          prompt: '',
          stream_prefix: '',
          data_format: 'json',
          content: '',
          reasoning_content: '',
          end_prefix: '',
          stop_flag: '',
          end_field: '',
          ...fieldMappingObject, // Override with actual values
        };

        jobToCopyData.field_mapping = deepClone(completeFieldMapping) || {};
      } else {
        // Initialize empty field_mapping structure if not present
        jobToCopyData.field_mapping = {
          prompt: '',
          stream_prefix: '',
          data_format: 'json',
          content: '',
          reasoning_content: '',
          end_prefix: '',
          stop_flag: '',
          end_field: '',
        };
      }

      setTaskToCopy(jobToCopyData);
      setIsModalVisible(true);

      // Show toast notification about re-entering sensitive information
      messageApi.warning({
        content: t('pages.jobs.copyWarning'),
        duration: 5,
      });
    },
    [messageApi, t]
  );

  /**
   * Handle copying a common API job template
   */
  const handleCopyCommonJob = useCallback(
    async (job: CommonJob) => {
      try {
        // Fetch full task details to get request_body and other fields
        const fullJobResponse = await commonJobApi.getJob(job.id);
        const fullJob = (fullJobResponse.data as CommonJob) || job;

        const copiedName = fullJob.name
          ? `${fullJob.name} (Copy)`
          : `Copy Task ${fullJob.id.substring(0, 8)}`;

        // Don't copy headers to avoid exposing sensitive information
        // Use default header value instead
        const defaultHeaders = 'Content-Type: application/json';

        const jobToCopyData: Partial<CommonJob> = {
          ...fullJob,
          name: copiedName,
          id: undefined,
          status: undefined,
          created_at: undefined,
          updated_at: undefined,
          headers: defaultHeaders as any,
          // Ensure request_body is included
          request_body: fullJob.request_body || '',
        };

        setCommonTaskToCopy(jobToCopyData);
        setIsModalVisible(true);

        messageApi.warning({
          content: t('pages.jobs.copyWarning'),
          duration: 5,
        });
      } catch (error) {
        console.error('Failed to fetch full job details:', error);
        messageApi.error({
          content: t('pages.jobs.copyError', 'Failed to load task details'),
          duration: 3,
        });
      }
    },
    [messageApi, t]
  );

  /**
   * Show confirmation dialog for stopping a job
   */
  const showStopConfirm = useCallback(
    (jobId: string, jobName?: string) => {
      modal.confirm({
        title: t('pages.jobs.stopConfirmTitle'),
        icon: <ExclamationCircleOutlined />,
        content: (
          <span>
            {t('pages.jobs.stopConfirmContent')}{' '}
            <Text code>{jobName || jobId}</Text>
          </span>
        ),
        okText: t('pages.jobs.confirmStop'),
        okType: 'danger',
        cancelText: t('common.cancel'),
        onOk: () =>
          activeMode === 'llm' ? stopJob(jobId) : stopCommonJob(jobId),
      });
    },
    [activeMode, modal, stopCommonJob, stopJob, t]
  );

  /**
   * Table column definitions
   */
  const columns: ColumnsType<Job> = useMemo(
    () => [
      {
        title: t('pages.jobs.taskId'),
        dataIndex: 'id',
        key: 'id',
        ellipsis: {
          showTitle: false,
        },
        render: (id: string) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={id} placement='topLeft'>
              <Text
                className='table-cell-text'
                ellipsis
                style={{ maxWidth: '100%' }}
              >
                {id}
              </Text>
            </Tooltip>
            <div className='table-cell-action'>
              <CopyButton text={id} />
            </div>
          </div>
        ),
      },
      {
        title: t('pages.jobs.taskName'),
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
      },
      {
        title: t('pages.jobs.targetUrl'),
        dataIndex: 'target_host',
        key: 'target_host',
        ellipsis: true,
        render: (target_host: string, record: Job) => {
          const apiPath = record.api_path || '/chat/completions';
          const fullUrl = target_host + apiPath;
          return (
            <div className='table-cell-with-copy'>
              <Tooltip title={fullUrl} placement='topLeft'>
                <Text className='table-cell-text' ellipsis>
                  {fullUrl}
                </Text>
              </Tooltip>
              <div className='table-cell-action'>
                <CopyButton text={fullUrl} />
              </div>
            </div>
          );
        },
      },
      {
        title: t('pages.jobs.model'),
        dataIndex: 'model',
        key: 'model',
        ellipsis: true,
        width: 120,
      },
      {
        title: t('pages.jobs.concurrentUsers'),
        dataIndex: 'concurrent_users',
        key: 'concurrent_users',
        align: 'center',
        width: 120,
      },
      {
        title: t('pages.jobs.duration'),
        dataIndex: 'duration',
        key: 'duration',
        align: 'center',
        render: (duration: number) => `${duration || 0}s`,
        width: 120,
      },
      {
        title: t('pages.jobs.status'),
        dataIndex: 'status',
        key: 'status',
        width: 120,
        filters: Object.entries(TASK_STATUS_MAP).map(([key]) => ({
          text: t(`status.${key}`),
          value: key,
        })),
        filteredValue: statusFilter ? statusFilter.split(',') : null,
        // Remove onFilter since we're using server-side filtering
        render: (status: string) => <StatusTag status={status} />,
      },
      {
        title: t('pages.jobs.createdTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 200,
        sorter: (a, b) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (time: string) => formatDate(time),
      },
      {
        title: t('pages.jobs.actions'),
        key: 'action',
        width: 200,
        fixed: 'right',
        render: (_, record) => {
          const menuItems = [
            {
              key: 'copy',
              label: (
                <Button
                  type='text'
                  size='small'
                  className='table-action-button'
                  onClick={e => {
                    e.stopPropagation();
                    handleCopyJob(record);
                  }}
                >
                  {t('pages.jobs.copyTemplate')}
                </Button>
              ),
            },
          ];

          if (['running', 'queued'].includes(record.status?.toLowerCase())) {
            menuItems.push({
              key: 'stop',
              label: (
                <Button
                  type='text'
                  danger
                  size='small'
                  className='table-action-button'
                  onClick={e => {
                    e.stopPropagation();
                    showStopConfirm(record.id, record.name);
                  }}
                >
                  {t('pages.jobs.stop')}
                </Button>
              ),
            });
          }

          return (
            <Space size='small' wrap>
              <Button
                size='small'
                type='primary'
                onClick={e => {
                  e.stopPropagation();
                  window.open(`/results/${record.id}`, '_blank');
                }}
              >
                {t('pages.jobs.results')}
              </Button>
              <Button
                size='small'
                type='primary'
                onClick={e => {
                  e.stopPropagation();
                  window.open(`/logs/task/${record.id}`, '_blank');
                }}
              >
                {t('pages.jobs.logs')}
              </Button>
              {menuItems.length > 0 && (
                <Dropdown menu={{ items: menuItems }} trigger={['click']}>
                  <Button
                    type='text'
                    icon={<MoreOutlined />}
                    onClick={e => e.stopPropagation()}
                  />
                </Dropdown>
              )}
            </Space>
          );
        },
      },
    ],
    [handleCopyJob, showStopConfirm, t]
  );

  const commonColumns: ColumnsType<CommonJob> = useMemo(
    () => [
      {
        title: t('pages.jobs.taskId'),
        dataIndex: 'id',
        key: 'id',
        ellipsis: {
          showTitle: false,
        },
        render: (id: string) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={id} placement='topLeft'>
              <Text
                className='table-cell-text'
                ellipsis
                style={{ maxWidth: '100%' }}
              >
                {id}
              </Text>
            </Tooltip>
            <div className='table-cell-action'>
              <CopyButton text={id} />
            </div>
          </div>
        ),
      },
      {
        title: t('pages.jobs.taskName'),
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
      },
      {
        title: t('pages.jobs.targetUrl'),
        dataIndex: 'target_url',
        key: 'target_url',
        width: 350,
        ellipsis: true,
        render: (target_url: string) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={target_url} placement='topLeft'>
              <Text className='table-cell-text' ellipsis>
                {target_url}
              </Text>
            </Tooltip>
            <div className='table-cell-action'>
              <CopyButton text={target_url} />
            </div>
          </div>
        ),
      },
      {
        title: t('pages.jobs.method'),
        dataIndex: 'method',
        key: 'method',
        align: 'center',
      },
      {
        title: t('pages.jobs.concurrentUsers'),
        dataIndex: 'concurrent_users',
        key: 'concurrent_users',
        align: 'center',
      },
      {
        title: t('pages.jobs.duration'),
        dataIndex: 'duration',
        key: 'duration',
        align: 'center',
        render: (duration: number) => `${duration || 0}s`,
      },
      {
        title: t('pages.jobs.status'),
        dataIndex: 'status',
        key: 'status',
        filters: Object.entries(TASK_STATUS_MAP).map(([key]) => ({
          text: t(`status.${key}`),
          value: key,
        })),
        filteredValue: commonStatusFilter
          ? commonStatusFilter.split(',')
          : null,
        render: (status: string) => <StatusTag status={status} />,
      },
      {
        title: t('pages.jobs.createdTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        sorter: (a, b) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (time: string) => formatDate(time),
      },
      {
        title: t('pages.jobs.actions'),
        key: 'action',
        width: 200,
        fixed: 'right',
        render: (_, record) => {
          const menuItems = [];
          menuItems.push({
            key: 'copy',
            label: (
              <Button
                type='text'
                size='small'
                className='table-action-button'
                onClick={e => {
                  e.stopPropagation();
                  handleCopyCommonJob(record);
                }}
              >
                {t('pages.jobs.copyTemplate')}
              </Button>
            ),
          });
          if (['running', 'queued'].includes(record.status?.toLowerCase())) {
            menuItems.push({
              key: 'stop',
              label: (
                <Button
                  type='text'
                  danger
                  size='small'
                  className='table-action-button'
                  onClick={e => {
                    e.stopPropagation();
                    showStopConfirm(record.id, record.name);
                  }}
                >
                  {t('pages.jobs.stop')}
                </Button>
              ),
            });
          }
          return (
            <Space size='small' wrap>
              <Button
                size='small'
                type='primary'
                onClick={e => {
                  e.stopPropagation();
                  window.open(`/common-results/${record.id}`, '_blank');
                }}
              >
                {t('pages.jobs.results')}
              </Button>
              <Button
                size='small'
                type='primary'
                onClick={e => {
                  e.stopPropagation();
                  window.open(`/logs/task/${record.id}`, '_blank');
                }}
              >
                {t('pages.jobs.logs')}
              </Button>
              {menuItems.length > 0 && (
                <Dropdown menu={{ items: menuItems }} trigger={['click']}>
                  <Button
                    type='text'
                    icon={<MoreOutlined />}
                    onClick={e => e.stopPropagation()}
                  />
                </Dropdown>
              )}
            </Space>
          );
        },
      },
    ],
    [commonStatusFilter, showStopConfirm, t]
  );

  /**
   * Handle job creation
   */
  const handleCreateJob = useCallback(
    async (values: any) => {
      const success =
        activeMode === 'llm'
          ? await createJob(values)
          : await createCommonJob(values);
      if (success) {
        setIsModalVisible(false);
        setTaskToCopy(null);
      }
    },
    [activeMode, createCommonJob, createJob]
  );

  /**
   * Handle table changes (pagination and filters)
   */
  const handleTableChange = useCallback(
    (newPagination: any, filters: any) => {
      // Handle status filter change from table
      const newStatusFilter = filters?.status ? filters.status.join(',') : '';
      const useCommon = activeMode === 'common';
      const prevStatus = useCommon ? commonStatusFilter : statusFilter;
      const isFilterChange = newStatusFilter !== prevStatus;

      const nextPage = isFilterChange ? 1 : newPagination.current || 1;
      const nextPageSize = newPagination.pageSize || commonPagination.pageSize;

      if (useCommon) {
        setCommonPagination({
          current: nextPage,
          pageSize: nextPageSize,
          // Keep previous total if antd does not provide it on pagination change
          total: newPagination.total ?? commonPagination.total,
        });
        setCommonStatusFilter(newStatusFilter);
        // Trigger fetch immediately with new pagination to avoid stalled UI
        commonManualRefresh({
          page: nextPage,
          pageSize: nextPageSize,
          status: newStatusFilter,
          search: commonSearchInput,
        });
      } else {
        setPagination({
          current: isFilterChange ? 1 : newPagination.current,
          pageSize: newPagination.pageSize,
          total: newPagination.total ?? pagination.total,
        });
        setStatusFilter(newStatusFilter);
      }
    },
    [
      activeMode,
      commonPagination.total,
      commonStatusFilter,
      commonManualRefresh,
      commonPagination.pageSize,
      commonSearchInput,
      setCommonPagination,
      setCommonStatusFilter,
      setPagination,
      setStatusFilter,
      pagination.total,
      statusFilter,
    ]
  );

  /**
   * Render last refresh time indicator
   */
  const renderLastRefreshTime = useCallback(
    (time?: Date | null) => {
      if (!time) return null;

      return (
        <Tooltip title={`${t('pages.jobs.lastRefresh')}: ${formatDate(time)}`}>
          <span className='status-refresh'>
            <ClockCircleOutlined className='mr-4' />
            {t('pages.jobs.refreshedAgo')}
          </span>
        </Tooltip>
      );
    },
    [t]
  );

  /**
   * Handle modal cancel
   */
  const handleModalCancel = useCallback(() => {
    setIsModalVisible(false);
    setTaskToCopy(null);
  }, []);

  const isCommonMode = activeMode === 'common';
  const currentJobs = isCommonMode ? commonFilteredJobs : filteredJobs;
  const currentPagination = isCommonMode ? commonPagination : pagination;
  const setCurrentPagination = isCommonMode
    ? setCommonPagination
    : setPagination;
  const currentLoading = isCommonMode ? commonLoading : loading;
  const currentRefreshing = isCommonMode ? commonRefreshing : refreshing;
  const currentError = isCommonMode ? commonError : error;
  const currentLastRefresh = isCommonMode ? commonLastRefresh : lastRefreshTime;
  const currentSearchInput = isCommonMode ? commonSearchInput : searchInput;
  const currentPerformSearch = isCommonMode
    ? commonPerformSearch
    : performSearch;
  const currentUpdateSearchInput = isCommonMode
    ? updateCommonSearchInput
    : updateSearchInput;
  const currentManualRefresh = isCommonMode
    ? () => commonManualRefresh()
    : () => manualRefresh();
  const currentColumns = isCommonMode ? commonColumns : columns;

  return (
    <div className='page-container'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('sidebar.testTasks')}
          icon={<ExperimentOutlined />}
          description={t('pages.jobs.description')}
        />
      </div>

      <div className='jobs-content-wrapper'>
        <Tabs
          activeKey={activeMode}
          onChange={key => {
            setActiveMode(key as 'llm' | 'common');
            localStorage.setItem(MODE_STORAGE_KEY, key as 'llm' | 'common');
          }}
          items={[
            {
              key: 'llm',
              label: (
                <span style={{ fontSize: 18, fontWeight: 600 }}>
                  {t('pages.jobs.llmTab') || 'LLM Load Test'}
                </span>
              ),
            },
            {
              key: 'common',
              label: (
                <span style={{ fontSize: 18, fontWeight: 600 }}>
                  {t('pages.jobs.commonApiTab') || 'Common API Load Test'}
                </span>
              ),
            },
          ]}
          className='modern-tabs'
        />

        {/* Create Task Button - Prominent Position */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 24,
            marginBottom: 16,
          }}
        >
          <Button
            type='primary'
            className='btn-success'
            icon={<PlusOutlined />}
            onClick={() => setIsModalVisible(true)}
            disabled={currentLoading}
          >
            {t('pages.jobs.createNew')}
          </Button>
          <Space wrap>
            {currentRefreshing && <Badge status='processing' />}
            {renderLastRefreshTime(currentLastRefresh)}
            <Search
              placeholder={
                isCommonMode
                  ? t('pages.jobs.searchPlaceholderCommon')
                  : t('pages.jobs.searchPlaceholder')
              }
              value={currentSearchInput}
              onSearch={currentPerformSearch}
              onChange={e => currentUpdateSearchInput(e.target.value)}
              onClear={() => currentPerformSearch('')}
              className='w-300 modern-search'
              allowClear
              enterButton
            />
            <Button
              icon={<ReloadOutlined spin={currentRefreshing} />}
              onClick={currentManualRefresh}
              disabled={currentLoading || currentRefreshing}
              className='modern-button'
            >
              {t('pages.jobs.refresh')}
            </Button>
          </Space>
        </div>

        <Table<any>
          columns={currentColumns as any}
          rowKey='id'
          dataSource={currentJobs as any}
          loading={currentLoading}
          pagination={currentPagination}
          onChange={(pag, filters) => {
            setCurrentPagination({
              current: pag.current || 1,
              pageSize: pag.pageSize || currentPagination.pageSize,
              total: pag.total || currentPagination.total,
            });
            handleTableChange(pag, filters);
          }}
          scroll={{ x: UI_CONFIG.TABLE_SCROLL_X }}
          className='modern-table unified-table'
          rowClassName={record =>
            record.status?.toLowerCase() === 'running'
              ? 'table-highlight-row'
              : ''
          }
          locale={{
            emptyText: currentError ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={<Text type='danger'>{currentError}</Text>}
              />
            ) : (
              <Empty description={t('common.noData')} />
            ),
          }}
        />
      </div>

      <Modal
        title={taskToCopy ? t('pages.jobs.edit') : t('pages.jobs.createNew')}
        open={isModalVisible}
        onCancel={handleModalCancel}
        footer={null}
        width={800}
        destroyOnHidden
        maskClosable={false}
      >
        {activeMode === 'llm' ? (
          <CreateJobForm
            onSubmit={handleCreateJob}
            onCancel={handleModalCancel}
            loading={currentLoading}
            initialData={taskToCopy}
          />
        ) : (
          <CreateCommonJobForm
            onSubmit={handleCreateJob}
            onCancel={handleModalCancel}
            loading={currentLoading}
            initialData={commonTaskToCopy}
          />
        )}
      </Modal>
    </div>
  );
};

export default JobsPage;
