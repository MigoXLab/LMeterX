/**
 * @file Jobs.tsx
 * @description Jobs page component
 * @author Charm
 * @copyright 2025
 * */
import {
  ClockCircleOutlined,
  EditOutlined,
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

import { commonJobApi, jobApi } from '../api/services';
import CreateCommonJobForm from '../components/CreateCommonJobForm';
import CreateJobForm from '../components/CreateJobForm';
import CopyButton from '../components/ui/CopyButton';
import PageHeader from '../components/ui/PageHeader';
import StatusTag from '../components/ui/StatusTag';
import { useCommonJobs } from '../hooks/useCommonJobs';
import { useJobs } from '../hooks/useJobs';
import { CommonJob, Job } from '../types/job';
import { getStoredUser } from '../utils/auth';
import { TASK_STATUS_MAP, UI_CONFIG } from '../utils/constants';
import { deepClone, safeJsonParse, safeJsonStringify } from '../utils/data';
import { formatDate, getTimestamp } from '../utils/date';
import { getLdapEnabled } from '../utils/runtimeConfig';

const { Search } = Input;
const { Text } = Typography;

const MODE_STORAGE_KEY = 'jobsActiveMode';
const LDAP_ENABLED = getLdapEnabled();

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
  const [renameTarget, setRenameTarget] = useState<{
    id: string;
    name?: string;
    type: 'llm' | 'common';
    created_by?: string;
  } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renaming, setRenaming] = useState(false);

  // Get message instance from App context
  const { message: messageApi, modal } = App.useApp();

  const currentUsername = useMemo(() => getStoredUser()?.username || '', []);
  const canManage = useCallback(
    (creator?: string) => {
      // Allow managing anonymous tasks when LDAP is disabled
      if (creator === '-') return true;
      // forbidden to manage task without created_by
      if (!creator || !currentUsername) return false;
      return creator === currentUsername;
    },
    [currentUsername]
  );

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
    updateJobName,
    deleteJob,
    manualRefresh,
    performSearch,
    updateSearchInput,
    setStatusFilter,
  } = useJobs(messageApi);
  const {
    filteredJobs: commonFilteredJobs,
    pagination: commonPagination,
    loading: commonLoading,
    refreshing: commonRefreshing,
    error: commonError,
    lastRefreshTime: commonLastRefresh,
    searchInput: commonSearchInput,
    statusFilter: commonStatusFilter,
    createJob: createCommonJob,
    stopJob: stopCommonJob,
    updateJobName: updateCommonJobName,
    deleteJob: deleteCommonJob,
    manualRefresh: commonManualRefresh,
    performSearch: commonPerformSearch,
    updateSearchInput: updateCommonSearchInput,
    setStatusFilter: setCommonStatusFilter,
  } = useCommonJobs(messageApi);

  /**
   * Handle copying a job template
   */
  const handleCopyJob = useCallback(
    async (job: Job) => {
      if (!canManage(job.created_by)) {
        messageApi.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const copiedName = job.name
          ? `${job.name} (Copy)`
          : `Copy Task ${job.id.substring(0, 8)}`;

        // Always fetch full task detail to preserve headers, datasets and mapping
        const fullJobResp = await jobApi.getJob(job.id);
        const fullJob = (fullJobResp as any)?.data || job;

        const jobToCopyData: Partial<Job> = {
          ...fullJob,
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
        messageApi.destroy();
        messageApi.warning({
          content: '请注意数据集需要重新上传',
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
    [canManage, messageApi, t]
  );

  /**
   * Handle copying a common API job template
   */
  const handleCopyCommonJob = useCallback(
    async (job: CommonJob) => {
      try {
        if (!canManage(job.created_by)) {
          messageApi.warning(t('pages.jobs.ownerOnly'));
          return;
        }
        // Fetch full task details to get request_body and other fields
        const fullJobResponse = await commonJobApi.getJob(job.id);
        const fullJob = (fullJobResponse.data as CommonJob) || job;

        const copiedName = fullJob.name
          ? `${fullJob.name} (Copy)`
          : `Copy Task ${fullJob.id.substring(0, 8)}`;

        const jobToCopyData: Partial<CommonJob> = {
          ...fullJob,
          name: copiedName,
          id: undefined,
          status: undefined,
          created_at: undefined,
          updated_at: undefined,
          // Ensure request_body is included as string
          request_body:
            typeof fullJob.request_body === 'string'
              ? fullJob.request_body
              : (fullJob.request_body ?? ''),
        };

        setCommonTaskToCopy(jobToCopyData);
        setIsModalVisible(true);

        messageApi.destroy();
        messageApi.warning({
          content: '请注意数据集需要重新上传',
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
    [canManage, messageApi, t]
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

  const openRenameModal = useCallback(
    (record: Job | CommonJob, type: 'llm' | 'common') => {
      if (!canManage(record.created_by)) {
        messageApi.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      setRenameTarget({
        id: record.id,
        name: record.name,
        type,
        created_by: record.created_by,
      });
      setRenameValue(record.name || '');
    },
    [canManage, messageApi, t]
  );

  const handleRenameSubmit = useCallback(async () => {
    if (!renameTarget) return;
    setRenaming(true);
    const success =
      renameTarget.type === 'llm'
        ? await updateJobName(renameTarget.id, renameValue)
        : await updateCommonJobName(renameTarget.id, renameValue);
    setRenaming(false);
    if (success) {
      setRenameTarget(null);
      setRenameValue('');
    }
  }, [renameTarget, renameValue, updateCommonJobName, updateJobName]);

  const closeRenameModal = useCallback(() => {
    setRenameTarget(null);
    setRenameValue('');
  }, []);

  const handleDeleteTask = useCallback(
    (record: Job | CommonJob, type: 'llm' | 'common') => {
      if (!canManage(record.created_by)) {
        messageApi.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      const statusLower = record.status?.toLowerCase();
      if (statusLower === 'running' || statusLower === 'stopping') {
        messageApi.warning(
          t(
            'pages.jobs.deleteRunningBlocked',
            'Please stop the task and wait for it to finish before deleting.'
          )
        );
        return;
      }
      modal.confirm({
        title: t('pages.jobs.deleteConfirmTitle'),
        icon: <ExclamationCircleOutlined />,
        content: (
          <span>
            <Text code>{record.name || record.id}</Text>{' '}
            {t('pages.jobs.deleteConfirmContent')}
          </span>
        ),
        okText: t('pages.jobs.delete'),
        okType: 'danger',
        cancelText: t('common.cancel'),
        onOk: () =>
          type === 'llm' ? deleteJob(record.id) : deleteCommonJob(record.id),
      });
    },
    [canManage, deleteCommonJob, deleteJob, messageApi, modal, t]
  );

  /**
   * Table column definitions
   */
  const columns: ColumnsType<Job> = useMemo(() => {
    const createdByColumn = {
      title: t('pages.jobs.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
      minWidth: 100,
      ellipsis: true,
      render: (creator?: string) => creator || '-',
    };

    const tableColumns: ColumnsType<Job> = [
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
        render: (name: string, record: Job) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={name}>
              <Text className='table-cell-text' ellipsis>
                {name}
              </Text>
            </Tooltip>
            {canManage(record.created_by) && (
              <div className='table-cell-action'>
                <Button
                  type='text'
                  size='small'
                  className='table-action-button'
                  icon={<EditOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    openRenameModal(record, 'llm');
                  }}
                />
              </div>
            )}
          </div>
        ),
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
      },
      // {
      //   title: t('pages.jobs.concurrentUsers'),
      //   dataIndex: 'concurrent_users',
      //   key: 'concurrent_users',
      //   align: 'center',
      // },
      // {
      //   title: t('pages.jobs.duration'),
      //   dataIndex: 'duration',
      //   key: 'duration',
      //   align: 'center',
      //   render: (duration: number) => `${duration || 0}s`,
      // },
      {
        title: t('pages.jobs.status'),
        dataIndex: 'status',
        key: 'status',
        width: 120,
        minWidth: 100,
        filters: Object.entries(TASK_STATUS_MAP).map(([key]) => ({
          text: t(`status.${key}`),
          value: key,
        })),
        filteredValue: statusFilter ? statusFilter.split(',') : null,
        // Remove onFilter since we're using server-side filtering
        render: (status: string) => <StatusTag status={status} />,
      },
      ...(LDAP_ENABLED ? [createdByColumn] : []),
      {
        title: t('pages.jobs.createdTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        minWidth: 100,
        sorter: (a, b) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (time: string) => formatDate(time),
      },
      {
        title: t('pages.jobs.actions'),
        key: 'action',
        width: 240,
        minWidth: 100,
        render: (_, record) => {
          const menuItems = [];
          const statusLower = record.status?.toLowerCase();

          if (
            canManage(record.created_by) &&
            ['running', 'queued'].includes(record.status?.toLowerCase())
          ) {
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

          if (
            canManage(record.created_by) &&
            statusLower !== 'running' &&
            statusLower !== 'stopping'
          ) {
            menuItems.push({
              key: 'delete',
              label: (
                <Button
                  type='text'
                  danger
                  size='small'
                  className='table-action-button'
                  onClick={e => {
                    e.stopPropagation();
                    handleDeleteTask(record, 'llm');
                  }}
                >
                  {t('pages.jobs.delete')}
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
              {canManage(record.created_by) && (
                <Button
                  size='small'
                  type='primary'
                  onClick={e => {
                    e.stopPropagation();
                    handleCopyJob(record);
                  }}
                >
                  {t('pages.jobs.copyTemplate')}
                </Button>
              )}
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
    ];

    return tableColumns;
  }, [
    canManage,
    handleCopyJob,
    handleDeleteTask,
    openRenameModal,
    showStopConfirm,
    t,
  ]);

  const commonColumns: ColumnsType<CommonJob> = useMemo(() => {
    const createdByColumn = {
      title: t('pages.jobs.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
      minWidth: 100,
      ellipsis: true,
      render: (creator?: string) => creator || '-',
    };

    const tableColumns: ColumnsType<CommonJob> = [
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
        render: (name: string, record: CommonJob) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={name}>
              <Text className='table-cell-text' ellipsis>
                {name}
              </Text>
            </Tooltip>
            {canManage(record.created_by) && (
              <div className='table-cell-action'>
                <Button
                  type='text'
                  size='small'
                  className='table-action-button'
                  icon={<EditOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    openRenameModal(record, 'common');
                  }}
                />
              </div>
            )}
          </div>
        ),
      },
      {
        title: t('pages.jobs.targetUrl'),
        dataIndex: 'target_url',
        key: 'target_url',
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
      // {
      //   title: t('pages.jobs.method'),
      //   dataIndex: 'method',
      //   key: 'method',
      //   align: 'center',
      // },
      // {
      //   title: t('pages.jobs.concurrentUsers'),
      //   dataIndex: 'concurrent_users',
      //   key: 'concurrent_users',
      //   align: 'center',
      // },
      // {
      //   title: t('pages.jobs.duration'),
      //   dataIndex: 'duration',
      //   key: 'duration',
      //   align: 'center',
      //   render: (duration: number) => `${duration || 0}s`,
      // },
      {
        title: t('pages.jobs.status'),
        dataIndex: 'status',
        key: 'status',
        width: 120,
        minWidth: 100,
        filters: Object.entries(TASK_STATUS_MAP).map(([key]) => ({
          text: t(`status.${key}`),
          value: key,
        })),
        filteredValue: commonStatusFilter
          ? commonStatusFilter.split(',')
          : null,
        render: (status: string) => <StatusTag status={status} />,
      },
      ...(LDAP_ENABLED ? [createdByColumn] : []),
      {
        title: t('pages.jobs.createdTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        minWidth: 100,
        sorter: (a, b) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (time: string) => formatDate(time),
      },
      {
        title: t('pages.jobs.actions'),
        key: 'action',
        width: 240,
        minWidth: 100,
        render: (_, record) => {
          const menuItems = [];
          const statusLower = record.status?.toLowerCase();
          if (
            canManage(record.created_by) &&
            ['running', 'queued'].includes(record.status?.toLowerCase())
          ) {
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
          if (canManage(record.created_by)) {
            menuItems.push({
              key: 'delete',
              label: (
                <Button
                  type='text'
                  danger
                  size='small'
                  className='table-action-button'
                  onClick={e => {
                    e.stopPropagation();
                    handleDeleteTask(record, 'common');
                  }}
                  disabled={
                    statusLower === 'running' || statusLower === 'stopping'
                  }
                >
                  {t('pages.jobs.delete')}
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
              {canManage(record.created_by) && (
                <Button
                  size='small'
                  type='primary'
                  onClick={e => {
                    e.stopPropagation();
                    handleCopyCommonJob(record);
                  }}
                >
                  {t('pages.jobs.copyTemplate')}
                </Button>
              )}
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
    ];

    return tableColumns;
  }, [
    canManage,
    commonStatusFilter,
    handleCopyCommonJob,
    handleDeleteTask,
    openRenameModal,
    showStopConfirm,
    t,
  ]);

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
      const nextPageSize =
        newPagination.pageSize ||
        (useCommon ? commonPagination.pageSize : pagination.pageSize);

      if (useCommon) {
        // Update status filter first if changed
        if (newStatusFilter !== commonStatusFilter) {
          setCommonStatusFilter(newStatusFilter);
        }
        // Trigger fetch with new pagination - manualRefresh will update pagination state
        commonManualRefresh({
          page: nextPage,
          pageSize: nextPageSize,
          status: newStatusFilter,
          search: commonSearchInput,
        });
      } else {
        if (newStatusFilter !== statusFilter) {
          setStatusFilter(newStatusFilter);
        }
        setPagination({
          current: isFilterChange ? 1 : newPagination.current,
          pageSize: newPagination.pageSize,
          total: newPagination.total ?? pagination.total,
        });
      }
    },
    [
      activeMode,
      commonPagination.total,
      commonStatusFilter,
      commonManualRefresh,
      commonPagination.pageSize,
      commonSearchInput,
      setCommonStatusFilter,
      setPagination,
      setStatusFilter,
      pagination.total,
      pagination.pageSize,
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
            // Only handle table change, let handleTableChange manage pagination updates
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
        title={t('pages.jobs.renameTitle')}
        open={!!renameTarget}
        onCancel={closeRenameModal}
        onOk={handleRenameSubmit}
        confirmLoading={renaming}
        destroyOnHidden
        maskClosable={false}
      >
        <Input
          value={renameValue}
          onChange={e => setRenameValue(e.target.value)}
          maxLength={100}
          placeholder={t('pages.jobs.renamePlaceholder')}
        />
      </Modal>

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
            suppressCopyWarning={!!taskToCopy}
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
