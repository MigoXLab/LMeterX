/**
 * @file CollectionDetail.tsx
 * @description Collection Detail page for managing collection tasks and rich text reports
 */
import {
  ArrowLeftOutlined,
  BarChartOutlined,
  EditOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import {
  Button,
  Input,
  message,
  Space,
  Table,
  Tabs,
  Tooltip,
  Typography,
} from 'antd';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/apiClient';
import MarkdownRenderer from '../components/ui/MarkdownRenderer';
import { PageHeader } from '../components/ui/PageHeader';
import StatusTag from '../components/ui/StatusTag';
import { Collection, CollectionTaskItem } from '../types/collection';
import { getStoredUser } from '../utils/auth';
import { formatDate } from '../utils/date';

const { Text } = Typography;
const { TextArea } = Input;

const CollectionDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [tasks, setTasks] = useState<CollectionTaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [tasksLoading, setTasksLoading] = useState(false);

  // Edit mode states
  const [isEditingContent, setIsEditingContent] = useState(false);
  const [editContent, setEditContent] = useState('');
  const currentUser = getStoredUser();
  const canEdit =
    currentUser?.is_admin || collection?.created_by === currentUser?.username;

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
    const modeTasks = tasks.filter(t => t.task_type === mode);
    if (modeTasks.length < 2) {
      message.warning(
        t('pages.collectionDetail.needAtLeast2', { mode: mode.toUpperCase() })
      );
      return;
    }
    const taskIds = modeTasks.map(t => t.id).join(',');
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
      width: 100,
      render: (_: any, record: CollectionTaskItem) =>
        canEdit ? (
          <Button
            danger
            type='text'
            size='small'
            onClick={() => handleRemoveTask(record.id)}
          >
            {t('pages.collectionDetail.remove')}
          </Button>
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
                                disabled={llmTasks.length < 2}
                              >
                                {t('pages.collectionDetail.compareLlm')}
                              </Button>
                              {llmTasks.length < 2 && (
                                <Text
                                  type='secondary'
                                  style={{ marginLeft: 8 }}
                                >
                                  {t('pages.collectionDetail.selectAtLeast2')}
                                </Text>
                              )}
                            </div>
                            <Table
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
                                disabled={httpTasks.length < 2}
                              >
                                {t('pages.collectionDetail.compareHttp')}
                              </Button>
                              {httpTasks.length < 2 && (
                                <Text
                                  type='secondary'
                                  style={{ marginLeft: 8 }}
                                >
                                  {t('pages.collectionDetail.selectAtLeast2')}
                                </Text>
                              )}
                            </div>
                            <Table
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
    </div>
  );
};

export default CollectionDetail;
