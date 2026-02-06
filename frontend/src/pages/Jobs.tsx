/**
 * @file Jobs.tsx
 * @description Jobs page component
 * @author Charm
 * @copyright 2025
 * */
import {
  BarChartOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  LineChartOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
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
import { useNavigate } from 'react-router-dom';

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
  const navigate = useNavigate();
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
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

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
    modelFilter,
    creatorFilter,
    allModels,
    createJob,
    stopJob,
    updateJobName,
    deleteJob,
    manualRefresh,
    performSearch,
    updateSearchInput,
    setStatusFilter,
    setModelFilter,
    setCreatorFilter,
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
    creatorFilter: commonCreatorFilter,
    createJob: createCommonJob,
    stopJob: stopCommonJob,
    updateJobName: updateCommonJobName,
    deleteJob: deleteCommonJob,
    manualRefresh: commonManualRefresh,
    performSearch: commonPerformSearch,
    updateSearchInput: updateCommonSearchInput,
    setStatusFilter: setCommonStatusFilter,
    setCreatorFilter: setCommonCreatorFilter,
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
          content: t('pages.jobs.datasetReuploadWarning'),
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
          content: t('pages.jobs.datasetReuploadWarning'),
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

  const renderLoadConfig = useCallback(
    (concurrentUsers?: number, duration?: number) => {
      const users = concurrentUsers ?? 0;
      const seconds = duration ?? 0;

      return (
        <Space direction='vertical' size={0}>
          <Text>
            {t('pages.jobs.concurrentUsers')}: {users}
          </Text>
          <Text>
            {t('pages.jobs.duration')}: {seconds}
          </Text>
        </Space>
      );
    },
    [t]
  );

  /**
   * Table column definitions
   */
  const columns: ColumnsType<Job> = useMemo(() => {
    const createdByColumn = {
      title: t('pages.jobs.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 160,
      minWidth: 120,
      ellipsis: true,
      render: (creator?: string) => creator || '-',
      filters: [
        { text: t('pages.jobs.filterMine'), value: 'mine' },
        // { text: t('pages.jobs.filterAll'), value: 'all' },
      ],
      // Use 'mine' as filteredValue when creatorFilter matches currentUsername
      // This ensures Ant Design Table maintains the filter state during pagination
      filteredValue: creatorFilter ? ['mine'] : null,
      filterMultiple: false,
    };

    const tableColumns: ColumnsType<Job> = [
      {
        title: t('pages.jobs.taskId'),
        dataIndex: 'id',
        key: 'id',
        width: 220,
        minWidth: 160,
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
        width: 600,
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
      // Commented out: API URL column - temporarily hidden
      // {
      //   title: t('pages.jobs.targetUrl'),
      //   dataIndex: 'target_host',
      //   key: 'target_host',
      //   ellipsis: true,
      //   render: (target_host: string, record: Job) => {
      //     const apiPath = record.api_path || '/chat/completions';
      //     const fullUrl = target_host + apiPath;
      //     return (
      //       <div className='table-cell-with-copy'>
      //         <Tooltip title={fullUrl} placement='topLeft'>
      //           <Text className='table-cell-text' ellipsis>
      //             {fullUrl}
      //           </Text>
      //         </Tooltip>
      //         <div className='table-cell-action'>
      //           <CopyButton text={fullUrl} />
      //         </div>
      //       </div>
      //     );
      //   },
      // },
      {
        title: t('pages.jobs.model'),
        dataIndex: 'model',
        key: 'model',
        width: 280,
        ellipsis: true,
        filters: allModels.map(model => ({
          text: model,
          value: model,
        })),
        filteredValue: modelFilter ? modelFilter.split(',') : null,
        filterSearch: true,
        filterMultiple: true,
      },
      {
        title: t('pages.jobs.loadConfig'),
        key: 'load_config',
        width: 200,
        minWidth: 160,
        ellipsis: {
          showTitle: false,
        },
        render: (_, record) => {
          const users = record.concurrent_users ?? record.concurrency ?? 0;
          const seconds = record.duration ?? 0;
          const configText = `${t('pages.jobs.concurrentUsers')}: ${users} / ${t('pages.jobs.duration')}: ${seconds}`;
          return (
            <Tooltip title={configText} placement='topLeft'>
              <Space direction='vertical' size={0} style={{ width: '100%' }}>
                <Text ellipsis>
                  {t('pages.jobs.concurrentUsers')}: {users}
                </Text>
                <Text ellipsis>
                  {t('pages.jobs.duration')}: {seconds}
                </Text>
              </Space>
            </Tooltip>
          );
        },
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
        width: 200,
        minWidth: 160,
        sorter: (a, b) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (time: string) => formatDate(time),
      },
      {
        title: t('pages.jobs.actions'),
        key: 'action',
        width: 200,
        minWidth: 120,
        render: (_, record) => {
          const statusLower = record.status?.toLowerCase();
          const moreMenuItems: any[] = [];

          if (
            canManage(record.created_by) &&
            ['running', 'queued'].includes(statusLower)
          ) {
            moreMenuItems.push({
              key: 'stop',
              icon: <StopOutlined />,
              label: t('pages.jobs.stop'),
              danger: true,
              onClick: (info: any) => {
                info.domEvent.stopPropagation();
                showStopConfirm(record.id, record.name);
              },
            });
          }

          if (
            canManage(record.created_by) &&
            statusLower !== 'running' &&
            statusLower !== 'stopping'
          ) {
            moreMenuItems.push({
              key: 'delete',
              icon: <DeleteOutlined />,
              label: t('pages.jobs.delete'),
              danger: true,
              onClick: (info: any) => {
                info.domEvent.stopPropagation();
                handleDeleteTask(record, 'llm');
              },
            });
          }

          return (
            <Space size={4}>
              <Tooltip title={t('pages.jobs.results')}>
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<LineChartOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    window.open(`/results/${record.id}`, '_blank');
                  }}
                />
              </Tooltip>
              <Tooltip title={t('pages.jobs.logs')}>
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<FileTextOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    window.open(`/logs/task/${record.id}`, '_blank');
                  }}
                />
              </Tooltip>
              {canManage(record.created_by) && (
                <Tooltip title={t('pages.jobs.copyTemplate')}>
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
                    icon={<CopyOutlined />}
                    onClick={e => {
                      e.stopPropagation();
                      handleCopyJob(record);
                    }}
                  />
                </Tooltip>
              )}
              {moreMenuItems.length > 0 && (
                <Dropdown
                  menu={{ items: moreMenuItems }}
                  trigger={['click']}
                  placement='bottomRight'
                >
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
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
    allModels,
    canManage,
    creatorFilter,
    currentUsername,
    handleCopyJob,
    handleDeleteTask,
    modelFilter,
    openRenameModal,
    renderLoadConfig,
    showStopConfirm,
    statusFilter,
    t,
  ]);

  const commonColumns: ColumnsType<CommonJob> = useMemo(() => {
    const createdByColumn = {
      title: t('pages.jobs.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 160,
      minWidth: 120,
      ellipsis: true,
      render: (creator?: string) => creator || '-',
      filters: [
        { text: t('pages.jobs.filterMine'), value: 'mine' },
        // { text: t('pages.jobs.filterAll'), value: 'all' },
      ],
      // Use 'mine' as filteredValue when commonCreatorFilter matches currentUsername
      // This ensures Ant Design Table maintains the filter state during pagination
      filteredValue: commonCreatorFilter ? ['mine'] : null,
      filterMultiple: false,
    };

    const tableColumns: ColumnsType<CommonJob> = [
      {
        title: t('pages.jobs.taskId'),
        dataIndex: 'id',
        key: 'id',
        width: 220,
        minWidth: 160,
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
        width: 600,
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
      // Commented out: API URL column - temporarily hidden
      // {
      //   title: t('pages.jobs.targetUrl'),
      //   dataIndex: 'target_url',
      //   key: 'target_url',
      //   ellipsis: true,
      //   render: (target_url: string) => (
      //     <div className='table-cell-with-copy'>
      //       <Tooltip title={target_url} placement='topLeft'>
      //         <Text className='table-cell-text' ellipsis>
      //           {target_url}
      //         </Text>
      //       </Tooltip>
      //       <div className='table-cell-action'>
      //         <CopyButton text={target_url} />
      //       </div>
      //     </div>
      //   ),
      // },
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
        title: t('pages.jobs.loadConfig'),
        key: 'load_config',
        width: 200,
        minWidth: 160,
        ellipsis: {
          showTitle: false,
        },
        render: (_, record) => {
          const users = record.concurrent_users ?? 0;
          const seconds = record.duration ?? 0;
          const configText = `${t('pages.jobs.concurrentUsers')}: ${users} / ${t('pages.jobs.duration')}: ${seconds}`;
          return (
            <Tooltip title={configText} placement='topLeft'>
              <Space direction='vertical' size={0} style={{ width: '100%' }}>
                <Text ellipsis>
                  {t('pages.jobs.concurrentUsers')}: {users}
                </Text>
                <Text ellipsis>
                  {t('pages.jobs.duration')}: {seconds}
                </Text>
              </Space>
            </Tooltip>
          );
        },
      },
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
        width: 200,
        minWidth: 160,
        sorter: (a, b) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (time: string) => formatDate(time),
      },
      {
        title: t('pages.jobs.actions'),
        key: 'action',
        width: 200,
        minWidth: 100,
        render: (_, record) => {
          const statusLower = record.status?.toLowerCase();
          const moreMenuItems: any[] = [];

          if (
            canManage(record.created_by) &&
            ['running', 'queued'].includes(statusLower)
          ) {
            moreMenuItems.push({
              key: 'stop',
              icon: <StopOutlined />,
              label: t('pages.jobs.stop'),
              danger: true,
              onClick: (info: any) => {
                info.domEvent.stopPropagation();
                showStopConfirm(record.id, record.name);
              },
            });
          }

          if (canManage(record.created_by)) {
            moreMenuItems.push({
              key: 'delete',
              icon: <DeleteOutlined />,
              label: t('pages.jobs.delete'),
              danger: true,
              disabled: statusLower === 'running' || statusLower === 'stopping',
              onClick: (info: any) => {
                info.domEvent.stopPropagation();
                handleDeleteTask(record, 'common');
              },
            });
          }

          return (
            <Space size={4}>
              <Tooltip title={t('pages.jobs.results')}>
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<LineChartOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    window.open(`/common-results/${record.id}`, '_blank');
                  }}
                />
              </Tooltip>
              <Tooltip title={t('pages.jobs.logs')}>
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<FileTextOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    window.open(`/logs/task/${record.id}`, '_blank');
                  }}
                />
              </Tooltip>
              {canManage(record.created_by) && (
                <Tooltip title={t('pages.jobs.copyTemplate')}>
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
                    icon={<CopyOutlined />}
                    onClick={e => {
                      e.stopPropagation();
                      handleCopyCommonJob(record);
                    }}
                  />
                </Tooltip>
              )}
              {moreMenuItems.length > 0 && (
                <Dropdown
                  menu={{ items: moreMenuItems }}
                  trigger={['click']}
                  placement='bottomRight'
                >
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
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
    commonCreatorFilter,
    commonStatusFilter,
    currentUsername,
    handleCopyCommonJob,
    handleDeleteTask,
    openRenameModal,
    renderLoadConfig,
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

      // Handle model filter change (only for LLM mode)
      const newModelFilter =
        filters?.model && filters.model.length > 0
          ? filters.model.map((value: unknown) => String(value)).join(',')
          : '';

      // Handle creator filter change - convert 'mine' to current username
      let newCreatorFilter = '';
      if (filters?.created_by && filters.created_by.length > 0) {
        const filterValue = filters.created_by[0];
        newCreatorFilter = filterValue === 'mine' ? currentUsername : '';
      }

      const useCommon = activeMode === 'common';
      const prevStatus = useCommon ? commonStatusFilter : statusFilter;
      const prevModel = modelFilter;
      const prevCreator = useCommon ? commonCreatorFilter : creatorFilter;

      const isFilterChange =
        newStatusFilter !== prevStatus ||
        newModelFilter !== prevModel ||
        newCreatorFilter !== prevCreator;

      const nextPage = isFilterChange ? 1 : newPagination.current || 1;
      const nextPageSize =
        newPagination.pageSize ||
        (useCommon ? commonPagination.pageSize : pagination.pageSize);

      if (useCommon) {
        // Update filters first if changed
        if (newStatusFilter !== commonStatusFilter) {
          setCommonStatusFilter(newStatusFilter);
        }
        if (newCreatorFilter !== commonCreatorFilter) {
          setCommonCreatorFilter(newCreatorFilter);
        }
        // Trigger fetch with new pagination - manualRefresh will update pagination state
        commonManualRefresh({
          page: nextPage,
          pageSize: nextPageSize,
          status: newStatusFilter,
          search: commonSearchInput,
          creator: newCreatorFilter,
        });
      } else {
        // Update filters first if changed
        if (newStatusFilter !== statusFilter) {
          setStatusFilter(newStatusFilter);
        }
        if (newModelFilter !== modelFilter) {
          setModelFilter(newModelFilter);
        }
        if (newCreatorFilter !== creatorFilter) {
          setCreatorFilter(newCreatorFilter);
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
      commonCreatorFilter,
      commonPagination.pageSize,
      commonPagination.total,
      commonManualRefresh,
      commonSearchInput,
      commonStatusFilter,
      creatorFilter,
      currentUsername,
      modelFilter,
      pagination.pageSize,
      pagination.total,
      setCommonCreatorFilter,
      setCommonStatusFilter,
      setCreatorFilter,
      setModelFilter,
      setPagination,
      setStatusFilter,
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

  const handleResetFilters = useCallback(() => {
    if (activeMode === 'common') {
      updateCommonSearchInput('');
      commonManualRefresh({
        page: 1,
        pageSize: commonPagination.pageSize,
        status: '',
        search: '',
        creator: '',
      });
      return;
    }

    updateSearchInput('');
    setStatusFilter('');
    setModelFilter('');
    setCreatorFilter('');
    performSearch('');
    setPagination(prev => ({
      ...prev,
      current: 1,
    }));
  }, [
    activeMode,
    commonManualRefresh,
    commonPagination.pageSize,
    performSearch,
    setCreatorFilter,
    setModelFilter,
    setPagination,
    setStatusFilter,
    updateCommonSearchInput,
    updateSearchInput,
  ]);

  /**
   * Handle row selection change
   */
  const handleSelectionChange = useCallback(
    (newSelectedRowKeys: React.Key[]) => {
      if (newSelectedRowKeys.length > 5) {
        messageApi.warning(t('pages.jobs.selectMaxForCompare'));
        return;
      }
      setSelectedRowKeys(newSelectedRowKeys);
    },
    [messageApi, t]
  );

  /**
   * Navigate to result comparison page with selected tasks
   */
  const handleGoToCompare = useCallback(() => {
    if (selectedRowKeys.length < 2 || selectedRowKeys.length > 5) {
      messageApi.warning(t('pages.jobs.selectMinForCompare'));
      return;
    }
    const mode = activeMode === 'llm' ? 'model' : 'common';
    const taskIds = selectedRowKeys.join(',');
    navigate(`/result-comparison?tasks=${taskIds}&mode=${mode}`);
  }, [activeMode, messageApi, navigate, selectedRowKeys, t]);

  const COMPARABLE_STATUSES = useMemo(
    () => ['completed', 'failed_requests'],
    []
  );

  const rowSelection = useMemo(
    () => ({
      selectedRowKeys,
      onChange: handleSelectionChange,
      preserveSelectedRowKeys: true,
      columnTitle: ' ',
      getCheckboxProps: (record: Job | CommonJob) => ({
        disabled: !COMPARABLE_STATUSES.includes(
          record.status?.toLowerCase() ?? ''
        ),
      }),
    }),
    [selectedRowKeys, handleSelectionChange, COMPARABLE_STATUSES]
  );

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
            setSelectedRowKeys([]);
          }}
          items={[
            {
              key: 'llm',
              label: (
                <span className='tab-label'>
                  {t('pages.jobs.llmTab') || 'LLM Load Test'}
                </span>
              ),
            },
            {
              key: 'common',
              label: (
                <span className='tab-label'>
                  {t('pages.jobs.commonApiTab') || 'Business API Load Test'}
                </span>
              ),
            },
          ]}
          className='unified-tabs'
        />

        {/* Toolbar */}
        <div className='jobs-toolbar'>
          <div className='jobs-toolbar-left'>
            <Button
              type='primary'
              className='modern-button-primary'
              icon={<PlusOutlined />}
              onClick={() => setIsModalVisible(true)}
              disabled={currentLoading}
            >
              {t('pages.jobs.createNew')}
            </Button>
            {selectedRowKeys.length > 0 && (
              <>
                {selectedRowKeys.length >= 2 && selectedRowKeys.length <= 5 && (
                  <Button
                    type='primary'
                    icon={<BarChartOutlined />}
                    onClick={handleGoToCompare}
                  >
                    {`${t('pages.jobs.goToCompare')} (${t(
                      'pages.jobs.selectedCount',
                      {
                        count: selectedRowKeys.length,
                      }
                    )})`}
                  </Button>
                )}
                <Button onClick={() => setSelectedRowKeys([])}>
                  {t('pages.jobs.clearSelection')}
                </Button>
              </>
            )}
          </div>
          <div className='jobs-toolbar-right'>
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
              onClick={handleResetFilters}
              disabled={currentLoading}
              className='modern-button'
            >
              {t('common.reset')}
            </Button>
            <Tooltip
              title={`${t('pages.jobs.lastRefresh')}: ${currentLastRefresh ? formatDate(currentLastRefresh) : '-'}`}
            >
              <Button
                type='text'
                icon={<ReloadOutlined spin={currentRefreshing} />}
                onClick={currentManualRefresh}
                disabled={currentLoading || currentRefreshing}
                className='modern-button'
              />
            </Tooltip>
          </div>
        </div>

        <Table<any>
          columns={currentColumns as any}
          rowKey='id'
          dataSource={currentJobs as any}
          loading={currentLoading}
          pagination={currentPagination}
          rowSelection={rowSelection}
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
