/**
 * @file CollectionDetail.tsx
 * @description Collection Detail page for managing collection tasks and rich text reports
 */
import {
  ArrowLeftOutlined,
  BarChartOutlined,
  CopyOutlined,
  EditOutlined,
  MinusCircleOutlined,
  PlayCircleOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import {
  App,
  Button,
  Input,
  message,
  Modal,
  Space,
  Table,
  Tabs,
  Tooltip,
  Typography,
} from 'antd';
import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/apiClient';
import { httpTaskApi, llmTaskApi } from '../api/services';
import CreateHttpTaskForm from '../components/CreateHttpTaskForm';
import CreateLlmTaskForm from '../components/CreateLlmTaskForm';
import MarkdownRenderer from '../components/ui/MarkdownRenderer';
import { PageHeader } from '../components/ui/PageHeader';
import StatusTag from '../components/ui/StatusTag';
import { Collection, CollectionTaskItem } from '../types/collection';
import { HttpTask, LlmTask } from '../types/job';
import { getStoredUser } from '../utils/auth';
import { deepClone, safeJsonParse, safeJsonStringify } from '../utils/data';
import { formatDate } from '../utils/date';

const { Text } = Typography;
const { TextArea } = Input;

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
      try {
        const parts = testDataStr.split(/[\\/]/);
        const filename = parts[parts.length - 1] || '';
        if (filename) {
          next.test_data_file = filename;
        }
      } catch {
        // ignore
      }
    } else if (looksLikeInlineJson) {
      next.test_data_input_type = 'input';
    } else {
      next.test_data_input_type = 'input';
    }
  }

  return next as T;
};

const CollectionDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [tasks, setTasks] = useState<CollectionTaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [tasksLoading, setTasksLoading] = useState(false);

  // Selection states
  const [selectedLlmTaskIds, setSelectedLlmTaskIds] = useState<React.Key[]>([]);
  const [selectedHttpTaskIds, setSelectedHttpTaskIds] = useState<React.Key[]>(
    []
  );

  // Edit mode states
  const [isEditingContent, setIsEditingContent] = useState(false);
  const [editContent, setEditContent] = useState('');
  const currentUser = getStoredUser();
  const canEdit =
    currentUser?.is_admin || collection?.created_by === currentUser?.username;

  const [isModalVisible, setIsModalVisible] = useState(false);
  const [taskToCopy, setTaskToCopy] = useState<Partial<LlmTask> | null>(null);
  const [httpTaskToCopy, setHttpTaskToCopy] =
    useState<Partial<HttpTask> | null>(null);
  const [activeMode, setActiveMode] = useState<'llm' | 'http'>('llm');
  const [currentLoading, setCurrentLoading] = useState(false);

  const { modal } = App.useApp();

  const getRerunName = useCallback((name?: string): string => {
    const baseName = name || 'Task';
    const match = baseName.match(/^(.*)-(\d+)$/);
    if (match) {
      return `${match[1]}-${parseInt(match[2]) + 1}`;
    }
    return `${baseName}-1`;
  }, []);

  const fetchCollection = async () => {
    setLoading(true);
    try {
      const response = await api.get<Collection>(`/collections/${id}`);
      const { data } = response;
      setCollection(data);
      setEditContent(data.rich_content || '');
    } catch (error) {
      message.error(t('pages.collectionDetail.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchTasks = async () => {
    setTasksLoading(true);
    try {
      const response = await api.get<{ data: CollectionTaskItem[] }>(
        `/collections/${id}/tasks`
      );
      const { data } = response;
      setTasks(data.data || []);
    } catch (error) {
      message.error(t('pages.collectionDetail.loadTasksFailed'));
    } finally {
      setTasksLoading(false);
    }
  };

  const handleRerunJob = useCallback(
    async (job: CollectionTaskItem) => {
      if (!canEdit) {
        message.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const fullJobResp = await llmTaskApi.getJob(job.id);
        const fullJob = resolveTaskDetail(fullJobResp, job as any);

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

        if (
          rerunData.warmup_enabled !== undefined &&
          rerunData.warmup_enabled !== null
        ) {
          rerunData.warmup_enabled = Boolean(rerunData.warmup_enabled);
        }

        rerunData = withDatasetFields(rerunData, fullJob);

        const resp = await llmTaskApi.createJob(rerunData);
        const newTaskId =
          (resp as any)?.data?.task_id || (resp as any)?.data?.id;
        if (newTaskId) {
          await api.post(`/collections/${id}/tasks`, {
            task_id: newTaskId,
            task_type: 'llm',
          });
          fetchTasks();
          fetchCollection();
          message.success(t('pages.jobs.rerunSuccess'));
        } else {
          message.error(t('pages.jobs.rerunFailed'));
        }
      } catch (error) {
        console.error('Failed to rerun job:', error);
        message.error(t('pages.jobs.rerunFailed'));
      }
    },
    [canEdit, getRerunName, id, t]
  );

  const handleRerunHttpTask = useCallback(
    async (job: CollectionTaskItem) => {
      if (!canEdit) {
        message.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const fullJobResponse = await httpTaskApi.getJob(job.id);
        const fullJob = (fullJobResponse.data as any) || job;

        let rerunData: any = {
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

        if (rerunData.headers) {
          const headerObject =
            typeof rerunData.headers === 'string'
              ? safeJsonParse(rerunData.headers, [])
              : rerunData.headers;
          rerunData.headers = deepClone(headerObject) || [];
        }

        rerunData = withDatasetFields(rerunData, fullJob);

        const resp = await httpTaskApi.createJob(rerunData);
        const newTaskId =
          (resp as any)?.data?.task_id || (resp as any)?.data?.id;
        if (newTaskId) {
          await api.post(`/collections/${id}/tasks`, {
            task_id: newTaskId,
            task_type: 'http',
          });
          fetchTasks();
          fetchCollection();
          message.success(t('pages.jobs.rerunSuccess'));
        } else {
          message.error(t('pages.jobs.rerunFailed'));
        }
      } catch (error) {
        console.error('Failed to rerun http task:', error);
        message.error(t('pages.jobs.rerunFailed'));
      }
    },
    [canEdit, getRerunName, id, t]
  );

  const showRerunConfirm = useCallback(
    (record: CollectionTaskItem, type: 'llm' | 'http') => {
      modal.confirm({
        title: t('pages.jobs.rerunConfirmTitle'),
        icon: <PlayCircleOutlined style={{ color: '#1677ff' }} />,
        content: (
          <span>
            {t('pages.jobs.rerunConfirmContent')}{' '}
            <Text code>{record.name || record.id}</Text>
          </span>
        ),
        okText: t('pages.jobs.confirmRerun'),
        cancelText: t('common.cancel'),
        onOk: () =>
          type === 'llm' ? handleRerunJob(record) : handleRerunHttpTask(record),
      });
    },
    [handleRerunHttpTask, handleRerunJob, modal, t]
  );

  const handleCopyJob = useCallback(
    async (job: CollectionTaskItem) => {
      if (!canEdit) {
        message.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const copiedName = job.name
          ? `${job.name} (Copy)`
          : `Copy Task ${job.id.substring(0, 8)}`;

        const fullJobResp = await llmTaskApi.getJob(job.id);
        const fullJob = resolveTaskDetail(fullJobResp, job as any);

        let jobToCopyData: Partial<LlmTask> = {
          ...fullJob,
          name: copiedName,
          id: undefined,
          status: undefined,
          created_at: undefined,
          updated_at: undefined,
        };

        if (jobToCopyData.headers) {
          const headerObject =
            typeof jobToCopyData.headers === 'string'
              ? safeJsonParse(jobToCopyData.headers, [])
              : jobToCopyData.headers;
          jobToCopyData.headers = deepClone(headerObject) || [];
        }

        if (jobToCopyData.request_payload) {
          jobToCopyData.request_payload =
            typeof jobToCopyData.request_payload === 'string'
              ? jobToCopyData.request_payload
              : safeJsonStringify(jobToCopyData.request_payload);
        }

        if (jobToCopyData.field_mapping) {
          const fieldMappingObject =
            typeof jobToCopyData.field_mapping === 'string'
              ? safeJsonParse(jobToCopyData.field_mapping, {})
              : jobToCopyData.field_mapping;

          const completeFieldMapping = {
            prompt: '',
            stream_prefix: '',
            data_format: 'json',
            content: '',
            reasoning_content: '',
            end_prefix: '',
            stop_flag: '',
            end_field: '',
            ...fieldMappingObject,
          };

          jobToCopyData.field_mapping = deepClone(completeFieldMapping) || {};
        } else {
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

        setActiveMode('llm');
        setTaskToCopy(jobToCopyData);
        setIsModalVisible(true);
      } catch (error) {
        console.error('Failed to fetch full job details:', error);
        message.error(t('pages.jobs.copyError', 'Failed to load task details'));
      }
    },
    [canEdit, t]
  );

  const handleCopyHttpTask = useCallback(
    async (job: CollectionTaskItem) => {
      if (!canEdit) {
        message.warning(t('pages.jobs.ownerOnly'));
        return;
      }
      try {
        const fullJobResponse = await httpTaskApi.getJob(job.id);
        const fullJob = (fullJobResponse.data as any) || job;

        const copiedName = job.name
          ? `${job.name} (Copy)`
          : `Copy Task ${job.id.substring(0, 8)}`;

        let jobToCopyData: Partial<HttpTask> = {
          ...fullJob,
          name: copiedName,
          id: undefined,
          status: undefined,
          created_at: undefined,
          updated_at: undefined,
          request_body:
            typeof fullJob.request_body === 'string'
              ? fullJob.request_body
              : (fullJob.request_body ?? ''),
        };

        if (jobToCopyData.headers) {
          const headerObject =
            typeof jobToCopyData.headers === 'string'
              ? safeJsonParse(jobToCopyData.headers, [])
              : jobToCopyData.headers;
          jobToCopyData.headers = deepClone(headerObject) || [];
        }

        jobToCopyData = withDatasetFields(jobToCopyData as any, fullJob);

        setActiveMode('http');
        setHttpTaskToCopy(jobToCopyData);
        setIsModalVisible(true);
      } catch (error) {
        console.error('Failed to fetch full HTTP task details:', error);
        message.error(t('pages.jobs.copyError', 'Failed to load task details'));
      }
    },
    [canEdit, t]
  );

  const handleModalCancel = useCallback(() => {
    setIsModalVisible(false);
    setTaskToCopy(null);
    setHttpTaskToCopy(null);
  }, []);

  const handleCreateTask = useCallback(
    async (values: any) => {
      setCurrentLoading(true);
      try {
        const resp =
          activeMode === 'llm'
            ? await llmTaskApi.createJob(values)
            : await httpTaskApi.createJob(values);
        const newTaskId =
          (resp as any)?.data?.task_id || (resp as any)?.data?.id;
        if (newTaskId) {
          await api.post(`/collections/${id}/tasks`, {
            task_id: newTaskId,
            task_type: activeMode,
          });
          fetchTasks();
          fetchCollection();
          message.success(t('pages.jobs.createSuccess'));
          setIsModalVisible(false);
          setTaskToCopy(null);
          setHttpTaskToCopy(null);
        } else {
          message.error(t('pages.jobs.createFailed'));
        }
      } catch (error) {
        console.error('Failed to create task:', error);
        message.error(t('pages.jobs.createFailed'));
      } finally {
        setCurrentLoading(false);
      }
    },
    [activeMode, id, t]
  );

  useEffect(() => {
    if (id) {
      fetchCollection();
      fetchTasks();
    }
  }, [id]);

  const handleSaveContent = async () => {
    try {
      await api.put(`/collections/${id}`, { rich_content: editContent });
      message.success(t('pages.collectionDetail.saveSuccess'));
      setIsEditingContent(false);
      fetchCollection();
    } catch (error) {
      message.error(t('pages.collectionDetail.saveFailed'));
    }
  };

  const handleSaveDescription = async (newDescription: string) => {
    try {
      await api.put(`/collections/${id}`, { description: newDescription });
      message.success(t('pages.collectionDetail.saveSuccess'));
      fetchCollection();
    } catch (error) {
      message.error(t('pages.collectionDetail.saveFailed'));
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        e.preventDefault();

        // Check existing images count limit
        const existingImagesCount = (editContent.match(/data:image/g) || [])
          .length;
        if (existingImagesCount >= 2) {
          message.warning(
            t('pages.collectionDetail.maxImagesLimit', 'Limit to 2 images')
          );
          return;
        }

        const file = items[i].getAsFile();
        if (file) {
          // Check file size (2MB limit)
          const MAX_SIZE = 2 * 1024 * 1024; // 2MB
          if (file.size > MAX_SIZE) {
            message.warning(
              t(
                'pages.collectionDetail.imageTooLarge',
                'Image size cannot exceed 2MB'
              )
            );
            return;
          }

          const reader = new FileReader();
          reader.onload = event => {
            const base64 = event.target?.result as string;
            const textarea = e.target as HTMLTextAreaElement;
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;

            // Generate unique identifier for the image reference
            const uniqueId = `img_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;

            // The short reference to insert at cursor position
            const imageMarkdown = `![image][${uniqueId}]`;

            // The actual base64 data to append at the end of the document
            const base64Reference = `\n[${uniqueId}]: ${base64}\n`;

            // Replace the selected text (if any) with the short reference
            let newContent =
              editContent.substring(0, start) +
              imageMarkdown +
              editContent.substring(end);

            // Ensure there's a newline before appending the reference at the end
            if (newContent && !newContent.endsWith('\n')) {
              newContent += '\n';
            }
            newContent += base64Reference;

            setEditContent(newContent);

            // Keep cursor immediately after the inserted reference
            setTimeout(() => {
              textarea.selectionStart = start + imageMarkdown.length;
              textarea.selectionEnd = start + imageMarkdown.length;
            }, 0);
          };
          reader.readAsDataURL(file);
        }
        break; // Only handle the first image
      }
    }
  };

  const handleRemoveTask = async (taskId: string) => {
    try {
      await api.delete(`/collections/${id}/tasks/${taskId}`);
      message.success(t('pages.collectionDetail.removeSuccess'));
      fetchTasks();
      fetchCollection(); // Update task count
    } catch (error) {
      message.error(t('pages.collectionDetail.removeFailed'));
    }
  };

  const goToComparison = (mode: 'http' | 'llm') => {
    const selectedIds =
      mode === 'llm' ? selectedLlmTaskIds : selectedHttpTaskIds;
    if (selectedIds.length < 2) {
      message.warning(
        t('pages.collectionDetail.needAtLeast2', { mode: mode.toUpperCase() })
      );
      return;
    }
    const taskIds = selectedIds.join(',');
    navigate(
      `/result-comparison?mode=${mode === 'llm' ? 'model' : 'http'}&tasks=${taskIds}`
    );
  };

  const llmTasks = tasks.filter(t => t.task_type === 'llm');
  const httpTasks = tasks.filter(t => t.task_type === 'http');

  const taskColumns = [
    {
      title: t('pages.jobs.taskName'),
      dataIndex: 'name',
      key: 'name',
      width: 300,
      ellipsis: true,
      render: (text: string, record: CollectionTaskItem) => (
        <Button
          type='link'
          style={{ padding: 0 }}
          onClick={() => {
            const basePath =
              record.task_type === 'llm' ? '/llm-results' : '/http-results';
            navigate(`${basePath}/${record.id}`);
          }}
        >
          {text}
        </Button>
      ),
    },
    {
      title: t('pages.jobs.loadConfig'),
      key: 'load_config',
      width: 150,
      render: (_: any, record: CollectionTaskItem) => {
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
      render: (text: string) => <StatusTag status={text} />,
    },
    {
      title: t('pages.jobs.createdTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => formatDate(time),
    },
    {
      title: t('pages.jobs.actions'),
      key: 'action',
      width: 140,
      render: (_: any, record: CollectionTaskItem) =>
        canEdit ? (
          <Space size={4}>
            <Tooltip title={t('pages.jobs.rerun')}>
              <Button
                type='text'
                size='small'
                className='action-icon-btn'
                icon={<PlayCircleOutlined />}
                onClick={e => {
                  e.stopPropagation();
                  showRerunConfirm(record, record.task_type);
                }}
              />
            </Tooltip>
            <Tooltip title={t('pages.jobs.copyTemplate')}>
              <Button
                type='text'
                size='small'
                className='action-icon-btn'
                icon={<CopyOutlined />}
                onClick={e => {
                  e.stopPropagation();
                  if (record.task_type === 'llm') {
                    handleCopyJob(record);
                  } else {
                    handleCopyHttpTask(record);
                  }
                }}
              />
            </Tooltip>
            <Tooltip title={t('pages.collectionDetail.remove')}>
              <Button
                danger
                type='text'
                size='small'
                className='action-icon-btn'
                icon={<MinusCircleOutlined />}
                onClick={e => {
                  e.stopPropagation();
                  handleRemoveTask(record.id);
                }}
              />
            </Tooltip>
          </Space>
        ) : null,
    },
  ];

  if (loading && !collection)
    return <div className='p-24 text-center'>{t('common.loading')}</div>;
  if (!collection)
    return (
      <div className='p-24 text-center'>
        {t('pages.collectionDetail.notFound')}
      </div>
    );

  return (
    <div className='page-container results-page'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={
            <Space>
              <Button
                type='text'
                icon={<ArrowLeftOutlined />}
                onClick={() => navigate('/collections')}
              />
              {collection.name}
            </Space>
          }
          level={3}
        />
        <div style={{ paddingLeft: '44px', marginTop: '8px' }}>
          <Typography.Paragraph
            type='secondary'
            editable={
              canEdit
                ? {
                    onChange: handleSaveDescription,
                    tooltip: t('common.edit') || 'Edit',
                    maxLength: 5000,
                  }
                : false
            }
          >
            {collection.description ||
              t('pages.collectionDetail.noDescription')}
          </Typography.Paragraph>
        </div>
      </div>

      <div className='results-content' style={{ padding: '24px' }}>
        <div className='results-section unified-section'>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.collectionDetail.reportContent')}
            </span>
            <div>
              {canEdit &&
                (isEditingContent ? (
                  <Space>
                    <Button onClick={() => setIsEditingContent(false)}>
                      {t('pages.collectionDetail.cancel')}
                    </Button>
                    <Button
                      type='primary'
                      icon={<SaveOutlined />}
                      onClick={handleSaveContent}
                    >
                      {t('pages.collectionDetail.save')}
                    </Button>
                  </Space>
                ) : (
                  <Button
                    type='primary'
                    className='modern-button-primary'
                    icon={<EditOutlined />}
                    onClick={() => setIsEditingContent(true)}
                  >
                    {t('pages.collectionDetail.editReport')}
                  </Button>
                ))}
            </div>
          </div>
          <div className='section-content'>
            {isEditingContent ? (
              <div>
                <div style={{ marginBottom: 8, color: '#8c8ea6' }}>
                  {t('pages.collectionDetail.markdownSupport')}
                </div>
                <TextArea
                  rows={15}
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  onPaste={handlePaste}
                  placeholder={t('pages.collectionDetail.reportPlaceholder')}
                />
              </div>
            ) : (
              <div style={{ minHeight: 150 }}>
                {collection.rich_content ? (
                  <MarkdownRenderer content={collection.rich_content} />
                ) : (
                  <div
                    style={{
                      color: '#8c8ea6',
                      padding: '20px 0',
                    }}
                  >
                    {t('pages.collectionDetail.noReport')}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <div className='results-section unified-section'>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.collectionDetail.associatedTasks')}
            </span>
          </div>
          <div className='section-content'>
            <Tabs
              items={[
                ...(llmTasks.length > 0
                  ? [
                      {
                        key: 'llm',
                        label: t('pages.collectionDetail.llmTasks', {
                          count: llmTasks.length,
                        }),
                        children: (
                          <>
                            <div style={{ marginBottom: 16 }}>
                              <Button
                                type='primary'
                                icon={<BarChartOutlined />}
                                onClick={() => goToComparison('llm')}
                                disabled={
                                  selectedLlmTaskIds.length < 2 ||
                                  selectedLlmTaskIds.length > 5
                                }
                              >
                                {t('pages.collectionDetail.compareLlm')}
                              </Button>
                              {selectedLlmTaskIds.length < 2 ? (
                                <Text
                                  type='secondary'
                                  style={{ marginLeft: 8 }}
                                >
                                  {t('pages.collectionDetail.selectAtLeast2')}
                                </Text>
                              ) : selectedLlmTaskIds.length > 5 ? (
                                <Text
                                  type='danger'
                                  style={{ marginLeft: 8, color: '#ff4d4f' }}
                                >
                                  {t(
                                    'pages.collectionDetail.selectMax5',
                                    '最多只能选择5个任务进行对比'
                                  )}
                                </Text>
                              ) : null}
                            </div>
                            <Table
                              rowSelection={{
                                selectedRowKeys: selectedLlmTaskIds,
                                onChange: newSelectedRowKeys => {
                                  if (
                                    newSelectedRowKeys.length > 5 &&
                                    newSelectedRowKeys.length >
                                      selectedLlmTaskIds.length
                                  ) {
                                    message.warning(
                                      t(
                                        'pages.collectionDetail.maxCompareLimit',
                                        '最多只能选择5个任务进行对比'
                                      )
                                    );
                                  }
                                  setSelectedLlmTaskIds(newSelectedRowKeys);
                                },
                              }}
                              columns={taskColumns}
                              dataSource={llmTasks}
                              rowKey='id'
                              size='small'
                              pagination={false}
                              loading={tasksLoading}
                              className='modern-table'
                            />
                          </>
                        ),
                      },
                    ]
                  : []),
                ...(httpTasks.length > 0
                  ? [
                      {
                        key: 'http',
                        label: t('pages.collectionDetail.httpTasks', {
                          count: httpTasks.length,
                        }),
                        children: (
                          <>
                            <div style={{ marginBottom: 16 }}>
                              <Button
                                type='primary'
                                icon={<BarChartOutlined />}
                                onClick={() => goToComparison('http')}
                                disabled={
                                  selectedHttpTaskIds.length < 2 ||
                                  selectedHttpTaskIds.length > 5
                                }
                              >
                                {t('pages.collectionDetail.compareHttp')}
                              </Button>
                              {selectedHttpTaskIds.length < 2 ? (
                                <Text
                                  type='secondary'
                                  style={{ marginLeft: 8 }}
                                >
                                  {t('pages.collectionDetail.selectAtLeast2')}
                                </Text>
                              ) : selectedHttpTaskIds.length > 5 ? (
                                <Text
                                  type='danger'
                                  style={{ marginLeft: 8, color: '#ff4d4f' }}
                                >
                                  {t(
                                    'pages.collectionDetail.selectMax5',
                                    '最多只能选择5个任务进行对比'
                                  )}
                                </Text>
                              ) : null}
                            </div>
                            <Table
                              rowSelection={{
                                selectedRowKeys: selectedHttpTaskIds,
                                onChange: newSelectedRowKeys => {
                                  if (
                                    newSelectedRowKeys.length > 5 &&
                                    newSelectedRowKeys.length >
                                      selectedHttpTaskIds.length
                                  ) {
                                    message.warning(
                                      t(
                                        'pages.collectionDetail.maxCompareLimit',
                                        '最多只能选择5个任务进行对比'
                                      )
                                    );
                                  }
                                  setSelectedHttpTaskIds(newSelectedRowKeys);
                                },
                              }}
                              columns={taskColumns}
                              dataSource={httpTasks}
                              rowKey='id'
                              size='small'
                              pagination={false}
                              loading={tasksLoading}
                              className='modern-table'
                            />
                          </>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          </div>
        </div>
      </div>
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
    </div>
  );
};

export default CollectionDetail;
