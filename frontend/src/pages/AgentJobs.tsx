import {
  BarChartOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  LineChartOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  App,
  Button,
  Divider,
  Dropdown,
  Input,
  Modal,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { agentTaskApi, clusterApi } from '@/api/services';
import AddToCollectionModal from '@/components/AddToCollectionModal';
import CreateAgentTaskForm from '@/components/CreateAgentTaskForm';
import CopyButton from '@/components/ui/CopyButton';
import StatusTag from '@/components/ui/StatusTag';
import { useI18n } from '@/hooks/useI18n';
import { AgentTask, AgentTaskPayload, Cluster } from '@/types/job';
import { getStoredUser } from '@/utils/auth';
import { UI_CONFIG } from '@/utils/constants';
import { formatDate, getTimestamp } from '@/utils/date';

const { Text } = Typography;
const { Search } = Input;

const ACTIVE_STATUSES = new Set(['created', 'queuing', 'running', 'stopping']);

interface AgentJobsProps {
  protocol: 'a2a' | 'mcp';
  canCreate: boolean;
  showCreator: boolean;
}

const AgentJobs: React.FC<AgentJobsProps> = ({
  protocol,
  canCreate,
  showCreator,
}) => {
  const { message, modal } = App.useApp();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [taskToCopy, setTaskToCopy] = useState<Partial<AgentTask> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [renameTarget, setRenameTarget] = useState<AgentTask | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renaming, setRenaming] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchRerunning, setBatchRerunning] = useState(false);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [singleAddTaskId, setSingleAddTaskId] = useState<string | null>(null);
  const currentUser = useMemo(() => getStoredUser(), []);
  const COMPARABLE_STATUSES = useMemo(
    () => ['completed', 'failed_requests'],
    []
  );
  const SELECTABLE_STATUSES = useMemo(
    () => ['completed', 'failed_requests', 'stopped'],
    []
  );

  const canManageTask = useCallback(
    (creator?: string) =>
      creator === '-' ||
      currentUser?.is_admin === true ||
      (!!creator && creator === currentUser?.username),
    [currentUser]
  );

  const filteredTasks = useMemo(() => {
    const keyword = searchInput.trim().toLowerCase();
    if (!keyword) return tasks;
    return tasks.filter(task =>
      [task.id, task.name, task.target_url].some(value =>
        String(value || '')
          .toLowerCase()
          .includes(keyword)
      )
    );
  }, [searchInput, tasks]);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const response = await agentTaskApi.getAll(1, 100, protocol);
      setTasks(response.data?.data || []);
    } catch {
      message.error(t('common.fetchTasksFailed'));
    } finally {
      setLoading(false);
    }
  }, [message, protocol, t]);

  useEffect(() => {
    loadTasks();
    clusterApi
      .getAllClusters()
      .then(response => {
        const body: any = response as any;
        const values = Array.isArray(body)
          ? body
          : Array.isArray(body?.data)
            ? body.data
            : Array.isArray(body?.data?.clusters)
              ? body.data.clusters
              : Array.isArray(body?.data?.data)
                ? body.data.data
                : [];
        const sorted = [...values].sort((a, b) => {
          const aHasSlots = (a.available_slots || 0) > 0;
          const bHasSlots = (b.available_slots || 0) > 0;
          if (aHasSlots && !bHasSlots) return -1;
          if (!aHasSlots && bHasSlots) return 1;
          return (a.id || '').localeCompare(b.id || '');
        });
        setClusters(sorted);
      })
      .catch(() => setClusters([]));
  }, [loadTasks]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (tasks.some(item => ACTIVE_STATUSES.has(item.status))) loadTasks();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadTasks, tasks]);

  const handleCreate = async (payload: AgentTaskPayload): Promise<boolean> => {
    try {
      setSubmitting(true);
      await agentTaskApi.create(payload);
      message.success(t('components.createAgentTaskForm.createSuccess'));
      setModalOpen(false);
      await loadTasks();
      return true;
    } catch (error: any) {
      message.error(
        error?.message || t('components.createAgentTaskForm.createFailed')
      );
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const openCreate = () => {
    setTaskToCopy(null);
    setModalOpen(true);
  };

  const handleCopy = async (row: AgentTask) => {
    try {
      const response = await agentTaskApi.getCopyTemplate(row.id);
      const detail = response.data || row;
      setTaskToCopy({
        ...detail,
        id: undefined,
        name: `${detail.name} (Copy)`.slice(0, 100),
        status: undefined,
        created_at: undefined,
        updated_at: undefined,
        dataset_file: undefined,
      });
      setModalOpen(true);
      if (detail.has_configured_headers || detail.dataset_configured) {
        const warnings: string[] = [];
        if (detail.has_configured_headers) {
          warnings.push(
            t('pages.jobs.copyInheritHeaders', {
              keys: (detail.redacted_header_keys || []).join(', '),
            })
          );
        }
        if (detail.dataset_configured) {
          warnings.push(t('pages.jobs.copyInheritDataset'));
        }
        message.info(
          t('pages.jobs.copyInheritReady', { details: warnings.join('; ') })
        );
      }
    } catch (error: any) {
      message.error(error?.message || t('pages.jobs.copyError'));
    }
  };

  const handleRerun = (row: AgentTask) => {
    modal.confirm({
      title: t('pages.jobs.rerunConfirmTitle'),
      content: (
        <span>
          {t('pages.jobs.rerunConfirmContent')}
          <Text strong style={{ marginLeft: 4 }}>
            {row.name}
          </Text>
        </span>
      ),
      okText: t('pages.jobs.confirmRerun'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        await agentTaskApi.rerun(row.id);
        message.success(t('pages.jobs.rerunSuccess'));
        await loadTasks();
      },
    });
  };

  const handleRename = async () => {
    if (!renameTarget) return;
    const value = renameValue.trim();
    if (!value) {
      message.warning(t('pages.jobs.renameEmpty'));
      return;
    }
    try {
      setRenaming(true);
      await agentTaskApi.update(renameTarget.id, { name: value });
      message.success(t('pages.jobs.renameSuccess'));
      setRenameTarget(null);
      setRenameValue('');
      await loadTasks();
    } catch (error: any) {
      message.error(error?.message || t('pages.jobs.renameFailed'));
    } finally {
      setRenaming(false);
    }
  };

  const handleStop = (row: AgentTask) => {
    modal.confirm({
      title: t('pages.jobs.stopConfirmTitle'),
      content: (
        <span>
          {t('pages.jobs.stopConfirmContent')}
          <Text strong style={{ marginLeft: 4 }}>
            {row.name}
          </Text>
        </span>
      ),
      okText: t('pages.jobs.confirmStop'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await agentTaskApi.stop(row.id);
        message.success(t('pages.jobs.stopSuccess'));
        await loadTasks();
      },
    });
  };

  const handleSelectionChange = useCallback(
    (newSelectedRowKeys: React.Key[]) => {
      if (newSelectedRowKeys.length > 5) {
        message.warning(t('pages.jobs.selectMaxForCompare'));
        return;
      }
      setSelectedRowKeys(newSelectedRowKeys);
    },
    [message, t]
  );

  const handleBatchRerun = useCallback(() => {
    if (selectedRowKeys.length === 0) return;

    const selectedTasks = tasks.filter(task =>
      selectedRowKeys.includes(task.id)
    );
    const manageableTasks = selectedTasks.filter(task =>
      canManageTask(task.created_by)
    );

    if (manageableTasks.length === 0) {
      message.warning(t('pages.jobs.ownerOnly'));
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
            const resp = await agentTaskApi.rerun(task.id);
            return !!(resp as any)?.data?.task_id;
          })
        );
        const successCount = results.filter(
          result => result.status === 'fulfilled' && result.value
        ).length;
        const failCount = results.length - successCount;
        await loadTasks();
        setBatchRerunning(false);
        setSelectedRowKeys([]);
        if (failCount === 0) {
          message.success(
            t('pages.jobs.batchRerunAllSuccess', { count: successCount })
          );
        } else {
          message.warning(
            t('pages.jobs.batchRerunProgress', {
              success: successCount,
              fail: failCount,
            })
          );
        }
      },
    });
  }, [canManageTask, loadTasks, message, modal, selectedRowKeys, t, tasks]);

  const handleGoToCompare = useCallback(() => {
    if (selectedRowKeys.length < 2 || selectedRowKeys.length > 5) {
      message.warning(t('pages.jobs.selectMinForCompare'));
      return;
    }
    const taskIds = selectedRowKeys.join(',');
    navigate(`/result-comparison?tasks=${taskIds}&mode=${protocol}`);
  }, [message, navigate, protocol, selectedRowKeys, t]);

  const allSelectedManageable = useMemo(() => {
    if (selectedRowKeys.length === 0) return true;
    const selectedTasks = tasks.filter(task =>
      selectedRowKeys.includes(task.id)
    );
    return selectedTasks.every(task => canManageTask(task.created_by));
  }, [canManageTask, selectedRowKeys, tasks]);

  const allSelectedComparable = useMemo(() => {
    if (selectedRowKeys.length === 0) return false;
    const selectedTasks = tasks.filter(task =>
      selectedRowKeys.includes(task.id)
    );
    return (
      selectedTasks.length > 0 &&
      selectedTasks.every(task =>
        COMPARABLE_STATUSES.includes(task.status?.toLowerCase() ?? '')
      )
    );
  }, [COMPARABLE_STATUSES, selectedRowKeys, tasks]);

  const rowSelection = useMemo(
    () => ({
      selectedRowKeys,
      onChange: handleSelectionChange,
      preserveSelectedRowKeys: true,
      columnTitle: ' ',
      getCheckboxProps: (record: AgentTask) => ({
        disabled: !SELECTABLE_STATUSES.includes(
          record.status?.toLowerCase() ?? ''
        ),
      }),
    }),
    [SELECTABLE_STATUSES, handleSelectionChange, selectedRowKeys]
  );

  const handleDelete = (row: AgentTask) => {
    modal.confirm({
      title: t('pages.jobs.deleteConfirmTitle'),
      content: t('pages.jobs.deleteConfirmContent'),
      okText: t('pages.jobs.delete'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        await agentTaskApi.delete(row.id);
        message.success(t('pages.jobs.deleteSuccess'));
        await loadTasks();
      },
    });
  };

  const columns: ColumnsType<AgentTask> = useMemo(() => {
    const tableColumns: ColumnsType<AgentTask> = [
      {
        title: t('pages.jobs.taskId'),
        dataIndex: 'id',
        key: 'id',
        width: 220,
        ellipsis: { showTitle: false },
        render: (id: string) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={id} placement='topLeft'>
              <Text className='table-cell-text' ellipsis>
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
        width: 360,
        ellipsis: true,
        render: (value: string, row: AgentTask) => (
          <div className='table-cell-with-copy'>
            <Tooltip title={value} placement='top'>
              <span
                className='table-cell-text-inner table-cell-link'
                role='link'
                tabIndex={0}
                onClick={() =>
                  window.open(`/agent-results/${row.id}`, '_blank')
                }
                onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    window.open(`/agent-results/${row.id}`, '_blank');
                  }
                }}
              >
                {value}
              </span>
            </Tooltip>
            {canManageTask(row.created_by) && (
              <Button
                type='text'
                size='small'
                icon={<EditOutlined />}
                aria-label={t('pages.jobs.renameTitle')}
                onClick={() => {
                  setRenameTarget(row);
                  setRenameValue(row.name);
                }}
              />
            )}
          </div>
        ),
      },
      {
        title: t('pages.jobs.targetUrl'),
        dataIndex: 'target_url',
        width: 300,
        ellipsis: { showTitle: false },
        render: (value: string) => (
          <Tooltip title={value} placement='topLeft'>
            <Text ellipsis>{value}</Text>
          </Tooltip>
        ),
      },
      {
        title: t('pages.jobs.loadConfig'),
        width: 180,
        render: (_: unknown, row: AgentTask) => (
          <Space direction='vertical' size={0}>
            <Text>
              {t('pages.jobs.concurrentUsers')}: {row.concurrent_users}
            </Text>
            <Text>
              {t('pages.jobs.duration')}: {row.duration}
            </Text>
          </Space>
        ),
      },
      {
        title: t('pages.jobs.status'),
        dataIndex: 'status',
        width: 120,
        render: (value: string) => <StatusTag status={value} />,
      },
      ...(showCreator
        ? [
            {
              title: t('pages.jobs.createdBy'),
              dataIndex: 'created_by',
              width: 140,
            },
          ]
        : []),
      {
        title: t('pages.jobs.createdTime'),
        dataIndex: 'created_at',
        width: 200,
        sorter: (a: AgentTask, b: AgentTask) =>
          getTimestamp(a.created_at) - getTimestamp(b.created_at),
        render: (value: string) => formatDate(value),
      },
      {
        title: t('pages.jobs.actions'),
        width: 140,
        render: (_: unknown, row: AgentTask) => {
          const menuItems = [
            {
              key: 'collection',
              icon: <FolderAddOutlined />,
              label: t('pages.jobs.addToCollection'),
              onClick: () => {
                setSingleAddTaskId(row.id);
                setCollectionModalOpen(true);
              },
            },
            {
              key: 'copy',
              icon: <CopyOutlined />,
              label: t('pages.jobs.copyTemplate'),
              onClick: () => handleCopy(row),
            },
            ...(canManageTask(row.created_by) && ACTIVE_STATUSES.has(row.status)
              ? [
                  {
                    key: 'stop',
                    icon: <StopOutlined />,
                    label: t('pages.jobs.stop'),
                    danger: true,
                    onClick: () => handleStop(row),
                  },
                ]
              : canManageTask(row.created_by)
                ? [
                    {
                      key: 'delete',
                      icon: <DeleteOutlined />,
                      label: t('pages.jobs.delete'),
                      danger: true,
                      onClick: () => handleDelete(row),
                    },
                  ]
                : []),
          ];
          return (
            <Space size={4}>
              <Tooltip title={t('pages.jobs.results')}>
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<LineChartOutlined />}
                  onClick={() =>
                    window.open(`/agent-results/${row.id}`, '_blank')
                  }
                />
              </Tooltip>
              <Tooltip title={t('pages.jobs.logs')}>
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<FileTextOutlined />}
                  onClick={() => window.open(`/logs/task/${row.id}`, '_blank')}
                />
              </Tooltip>
              {!ACTIVE_STATUSES.has(row.status) && (
                <Tooltip title={t('pages.jobs.rerun')}>
                  <Button
                    type='text'
                    size='small'
                    className='action-icon-btn'
                    icon={<PlayCircleOutlined />}
                    onClick={() => handleRerun(row)}
                  />
                </Tooltip>
              )}
              <Dropdown
                menu={{ items: menuItems }}
                trigger={['click']}
                placement='bottomRight'
              >
                <Button
                  type='text'
                  size='small'
                  className='action-icon-btn'
                  icon={<MoreOutlined />}
                />
              </Dropdown>
            </Space>
          );
        },
      },
    ];

    return tableColumns;
  }, [
    canManageTask,
    handleCopy,
    handleDelete,
    handleRerun,
    handleStop,
    showCreator,
    t,
  ]);

  return (
    <div>
      <div className='jobs-toolbar'>
        <div className='jobs-toolbar-left'>
          {canCreate && (
            <Button
              type='primary'
              className='modern-button-primary'
              icon={<PlusOutlined />}
              onClick={openCreate}
            >
              {t('pages.jobs.createNew')}
            </Button>
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
              {selectedRowKeys.length >= 2 &&
                selectedRowKeys.length <= 5 &&
                allSelectedComparable && (
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
          <Search
            placeholder={t('pages.jobs.searchPlaceholderAgent')}
            value={searchInput}
            onChange={event => setSearchInput(event.target.value)}
            className='w-300 modern-search'
            allowClear
          />
          <Button
            className='modern-button'
            onClick={() => setSearchInput('')}
            disabled={!searchInput}
          >
            {t('common.reset')}
          </Button>
          <Tooltip title={t('pages.jobs.refresh')}>
            <Button
              type='text'
              className='modern-button'
              icon={<ReloadOutlined spin={loading} />}
              onClick={loadTasks}
              disabled={loading}
            />
          </Tooltip>
        </div>
      </div>
      <Table<AgentTask>
        rowKey='id'
        columns={columns}
        dataSource={filteredTasks}
        loading={loading}
        rowSelection={rowSelection}
        scroll={{ x: UI_CONFIG.TABLE_SCROLL_X }}
        className='modern-table unified-table'
        rowClassName={record =>
          record.status?.toLowerCase() === 'running'
            ? 'table-highlight-row'
            : ''
        }
      />

      <Modal
        title={
          taskToCopy
            ? t('pages.jobs.copyAgentTitle', {
                protocol: protocol.toUpperCase(),
              })
            : t('components.createAgentTaskForm.createTitle')
        }
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setTaskToCopy(null);
        }}
        width={900}
        destroyOnHidden
        maskClosable={false}
        footer={null}
      >
        <CreateAgentTaskForm
          key={`${protocol}-${taskToCopy ? 'copy' : 'create'}`}
          protocol={protocol}
          clusters={clusters}
          loading={submitting}
          onSubmit={handleCreate}
          onCancel={() => {
            setModalOpen(false);
            setTaskToCopy(null);
          }}
          initialData={taskToCopy}
        />
      </Modal>
      <AddToCollectionModal
        open={collectionModalOpen}
        onCancel={() => {
          setCollectionModalOpen(false);
          setSingleAddTaskId(null);
        }}
        taskIds={
          singleAddTaskId
            ? [singleAddTaskId]
            : selectedRowKeys.map(key => String(key))
        }
        taskType={protocol}
        onSuccess={() => {
          if (!singleAddTaskId) setSelectedRowKeys([]);
        }}
      />
      <Modal
        title={t('pages.jobs.renameTitle')}
        open={!!renameTarget}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
        confirmLoading={renaming}
        onOk={handleRename}
        onCancel={() => {
          setRenameTarget(null);
          setRenameValue('');
        }}
      >
        <Input
          value={renameValue}
          maxLength={100}
          onChange={event => setRenameValue(event.target.value)}
          onPressEnter={handleRename}
          placeholder={t('pages.jobs.renamePlaceholder')}
        />
      </Modal>
    </div>
  );
};

export default AgentJobs;
