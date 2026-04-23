/**
 * @file Tasks.tsx
 * @description Tasks page component
 * @author Charm
 * @copyright 2025
 * */
import {
  BarChartOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  GlobalOutlined,
  LineChartOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  App,
  Badge,
  Button,
  Divider,
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

import { httpTaskApi, llmTaskApi } from '../api/services';
import AddToCollectionModal from '../components/AddToCollectionModal';
import CreateHttpTaskForm from '../components/CreateHttpTaskForm';
import CreateLlmTaskForm from '../components/CreateLlmTaskForm';
import WebOneClickModal from '../components/WebOneClickModal';
import CopyButton from '../components/ui/CopyButton';
import PageHeader from '../components/ui/PageHeader';
import StatusTag from '../components/ui/StatusTag';
import { useHttpTasks } from '../hooks/useHttpTasks';
import { useLlmTasks } from '../hooks/useLlmTasks';
import { HttpTask, LlmTask } from '../types/job';
import { getStoredUser } from '../utils/auth';
import { TASK_STATUS_MAP, UI_CONFIG } from '../utils/constants';
import { deepClone, safeJsonParse, safeJsonStringify } from '../utils/data';
import { formatDate, getTimestamp } from '../utils/date';
import { getLdapEnabled } from '../utils/runtimeConfig';

const { Search } = Input;
const { Text } = Typography;

const MODE_STORAGE_KEY = 'jobsActiveMode';
const LDAP_ENABLED = getLdapEnabled();

const resolveTaskDetail = <T extends Record<string, any>>(
  response: any,
  fallback: T
): T => {
  const rawData = response?.data;
  const detail =
    rawData &&
    typeof rawData === 'object' &&
    !Array.isArray(rawData) &&
    'data' in rawData
      ? (rawData as any).data
      : rawData;

  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) {
    return fallback;
  }

  // Prefer detail values while keeping list-row values as fallback.
  return { ...fallback, ...detail } as T;
};

const withDatasetFields = <T extends Record<string, any>>(
  target: T,
  source: Record<string, any>
): T => {
  const next = { ...target } as Record<string, any>;

  if (source.test_data !== undefined && source.test_data !== null) {
    next.test_data = source.test_data;
  }
  if (source.chat_type !== undefined && source.chat_type !== null) {
    next.chat_type = source.chat_type;
  }

  // Copy mode relies on this form-only field to avoid resetting dataset type.
  if (next.test_data !== undefined && next.test_data !== null) {
    const testDataStr = String(next.test_data).trim();
    const isDefault = testDataStr === 'default';
    const isEmpty = testDataStr === '';
    const looksLikePath =
      /\/upload_files\//i.test(testDataStr) ||
      /^[\\/]/.test(testDataStr) ||
      /\.(jsonl?|txt)$/i.test(testDataStr);
    const looksLikeInlineJson =
      testDataStr.startsWith('{') || testDataStr.includes('\n');

    if (isDefault) {
      next.test_data_input_type = 'default';
    } else if (isEmpty) {
      next.test_data_input_type = 'none';
    } else if (looksLikePath) {
      next.test_data_input_type = 'upload';
      // Provide a display name for the uploader panel
      try {
        const parts = testDataStr.split(/[\\/]/);
        const filename = parts[parts.length - 1] || '';
        if (filename) {
          next.test_data_file = filename;
        }
      } catch {
        // ignore filename derivation errors
      }
    } else if (looksLikeInlineJson) {
      next.test_data_input_type = 'input';
    } else {
      // Fallback: treat as inline custom JSONL content
      next.test_data_input_type = 'input';
    }
  }

  return next as T;
};

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // State managed by the component
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [taskToCopy, setTaskToCopy] = useState<Partial<LlmTask> | null>(null);
  const [httpTaskToCopy, setHttpTaskToCopy] =
    useState<Partial<HttpTask> | null>(null);
  const [activeMode, setActiveMode] = useState<'llm' | 'http'>(() => {
    const stored = localStorage.getItem(MODE_STORAGE_KEY);
    return stored === 'http' || stored === 'common' ? 'http' : 'llm';
  });
  const [renameTarget, setRenameTarget] = useState<{
    id: string;
    name?: string;
    type: 'llm' | 'http';
    created_by?: string;
  } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renaming, setRenaming] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [webOneClickOpen, setWebOneClickOpen] = useState(false);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [singleAddTaskId, setSingleAddTaskId] = useState<string | null>(null);

  // Get message instance from App context
  const { message: messageApi, modal } = App.useApp();

  const storedUser = useMemo(() => getStoredUser(), []);
  const currentUsername = useMemo(
    () => storedUser?.username || '',
    [storedUser]
  );
  const isAdmin = useMemo(() => storedUser?.is_admin === true, [storedUser]);

  const canManage = useCallback(
    (creator?: string) => {
      // Admin users can manage all tasks
      if (isAdmin) return true;
      // Allow managing anonymous tasks when LDAP is disabled
      if (creator === '-') return true;
      // forbidden to manage task without created_by
      if (!creator || !currentUsername) return false;
      return creator === currentUsername;
    },
    [currentUsername, isAdmin]
  );

  // Allow all users to stop and rename tasks created by "agent"
  const canStopOrRename = useCallback(
    (creator?: string) => {
      if (creator === 'agent') return true;
      return canManage(creator);
    },
    [canManage]
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
  } = useLlmTasks(messageApi);
  const {
    filteredJobs: httpFilteredJobs,
    pagination: httpPagination,
    loading: httpLoading,
    refreshing: httpRefreshing,
    error: httpError,
    lastRefreshTime: httpLastRefresh,
    searchInput: httpSearchInput,
    statusFilter: httpStatusFilter,
    creatorFilter: httpCreatorFilter,
    createJob: createHttpTask,
    stopJob: stopHttpTask,
    updateJobName: updateHttpTaskName,
    deleteJob: deleteHttpTask,
    manualRefresh: httpManualRefresh,
    performSearch: httpPerformSearch,
    updateSearchInput: updateHttpSearchInput,
    setStatusFilter: setHttpStatusFilter,
    setCreatorFilter: setHttpCreatorFilter,
  } = useHttpTasks(messageApi);

  /**
   * Handle copying a job template
   */
  const handleCopyJob = useCallback(
    async (job: LlmTask) => {
      if (!canManage(job.created_by)) {
        messageApi.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const copiedName = job.name
          ? `${job.name} (Copy)`
          : `Copy Task ${job.id.substring(0, 8)}`;

        // Always fetch full task detail to preserve headers, datasets and mapping
        const fullJobResp = await llmTaskApi.getJob(job.id);
        const fullJob = resolveTaskDetail(fullJobResp, job);

        let jobToCopyData: Partial<LlmTask> = {
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

        jobToCopyData = withDatasetFields(jobToCopyData as any, fullJob);

        setTaskToCopy(jobToCopyData);
        setIsModalVisible(true);
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
   * Handle copying an HTTP API task template
   */
  const handleCopyHttpTask = useCallback(
    async (job: HttpTask) => {
      try {
        if (!canManage(job.created_by)) {
          messageApi.warning(t('pages.jobs.ownerOnly'));
          return;
        }
        // Fetch full task details to get request_body and other fields
        const fullJobResponse = await httpTaskApi.getJob(job.id);
        const fullJob = (fullJobResponse.data as HttpTask) || job;

        const copiedName = fullJob.name
          ? `${fullJob.name} (Copy)`
          : `Copy Task ${fullJob.id.substring(0, 8)}`;

        const jobToCopyData: Partial<HttpTask> = {
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

        setHttpTaskToCopy(jobToCopyData);
        setIsModalVisible(true);
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
   * Generate a rerun task name with incrementing suffix (-1, -2, ...)
   */
  const getRerunName = useCallback((name?: string): string => {
    const baseName = name || 'Task';
    const match = baseName.match(/^(.*)-(\d+)$/);
    if (match) {
      return `${match[1]}-${parseInt(match[2]) + 1}`;
    }
    return `${baseName}-1`;
  }, []);

  /**
   * Handle rerun an LLM job (create a new task based on existing config)
   */
  const handleRerunJob = useCallback(
    async (job: LlmTask) => {
      if (!canManage(job.created_by)) {
        messageApi.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const fullJobResp = await llmTaskApi.getJob(job.id);
        const fullJob = resolveTaskDetail(fullJobResp, job);

        let rerunData: any = {
          ...fullJob,
          name: getRerunName(fullJob.name),
          id: undefined,
          status: undefined,
          created_at: undefined,
          updated_at: undefined,
          result_id: undefined,
          temp_task_id: `temp-${Date.now()}`,
        };

        // Handle headers
        if (rerunData.headers) {
          const headerObject =
            typeof rerunData.headers === 'string'
              ? safeJsonParse(rerunData.headers, [])
              : rerunData.headers;
          rerunData.headers = deepClone(headerObject) || [];
        }

        // Handle request_payload
        if (rerunData.request_payload) {
          rerunData.request_payload =
            typeof rerunData.request_payload === 'string'
              ? rerunData.request_payload
              : safeJsonStringify(rerunData.request_payload);
        }

        // Handle field_mapping
        if (rerunData.field_mapping) {
          const fieldMappingObject =
            typeof rerunData.field_mapping === 'string'
              ? safeJsonParse(rerunData.field_mapping, {})
              : rerunData.field_mapping;
          rerunData.field_mapping = deepClone(fieldMappingObject) || {};
        }

        // Preserve warmup configuration
        if (
          rerunData.warmup_enabled !== undefined &&
          rerunData.warmup_enabled !== null
        ) {
          rerunData.warmup_enabled = Boolean(rerunData.warmup_enabled);
        }

        rerunData = withDatasetFields(rerunData, fullJob);

        const resp = await llmTaskApi.createJob(rerunData);
        const success = !!(resp as any)?.data?.task_id;
        if (success) {
          manualRefresh();
          messageApi.success(t('pages.jobs.rerunSuccess'));
        } else {
          messageApi.error(t('pages.jobs.rerunFailed'));
        }
      } catch (error) {
        console.error('Failed to rerun job:', error);
        messageApi.error(t('pages.jobs.rerunFailed'));
      }
    },
    [canManage, getRerunName, manualRefresh, messageApi, t]
  );

  /**
   * Handle rerun an HTTP API task
   */
  const handleRerunHttpTask = useCallback(
    async (job: HttpTask) => {
      if (!canManage(job.created_by)) {
        messageApi.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const fullJobResponse = await httpTaskApi.getJob(job.id);
        const fullJob = (fullJobResponse.data as HttpTask) || job;

        const rerunData: any = {
          ...fullJob,
          name: getRerunName(fullJob.name),
          id: undefined,
          status: undefined,
          created_at: undefined,
          updated_at: undefined,
          temp_task_id: `temp-${Date.now()}`,
          request_body:
            typeof fullJob.request_body === 'string'
              ? fullJob.request_body
              : (fullJob.request_body ?? ''),
        };

        const resp = await httpTaskApi.createJob(rerunData);
        const success = resp.status === 200 || resp.status === 201;
        if (success) {
          httpManualRefresh();
          messageApi.success(t('pages.jobs.rerunSuccess'));
        } else {
          messageApi.error(t('pages.jobs.rerunFailed'));
        }
      } catch (error) {
        console.error('Failed to rerun HTTP task:', error);
        messageApi.error(t('pages.jobs.rerunFailed'));
      }
    },
    [canManage, getRerunName, httpManualRefresh, messageApi, t]
  );

  /**
   * Show confirmation dialog for rerunning a job
   */
  const showRerunConfirm = useCallback(
    (record: LlmTask | HttpTask, type: 'llm' | 'http') => {
      modal.confirm({
        title: t('pages.jobs.rerunConfirmTitle'),
        icon: <PlayCircleOutlined style={{ color: '#52c41a' }} />,
        content: (
          <div>
            <p>
              {t('pages.jobs.rerunConfirmContent')}{' '}
              <Text code>{record.name || record.id}</Text>
            </p>
          </div>
        ),
        okText: t('pages.jobs.confirmRerun'),
        okButtonProps: {
          style: {
            backgroundColor: '#52c41a',
            borderColor: '#52c41a',
          },
        },
        cancelText: t('common.cancel'),
        onOk: () =>
          type === 'llm'
            ? handleRerunJob(record as LlmTask)
            : handleRerunHttpTask(record as HttpTask),
      });
    },
    [handleRerunHttpTask, handleRerunJob, modal, t]
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
        okButtonProps: {
          style: {
            backgroundColor: '#fa8c16',
            borderColor: '#fa8c16',
          },
        },
        cancelText: t('common.cancel'),
        onOk: () =>
          activeMode === 'llm' ? stopJob(jobId) : stopHttpTask(jobId),
      });
    },
    [activeMode, modal, stopHttpTask, stopJob, t]
  );

  const openRenameModal = useCallback(
    (record: LlmTask | HttpTask, type: 'llm' | 'http') => {
      if (!canStopOrRename(record.created_by)) {
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
    [canStopOrRename, messageApi, t]
  );

  const handleRenameSubmit = useCallback(async () => {
    if (!renameTarget) return;
    setRenaming(true);
    const success =
      renameTarget.type === 'llm'
        ? await updateJobName(renameTarget.id, renameValue)
        : await updateHttpTaskName(renameTarget.id, renameValue);
    setRenaming(false);
    if (success) {
      setRenameTarget(null);
      setRenameValue('');
    }
  }, [renameTarget, renameValue, updateHttpTaskName, updateJobName]);

  const closeRenameModal = useCallback(() => {
    setRenameTarget(null);
    setRenameValue('');
  }, []);

  const handleDeleteTask = useCallback(
    (record: LlmTask | HttpTask, type: 'llm' | 'http') => {
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
          type === 'llm' ? deleteJob(record.id) : deleteHttpTask(record.id),
      });
    },
    [canManage, deleteHttpTask, deleteJob, messageApi, modal, t]
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
  const columns: ColumnsType<LlmTask> = useMemo(() => {
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

    const tableColumns: ColumnsType<LlmTask> = [
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
        render: (name: string, record: LlmTask) => (
          <div className='table-cell-with-copy'>
            <div className='table-cell-text'>
              <Tooltip title={name} placement='top'>
                <span
                  className='table-cell-text-inner table-cell-link'
                  role='link'
                  tabIndex={0}
                  onClick={e => {
                    e.stopPropagation();
                    window.open(`/llm-results/${record.id}`, '_blank');
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation();
                      window.open(`/llm-results/${record.id}`, '_blank');
                    }
                  }}
                >
                  {name}
                </span>
              </Tooltip>
            </div>
            {canStopOrRename(record.created_by) && (
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

          moreMenuItems.push({
            key: 'collection',
            icon: <FolderAddOutlined />,
            label: t('pages.jobs.addToCollection'),
            onClick: (info: any) => {
              info.domEvent.stopPropagation();
              setSingleAddTaskId(record.id);
              setCollectionModalOpen(true);
            },
          });

          if (canManage(record.created_by)) {
            moreMenuItems.push({
              key: 'copy',
              icon: <CopyOutlined />,
              label: t('pages.jobs.copyTemplate'),
              onClick: (info: any) => {
                info.domEvent.stopPropagation();
                handleCopyJob(record);
              },
            });
          }

          if (
            canStopOrRename(record.created_by) &&
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
                    window.open(`/llm-results/${record.id}`, '_blank');
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
                <Tooltip title={t('pages.jobs.rerun')}>
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
                    icon={<PlayCircleOutlined />}
                    onClick={e => {
                      e.stopPropagation();
                      showRerunConfirm(record, 'llm');
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
    canStopOrRename,
    creatorFilter,
    currentUsername,
    handleCopyJob,
    handleDeleteTask,
    modelFilter,
    openRenameModal,
    renderLoadConfig,
    showRerunConfirm,
    showStopConfirm,
    statusFilter,
    t,
  ]);

  const httpColumns: ColumnsType<HttpTask> = useMemo(() => {
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
      // Use 'mine' as filteredValue when httpCreatorFilter matches currentUsername
      // This ensures Ant Design Table maintains the filter state during pagination
      filteredValue: httpCreatorFilter ? ['mine'] : null,
      filterMultiple: false,
    };

    const tableColumns: ColumnsType<HttpTask> = [
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
        render: (name: string, record: HttpTask) => (
          <div className='table-cell-with-copy'>
            <div className='table-cell-text'>
              <Tooltip title={name} placement='top'>
                <span
                  className='table-cell-text-inner table-cell-link'
                  role='link'
                  tabIndex={0}
                  onClick={e => {
                    e.stopPropagation();
                    window.open(`/http-results/${record.id}`, '_blank');
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation();
                      window.open(`/http-results/${record.id}`, '_blank');
                    }
                  }}
                >
                  {name}
                </span>
              </Tooltip>
            </div>
            {canStopOrRename(record.created_by) && (
              <div className='table-cell-action'>
                <Button
                  type='text'
                  size='small'
                  className='table-action-button'
                  icon={<EditOutlined />}
                  onClick={e => {
                    e.stopPropagation();
                    openRenameModal(record, 'http');
                  }}
                />
              </div>
            )}
          </div>
        ),
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
        filteredValue: httpStatusFilter ? httpStatusFilter.split(',') : null,
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

          moreMenuItems.push({
            key: 'collection',
            icon: <FolderAddOutlined />,
            label: t('pages.jobs.addToCollection'),
            onClick: (info: any) => {
              info.domEvent.stopPropagation();
              setSingleAddTaskId(record.id);
              setCollectionModalOpen(true);
            },
          });

          if (canManage(record.created_by)) {
            moreMenuItems.push({
              key: 'copy',
              icon: <CopyOutlined />,
              label: t('pages.jobs.copyTemplate'),
              onClick: (info: any) => {
                info.domEvent.stopPropagation();
                handleCopyHttpTask(record);
              },
            });
          }

          if (
            canStopOrRename(record.created_by) &&
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
                handleDeleteTask(record, 'http');
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
                    window.open(`/http-results/${record.id}`, '_blank');
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
                <Tooltip title={t('pages.jobs.rerun')}>
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
                    icon={<PlayCircleOutlined />}
                    onClick={e => {
                      e.stopPropagation();
                      showRerunConfirm(record, 'http');
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
    canStopOrRename,
    httpCreatorFilter,
    httpStatusFilter,
    currentUsername,
    handleCopyHttpTask,
    handleDeleteTask,
    openRenameModal,
    renderLoadConfig,
    showRerunConfirm,
    showStopConfirm,
    t,
  ]);

  /**
   * Handle job creation
   */
  const handleCreateTask = useCallback(
    async (values: any) => {
      const success =
        activeMode === 'llm'
          ? await createJob(values)
          : await createHttpTask(values);
      if (success) {
        setIsModalVisible(false);
        setTaskToCopy(null);
        setHttpTaskToCopy(null);
      }
    },
    [activeMode, createHttpTask, createJob]
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

      const useHttp = activeMode === 'http';
      const prevStatus = useHttp ? httpStatusFilter : statusFilter;
      const prevModel = modelFilter;
      const prevCreator = useHttp ? httpCreatorFilter : creatorFilter;

      const isFilterChange =
        newStatusFilter !== prevStatus ||
        newModelFilter !== prevModel ||
        newCreatorFilter !== prevCreator;

      const nextPage = isFilterChange ? 1 : newPagination.current || 1;
      const nextPageSize =
        newPagination.pageSize ||
        (useHttp ? httpPagination.pageSize : pagination.pageSize);

      if (useHttp) {
        // Update filters first if changed
        if (newStatusFilter !== httpStatusFilter) {
          setHttpStatusFilter(newStatusFilter);
        }
        if (newCreatorFilter !== httpCreatorFilter) {
          setHttpCreatorFilter(newCreatorFilter);
        }
        // Trigger fetch with new pagination - manualRefresh will update pagination state
        httpManualRefresh({
          page: nextPage,
          pageSize: nextPageSize,
          status: newStatusFilter,
          search: httpSearchInput,
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
      httpCreatorFilter,
      httpPagination.pageSize,
      httpPagination.total,
      httpManualRefresh,
      httpSearchInput,
      httpStatusFilter,
      creatorFilter,
      currentUsername,
      modelFilter,
      pagination.pageSize,
      pagination.total,
      setHttpCreatorFilter,
      setHttpStatusFilter,
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
    setHttpTaskToCopy(null);
  }, []);

  const handleResetFilters = useCallback(() => {
    if (activeMode === 'http') {
      updateHttpSearchInput('');
      httpManualRefresh({
        page: 1,
        pageSize: httpPagination.pageSize,
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
    httpManualRefresh,
    httpPagination.pageSize,
    performSearch,
    setCreatorFilter,
    setModelFilter,
    setPagination,
    setStatusFilter,
    updateHttpSearchInput,
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
   * Handle batch rerun of selected tasks
   */
  const [batchRerunning, setBatchRerunning] = useState(false);

  const handleBatchRerun = useCallback(() => {
    if (selectedRowKeys.length === 0) return;

    const useHttp = activeMode === 'http';
    const currentData = (useHttp ? httpFilteredJobs : filteredJobs) as Array<
      LlmTask | HttpTask
    >;
    const selectedTasks = currentData.filter(job =>
      selectedRowKeys.includes(job.id)
    );

    // Filter tasks that the current user can manage
    const manageableTasks = selectedTasks.filter(job =>
      canManage(job.created_by)
    );

    if (manageableTasks.length === 0) {
      messageApi.warning(t('pages.jobs.ownerOnly'));
      return;
    }

    modal.confirm({
      title: t('pages.jobs.batchRerunConfirmTitle'),
      icon: <PlayCircleOutlined style={{ color: '#52c41a' }} />,
      content: (
        <div>
          <p>
            {t('pages.jobs.batchRerunConfirmContent', {
              count: manageableTasks.length,
            })}
          </p>
        </div>
      ),
      okText: t('pages.jobs.confirmRerun'),
      okButtonProps: {
        style: {
          backgroundColor: '#52c41a',
          borderColor: '#52c41a',
        },
      },
      cancelText: t('common.cancel'),
      onOk: async () => {
        setBatchRerunning(true);

        const results = await Promise.allSettled(
          manageableTasks.map(async task => {
            if (useHttp) {
              const fullJobResponse = await httpTaskApi.getJob(task.id);
              const fullJob =
                (fullJobResponse.data as HttpTask) || (task as HttpTask);
              const rerunData: any = {
                ...fullJob,
                name: getRerunName(fullJob.name),
                id: undefined,
                status: undefined,
                created_at: undefined,
                updated_at: undefined,
                temp_task_id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                request_body:
                  typeof fullJob.request_body === 'string'
                    ? fullJob.request_body
                    : (fullJob.request_body ?? ''),
              };
              // Call API directly to avoid per-task toast from hook
              const resp = await httpTaskApi.createJob(rerunData);
              return resp.status === 200 || resp.status === 201;
            }
            const fullJobResp = await llmTaskApi.getJob(task.id);
            const fullJob = resolveTaskDetail(fullJobResp, task as any);
            let rerunData: any = {
              ...fullJob,
              name: getRerunName(fullJob.name),
              id: undefined,
              status: undefined,
              created_at: undefined,
              updated_at: undefined,
              result_id: undefined,
              temp_task_id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            };
            if (rerunData.headers) {
              const headerObject =
                typeof rerunData.headers === 'string'
                  ? safeJsonParse(rerunData.headers, [])
                  : rerunData.headers;
              rerunData.headers = deepClone(headerObject) || [];
            }
            if (rerunData.request_payload) {
              rerunData.request_payload =
                typeof rerunData.request_payload === 'string'
                  ? rerunData.request_payload
                  : safeJsonStringify(rerunData.request_payload);
            }
            if (rerunData.field_mapping) {
              const fieldMappingObject =
                typeof rerunData.field_mapping === 'string'
                  ? safeJsonParse(rerunData.field_mapping, {})
                  : rerunData.field_mapping;
              rerunData.field_mapping = deepClone(fieldMappingObject) || {};
            }
            // Preserve warmup configuration
            if (
              rerunData.warmup_enabled !== undefined &&
              rerunData.warmup_enabled !== null
            ) {
              rerunData.warmup_enabled = Boolean(rerunData.warmup_enabled);
            }
            rerunData = withDatasetFields(rerunData, fullJob);
            // Call API directly to avoid per-task toast from hook
            const resp = await llmTaskApi.createJob(rerunData);
            return !!(resp as any)?.data?.task_id;
          })
        );

        const successCount = results.filter(
          r => r.status === 'fulfilled' && r.value
        ).length;
        const failCount = results.length - successCount;

        // Refresh task list once after all tasks are created
        if (useHttp) {
          httpManualRefresh();
        } else {
          manualRefresh();
        }

        setBatchRerunning(false);
        setSelectedRowKeys([]);

        if (failCount === 0) {
          messageApi.success(
            t('pages.jobs.batchRerunAllSuccess', { count: successCount })
          );
        } else {
          messageApi.warning(
            t('pages.jobs.batchRerunProgress', {
              success: successCount,
              fail: failCount,
            })
          );
        }
      },
    });
  }, [
    selectedRowKeys,
    activeMode,
    httpFilteredJobs,
    filteredJobs,
    canManage,
    messageApi,
    modal,
    t,
    getRerunName,
    httpManualRefresh,
    manualRefresh,
  ]);

  /**
   * Navigate to result comparison page with selected tasks
   */
  const handleGoToCompare = useCallback(() => {
    if (selectedRowKeys.length < 2 || selectedRowKeys.length > 5) {
      messageApi.warning(t('pages.jobs.selectMinForCompare'));
      return;
    }
    const mode = activeMode === 'llm' ? 'model' : 'http';
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
      getCheckboxProps: (record: LlmTask | HttpTask) => ({
        disabled: !COMPARABLE_STATUSES.includes(
          record.status?.toLowerCase() ?? ''
        ),
      }),
    }),
    [selectedRowKeys, handleSelectionChange, COMPARABLE_STATUSES]
  );

  const isHttpMode = activeMode === 'http';
  const currentJobs = isHttpMode ? httpFilteredJobs : filteredJobs;

  // Check if all selected tasks can be managed by the current user
  const allSelectedManageable = useMemo(() => {
    if (selectedRowKeys.length === 0) return true;
    const currentData = (isHttpMode ? httpFilteredJobs : filteredJobs) as Array<
      LlmTask | HttpTask
    >;
    const selectedTasks = currentData.filter(job =>
      selectedRowKeys.includes(job.id)
    );
    return selectedTasks.every(job => canManage(job.created_by));
  }, [selectedRowKeys, isHttpMode, httpFilteredJobs, filteredJobs, canManage]);
  const currentPagination = isHttpMode ? httpPagination : pagination;
  const currentLoading = isHttpMode ? httpLoading : loading;
  const currentRefreshing = isHttpMode ? httpRefreshing : refreshing;
  const currentError = isHttpMode ? httpError : error;
  const currentLastRefresh = isHttpMode ? httpLastRefresh : lastRefreshTime;
  const currentSearchInput = isHttpMode ? httpSearchInput : searchInput;
  const currentPerformSearch = isHttpMode ? httpPerformSearch : performSearch;
  const currentUpdateSearchInput = isHttpMode
    ? updateHttpSearchInput
    : updateSearchInput;
  const currentManualRefresh = isHttpMode
    ? () => httpManualRefresh()
    : () => manualRefresh();
  const currentColumns = isHttpMode ? httpColumns : columns;

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
            setActiveMode(key as 'llm' | 'http');
            localStorage.setItem(MODE_STORAGE_KEY, key);
            setSelectedRowKeys([]);
          }}
          items={[
            {
              key: 'http',
              label: (
                <span className='tab-label'>
                  {t('pages.jobs.httpApiTab') || 'HTTP API Load Test'}
                </span>
              ),
            },
            {
              key: 'llm',
              label: (
                <span className='tab-label'>
                  {t('pages.jobs.llmTab') || 'LLM Load Test'}
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
            {isHttpMode && (
              <Tooltip
                title={t('pages.jobs.webOneClickTooltip')}
                placement='bottom'
                styles={{ root: { maxWidth: 280 } }}
              >
                <Button
                  icon={<GlobalOutlined />}
                  onClick={() => setWebOneClickOpen(true)}
                  disabled={currentLoading}
                  className='modern-button-web-quick-test'
                >
                  {t('pages.jobs.webOneClick')}
                </Button>
              </Tooltip>
            )}
            {selectedRowKeys.length > 0 && (
              <>
                <Divider
                  type='vertical'
                  style={{ height: 24, margin: '0 4px' }}
                />
                <span
                  style={{
                    margin: '0 8px',
                    fontSize: 14,
                    color: '#000',
                  }}
                >
                  {t('pages.jobs.selectedCount', {
                    count: selectedRowKeys.length,
                  })}
                </span>
                <Tooltip
                  title={
                    !allSelectedManageable
                      ? t('pages.jobs.batchRerunOwnerOnly')
                      : undefined
                  }
                >
                  <Button
                    icon={<PlayCircleOutlined />}
                    onClick={handleBatchRerun}
                    loading={batchRerunning}
                    disabled={!allSelectedManageable}
                    className='btn-purple-dark'
                  >
                    {t('pages.jobs.batchRerun')}
                  </Button>
                </Tooltip>
                {selectedRowKeys.length >= 2 && selectedRowKeys.length <= 5 && (
                  <Button
                    icon={<BarChartOutlined />}
                    onClick={handleGoToCompare}
                    className='btn-purple-medium'
                  >
                    {t('pages.jobs.goToCompare')}
                  </Button>
                )}
                <Button
                  icon={<FolderAddOutlined />}
                  onClick={() => {
                    setSingleAddTaskId(null);
                    setCollectionModalOpen(true);
                  }}
                  className='btn-purple-light'
                >
                  {t('pages.jobs.addToCollection')}
                </Button>
                <Button
                  icon={<CloseOutlined />}
                  onClick={() => setSelectedRowKeys([])}
                  className='modern-button'
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {t('pages.jobs.clearSelection')}
                </Button>
              </>
            )}
          </div>
          <div className='jobs-toolbar-right'>
            {currentRefreshing && <Badge status='processing' />}
            {renderLastRefreshTime(currentLastRefresh)}
            <Search
              placeholder={t('pages.jobs.searchPlaceholder')}
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
        title={
          taskToCopy || httpTaskToCopy
            ? t('pages.jobs.edit')
            : t('pages.jobs.createNew')
        }
        open={isModalVisible}
        onCancel={handleModalCancel}
        footer={null}
        width={900}
        destroyOnHidden
        maskClosable={false}
      >
        {activeMode === 'llm' ? (
          <CreateLlmTaskForm
            onSubmit={handleCreateTask}
            onCancel={handleModalCancel}
            loading={currentLoading}
            initialData={taskToCopy}
            suppressCopyWarning={!!taskToCopy}
          />
        ) : (
          <CreateHttpTaskForm
            onSubmit={handleCreateTask}
            onCancel={handleModalCancel}
            loading={currentLoading}
            initialData={httpTaskToCopy}
          />
        )}
      </Modal>

      <WebOneClickModal
        open={webOneClickOpen}
        onClose={() => setWebOneClickOpen(false)}
        onTaskCreated={() => httpManualRefresh()}
      />

      <AddToCollectionModal
        open={collectionModalOpen}
        onCancel={() => {
          setCollectionModalOpen(false);
          setSingleAddTaskId(null);
        }}
        taskIds={
          singleAddTaskId
            ? [singleAddTaskId]
            : selectedRowKeys.map(k => String(k))
        }
        taskType={activeMode}
        onSuccess={() => {
          if (!singleAddTaskId) setSelectedRowKeys([]);
        }}
      />
    </div>
  );
};

export default Tasks;
