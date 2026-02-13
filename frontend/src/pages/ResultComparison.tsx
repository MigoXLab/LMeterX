/**
 * @file ResultComparison.tsx
 * @description Result comparison page
 * @author Charm
 * @copyright 2025
 * */
import {
  BarChartOutlined,
  ClearOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Checkbox,
  Col,
  Empty,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import html2canvas from 'html2canvas';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/apiClient';
import { analysisApi } from '../api/services';
import { CopyButton } from '../components/ui/CopyButton';
import { LoadingSpinner } from '../components/ui/LoadingState';
import MarkdownRenderer from '../components/ui/MarkdownRenderer';
import { PageHeader } from '../components/ui/PageHeader';
import { useLanguage } from '../contexts/LanguageContext';
import { createFileTimestamp, formatDate } from '../utils/date';

const { Text } = Typography;
const { Option } = Select;

// Macaron palette
const TASK_COLORS = [
  '#A8D8F8', // Sky Macaron (lighter)
  '#8EA9F5', // Soft Periwinkle
  '#D4BEF0', // Lilac Macaron (lighter)
  '#B38CD9', // Lavender Macaron
  '#9A95E0', // Rose Macaron
];

interface ModelTaskInfo {
  model_name: string;
  concurrent_users: number;
  task_id: string;
  task_name: string;
  created_at: string;
  duration?: number;
}

interface ComparisonMetrics {
  task_id: string;
  model_name: string;
  concurrent_users: number;
  task_name: string;
  duration: string;
  stream_mode: boolean;
  dataset_type: string;
  first_token_latency: number;
  total_time: number;
  total_tps: number;
  completion_tps: number;
  avg_total_tokens_per_req: number;
  avg_completion_tokens_per_req: number;
  rps: number;
}

interface SelectedTask {
  task_id: string;
  model_name: string;
  concurrent_users: number;
  task_name: string;
  created_at: string;
  duration?: number;
}

type ComparisonMode = 'model' | 'common';

const MODE_STORAGE_KEY = 'resultComparisonMode';

interface CommonTaskInfo {
  task_id: string;
  task_name: string;
  method: string;
  target_url: string;
  concurrent_users: number;
  created_at: string;
  duration?: number;
}

interface CommonComparisonMetrics {
  task_id: string;
  task_name: string;
  method: string;
  target_url: string;
  concurrent_users: number;
  duration: string;
  request_count: number;
  failure_count: number;
  success_rate: number;
  rps: number;
  avg_response_time: number;
  p95_response_time: number;
  min_response_time: number;
  max_response_time: number;
  avg_content_length: number;
}

interface SelectedCommonTask {
  task_id: string;
  task_name: string;
  method: string;
  target_url: string;
  concurrent_users: number;
  created_at: string;
  duration?: number;
}

type NumericMetricKey =
  | 'first_token_latency'
  | 'total_time'
  | 'total_tps'
  | 'completion_tps'
  | 'avg_total_tokens_per_req'
  | 'avg_completion_tokens_per_req'
  | 'rps';

interface MetricCardConfig {
  metricKey: NumericMetricKey;
  title: string;
  description: string;
  chartTitle: string;
  unit?: string;
  decimals?: number;
}

type CommonNumericMetricKey =
  | 'avg_response_time'
  | 'p95_response_time'
  | 'min_response_time'
  | 'max_response_time'
  | 'rps'
  | 'success_rate';

interface CommonMetricCardConfig {
  metricKey: CommonNumericMetricKey;
  title: string;
  description: string;
  chartTitle: string;
  unit?: string;
  decimals?: number;
}

const CHART_VISIBLE_COUNT = 6;

const ResultComparison: React.FC = () => {
  const { t } = useTranslation();
  const { currentLanguage } = useLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const [comparisonMode, setComparisonMode] = useState<ComparisonMode>(() => {
    const urlMode = searchParams.get('mode');
    if (urlMode === 'model' || urlMode === 'common') return urlMode;
    const stored = localStorage.getItem(MODE_STORAGE_KEY);
    return stored === 'common' ? 'common' : 'model';
  });
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [availableTasks, setAvailableTasks] = useState<ModelTaskInfo[]>([]);
  const [availableCommonTasks, setAvailableCommonTasks] = useState<
    CommonTaskInfo[]
  >([]);
  const [selectedTasks, setSelectedTasks] = useState<SelectedTask[]>([]);
  const [selectedCommonTasks, setSelectedCommonTasks] = useState<
    SelectedCommonTask[]
  >([]);
  const [comparisonResults, setComparisonResults] = useState<
    ComparisonMetrics[]
  >([]);
  const [commonComparisonResults, setCommonComparisonResults] = useState<
    CommonComparisonMetrics[]
  >([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [selectedModel, setSelectedModel] = useState<string | undefined>(
    undefined
  );
  const [tempSelectedTasks, setTempSelectedTasks] = useState<string[]>([]);
  const [messageApi, contextHolder] = message.useMessage();

  // AI Analysis states
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<string>('');
  const [isAnalysisModalVisible, setIsAnalysisModalVisible] = useState(false);
  const [isDownloadingAnalysis, setIsDownloadingAnalysis] = useState(false);

  // Refs for download functionality
  const modelInfoRef = useRef<HTMLDivElement | null>(null);
  const comparisonResultsRef = useRef<HTMLDivElement | null>(null);
  const analysisModalContentRef = useRef<HTMLDivElement | null>(null);

  // Ref for pending auto-compare from URL params
  const pendingCompareRef = useRef<{
    taskIds: string[];
    mode: ComparisonMode;
  } | null>(null);

  // Fetch available tasks for comparison
  const fetchAvailableTasks = useCallback(
    async (mode: ComparisonMode = comparisonMode) => {
      setLoading(true);
      try {
        if (mode === 'model') {
          const response = await api.get<{
            data: ModelTaskInfo[];
            status: string;
            error?: string;
          }>('/tasks/comparison/available');

          if (response.data.status === 'success') {
            setAvailableTasks(response.data.data);
          } else {
            messageApi.error(
              response.data.error ||
                t('pages.resultComparison.fetchAvailableTasksFailed')
            );
          }
        } else {
          const response = await api.get<{
            data: CommonTaskInfo[];
            status: string;
            error?: string;
          }>('/common-tasks/comparison/available');

          if (response.data.status === 'success') {
            setAvailableCommonTasks(response.data.data);
          } else {
            messageApi.error(
              response.data.error ||
                t('pages.resultComparison.fetchAvailableTasksFailed')
            );
          }
        }
      } catch (error) {
        messageApi.error(t('pages.resultComparison.fetchAvailableTasksError'));
      } finally {
        setLoading(false);
      }
    },
    [comparisonMode, messageApi, t]
  );

  // Compare selected tasks
  const compareResult = useCallback(async () => {
    if (tempSelectedTasks.length < 2) {
      messageApi.warning(t('pages.resultComparison.selectAtLeast2Tasks'));
      return;
    }

    if (tempSelectedTasks.length > 5) {
      messageApi.warning(t('pages.resultComparison.max5TasksAllowed'));
      return;
    }

    setComparing(true);
    try {
      if (comparisonMode === 'model') {
        const response = await api.post<{
          data: ComparisonMetrics[];
          status: string;
          error?: string;
        }>('/tasks/comparison', {
          selected_tasks: tempSelectedTasks,
        });

        if (response.data.status === 'success') {
          setComparisonResults(response.data.data);

          const selectedTasksData = availableTasks
            .filter(task => tempSelectedTasks.includes(task.task_id))
            .map(task => ({
              task_id: task.task_id,
              model_name: task.model_name,
              concurrent_users: task.concurrent_users,
              task_name: task.task_name,
              created_at: task.created_at,
              duration: task.duration,
            }));

          setSelectedTasks(selectedTasksData);
          setIsModalVisible(false);
          setTempSelectedTasks([]);
          messageApi.success(t('pages.resultComparison.comparisonCompleted'));
        } else {
          messageApi.error(
            response.data.error ||
              t('pages.resultComparison.compareResultFailed')
          );
        }
      } else {
        const response = await api.post<{
          data: CommonComparisonMetrics[];
          status: string;
          error?: string;
        }>('/common-tasks/comparison', {
          selected_tasks: tempSelectedTasks,
        });

        if (response.data.status === 'success') {
          setCommonComparisonResults(response.data.data);

          const selectedTasksData = availableCommonTasks
            .filter(task => tempSelectedTasks.includes(task.task_id))
            .map(task => ({
              task_id: task.task_id,
              task_name: task.task_name,
              method: task.method,
              target_url: task.target_url,
              concurrent_users: task.concurrent_users,
              created_at: task.created_at,
              duration: task.duration,
            }));

          setSelectedCommonTasks(selectedTasksData);
          setIsModalVisible(false);
          setTempSelectedTasks([]);
          messageApi.success(t('pages.resultComparison.comparisonCompleted'));
        } else {
          messageApi.error(
            response.data.error ||
              t('pages.resultComparison.compareResultFailed')
          );
        }
      }
    } catch (error) {
      messageApi.error(t('pages.resultComparison.compareResultError'));
    } finally {
      setComparing(false);
    }
  }, [
    tempSelectedTasks,
    availableTasks,
    availableCommonTasks,
    comparisonMode,
    messageApi,
    t,
  ]);

  /**
   * Compare directly with provided task IDs (used for auto-compare from URL params)
   */
  const compareDirectly = useCallback(
    async (taskIds: string[], mode: ComparisonMode) => {
      if (taskIds.length < 2 || taskIds.length > 5) return;

      setComparing(true);
      try {
        if (mode === 'model') {
          const response = await api.post<{
            data: ComparisonMetrics[];
            status: string;
            error?: string;
          }>('/tasks/comparison', {
            selected_tasks: taskIds,
          });

          if (response.data.status === 'success') {
            setComparisonResults(response.data.data);

            const selectedTasksData = availableTasks
              .filter(task => taskIds.includes(task.task_id))
              .map(task => ({
                task_id: task.task_id,
                model_name: task.model_name,
                concurrent_users: task.concurrent_users,
                task_name: task.task_name,
                created_at: task.created_at,
                duration: task.duration,
              }));

            setSelectedTasks(selectedTasksData);
            messageApi.success(t('pages.resultComparison.comparisonCompleted'));
          } else {
            messageApi.error(
              response.data.error ||
                t('pages.resultComparison.compareResultFailed')
            );
          }
        } else {
          const response = await api.post<{
            data: CommonComparisonMetrics[];
            status: string;
            error?: string;
          }>('/common-tasks/comparison', {
            selected_tasks: taskIds,
          });

          if (response.data.status === 'success') {
            setCommonComparisonResults(response.data.data);

            const selectedTasksData = availableCommonTasks
              .filter(task => taskIds.includes(task.task_id))
              .map(task => ({
                task_id: task.task_id,
                task_name: task.task_name,
                method: task.method,
                target_url: task.target_url,
                concurrent_users: task.concurrent_users,
                created_at: task.created_at,
                duration: task.duration,
              }));

            setSelectedCommonTasks(selectedTasksData);
            messageApi.success(t('pages.resultComparison.comparisonCompleted'));
          } else {
            messageApi.error(
              response.data.error ||
                t('pages.resultComparison.compareResultFailed')
            );
          }
        }
      } catch (error) {
        messageApi.error(t('pages.resultComparison.compareResultError'));
      } finally {
        setComparing(false);
      }
    },
    [availableTasks, availableCommonTasks, messageApi, t]
  );

  // Read URL params on mount and set pending compare
  useEffect(() => {
    const tasksParam = searchParams.get('tasks');
    const modeParam = searchParams.get('mode');
    if (tasksParam) {
      const taskIds = tasksParam.split(',').filter(Boolean);
      if (taskIds.length >= 2 && taskIds.length <= 5) {
        const mode: ComparisonMode =
          modeParam === 'model' || modeParam === 'common' ? modeParam : 'model';
        pendingCompareRef.current = { taskIds, mode };
        setComparisonMode(mode);
      }
      // Clear URL params
      setSearchParams({}, { replace: true });
    }
  }, []);

  // Auto-compare when available tasks are loaded and there's a pending compare
  useEffect(() => {
    const pending = pendingCompareRef.current;
    if (!pending) return;

    if (pending.mode === 'model' && availableTasks.length > 0) {
      pendingCompareRef.current = null;
      compareDirectly(pending.taskIds, pending.mode);
    } else if (pending.mode === 'common' && availableCommonTasks.length > 0) {
      pendingCompareRef.current = null;
      compareDirectly(pending.taskIds, pending.mode);
    }
  }, [availableTasks, availableCommonTasks, compareDirectly]);

  // Handle task selection in modal
  const handleTaskSelection = (taskId: string, checked: boolean) => {
    if (checked) {
      if (tempSelectedTasks.length >= 5) {
        messageApi.warning(t('pages.resultComparison.max5TasksAllowed'));
        return;
      }
      setTempSelectedTasks([...tempSelectedTasks, taskId]);
    } else {
      setTempSelectedTasks(tempSelectedTasks.filter(id => id !== taskId));
    }
  };

  // Handle search input change
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  // Handle search clear or search action
  const handleSearch = (value: string) => {
    if (!value.trim()) {
      // When search is cleared, refresh the available tasks
      fetchAvailableTasks(comparisonMode);
    }
  };

  // Handle model filter change
  const handleModelFilterChange = (value: string) => {
    if (comparisonMode !== 'model') return;
    setSelectedModel(value || undefined);
    if (!value) {
      // When model filter is cleared, refresh the available tasks
      fetchAvailableTasks('model');
    }
  };

  // Clear all selected tasks
  const clearAllTasks = () => {
    Modal.confirm({
      title: t('pages.resultComparison.clearAllTasks'),
      icon: <ExclamationCircleOutlined />,
      content: t('pages.resultComparison.clearAllTasksConfirm'),
      onOk: () => {
        if (comparisonMode === 'model') {
          setSelectedTasks([]);
          setComparisonResults([]);
        } else {
          setSelectedCommonTasks([]);
          setCommonComparisonResults([]);
        }
        messageApi.success(t('pages.resultComparison.allTasksCleared'));
      },
    });
  };

  // Reset modal state when opening
  const handleModalOpen = () => {
    const activeIds =
      comparisonMode === 'model'
        ? selectedTasks.map(task => task.task_id)
        : selectedCommonTasks.map(task => task.task_id);
    setTempSelectedTasks(activeIds);
    setIsModalVisible(true);
  };

  // Filter available tasks
  const filteredAvailableTasks = useMemo(() => {
    if (comparisonMode === 'model') {
      return availableTasks.filter(task => {
        const matchesSearch =
          searchText === '' ||
          task.model_name.toLowerCase().includes(searchText.toLowerCase()) ||
          task.task_name.toLowerCase().includes(searchText.toLowerCase());

        const matchesModel =
          !selectedModel || task.model_name === selectedModel;

        return matchesSearch && matchesModel;
      });
    }

    return availableCommonTasks.filter(task => {
      const matchesSearch =
        searchText === '' ||
        task.task_name.toLowerCase().includes(searchText.toLowerCase()) ||
        task.target_url.toLowerCase().includes(searchText.toLowerCase()) ||
        task.method.toLowerCase().includes(searchText.toLowerCase());

      return matchesSearch;
    });
  }, [
    availableCommonTasks,
    availableTasks,
    comparisonMode,
    searchText,
    selectedModel,
  ]);

  const sortedAvailableTasks = useMemo(() => {
    const tasks = [...filteredAvailableTasks];
    tasks.sort((a, b) => {
      const timeA = new Date(a.created_at).getTime();
      const timeB = new Date(b.created_at).getTime();
      return timeB - timeA;
    });
    return tasks;
  }, [filteredAvailableTasks]);

  // Get unique model names for filtering
  const uniqueModels = useMemo(() => {
    if (comparisonMode !== 'model') return [];
    const models = [...new Set(availableTasks.map(task => task.model_name))];
    return models.sort();
  }, [availableTasks, comparisonMode]);

  const activeSelectedTasks =
    comparisonMode === 'model' ? selectedTasks : selectedCommonTasks;
  const activeComparisonResults =
    comparisonMode === 'model' ? comparisonResults : commonComparisonResults;

  const taskColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    activeComparisonResults.forEach((result, index) => {
      map[result.task_id] = TASK_COLORS[index % TASK_COLORS.length];
    });
    return map;
  }, [activeComparisonResults]);

  // Get color for task by task_id
  const getTaskColor = (taskId: string) => {
    return taskColorMap[taskId] || TASK_COLORS[0];
  };

  // Table columns for available tasks in modal
  const availableTasksColumns: ColumnsType<ModelTaskInfo | CommonTaskInfo> =
    useMemo(() => {
      if (comparisonMode === 'model') {
        return [
          {
            title: t('pages.resultComparison.select'),
            key: 'select',
            width: 56,
            align: 'center',
            render: (_, record: ModelTaskInfo) => (
              <Checkbox
                checked={tempSelectedTasks.includes(record.task_id)}
                onChange={e =>
                  handleTaskSelection(record.task_id, e.target.checked)
                }
              />
            ),
          },
          {
            title: t('pages.resultComparison.taskId'),
            dataIndex: 'task_id',
            key: 'task_id',
            ellipsis: true,
          },
          {
            title: t('pages.resultComparison.taskName'),
            dataIndex: 'task_name',
            key: 'task_name',
            ellipsis: true,
          },
          {
            title: t('pages.resultComparison.modelName'),
            dataIndex: 'model_name',
            key: 'model_name',
            width: 160,
            ellipsis: true,
            render: (model: string) => (
              <Tooltip title={model} placement='topLeft'>
                <span
                  style={{
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'inline-block',
                  }}
                >
                  {model}
                </span>
              </Tooltip>
            ),
          },
          {
            title: t('pages.resultComparison.concurrentUsers'),
            dataIndex: 'concurrent_users',
            key: 'concurrent_users',
            width: 90,
            align: 'center',
          },
          {
            title: t('pages.resultComparison.testDuration'),
            dataIndex: 'duration',
            key: 'duration',
            width: 100,
            align: 'center',
            render: (duration: number) => `${duration || 0}s`,
          },
        ];
      }

      return [
        {
          title: t('pages.resultComparison.select'),
          key: 'select',
          width: 56,
          align: 'center',
          render: (_, record: CommonTaskInfo) => (
            <Checkbox
              checked={tempSelectedTasks.includes(record.task_id)}
              onChange={e =>
                handleTaskSelection(record.task_id, e.target.checked)
              }
            />
          ),
        },
        {
          title: t('pages.resultComparison.taskId'),
          dataIndex: 'task_id',
          key: 'task_id',
          ellipsis: true,
        },
        {
          title: t('pages.resultComparison.taskName'),
          dataIndex: 'task_name',
          key: 'task_name',
          ellipsis: true,
        },
        {
          title: t('pages.resultComparison.concurrentUsers'),
          dataIndex: 'concurrent_users',
          key: 'concurrent_users',
          width: 90,
          align: 'center',
        },
        {
          title: t('pages.resultComparison.testDuration'),
          dataIndex: 'duration',
          key: 'duration',
          width: 100,
          align: 'center',
          render: (duration: number) => `${duration || 0}s`,
        },
      ];
    }, [comparisonMode, t, tempSelectedTasks]);

  // Table columns for selected tasks
  const selectedTasksColumns: ColumnsType<SelectedTask | SelectedCommonTask> =
    useMemo(() => {
      if (comparisonMode === 'model') {
        return [
          {
            title: t('pages.resultComparison.taskId'),
            dataIndex: 'task_id',
            key: 'task_id',
            ellipsis: true,
          },
          {
            title: t('pages.resultComparison.taskName'),
            dataIndex: 'task_name',
            key: 'task_name',
            ellipsis: true,
          },
          {
            title: t('pages.resultComparison.modelName'),
            dataIndex: 'model_name',
            key: 'model_name',
            width: 200,
            ellipsis: true,
            render: (model: string) => (
              <Tooltip title={model} placement='topLeft'>
                <span
                  style={{
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'inline-block',
                  }}
                >
                  {model}
                </span>
              </Tooltip>
            ),
          },
          {
            title: t('pages.resultComparison.concurrentUsers'),
            dataIndex: 'concurrent_users',
            key: 'concurrent_users',
            align: 'center',
          },
          {
            title: t('pages.resultComparison.testDuration'),
            dataIndex: 'duration',
            key: 'duration',
            align: 'center',
            render: (duration: number) => `${duration || 0}s`,
          },
          {
            title: t('pages.resultComparison.createdTime'),
            dataIndex: 'created_at',
            key: 'created_at',
            render: (date: string) => formatDate(date),
          },
        ];
      }

      return [
        {
          title: t('pages.resultComparison.taskId'),
          dataIndex: 'task_id',
          key: 'task_id',
          ellipsis: true,
        },
        {
          title: t('pages.resultComparison.taskName'),
          dataIndex: 'task_name',
          key: 'task_name',
          ellipsis: true,
        },
        {
          title: t('pages.resultComparison.targetUrl', 'Target URL'),
          dataIndex: 'target_url',
          key: 'target_url',
          ellipsis: true,
          render: (url: string) => (
            <Tooltip title={url} placement='topLeft'>
              <span>{url}</span>
            </Tooltip>
          ),
        },
        {
          title: t('pages.resultComparison.concurrentUsers'),
          dataIndex: 'concurrent_users',
          key: 'concurrent_users',
          align: 'center',
        },
        {
          title: t('pages.resultComparison.testDuration'),
          dataIndex: 'duration',
          key: 'duration',
          align: 'center',
          render: (duration: number) => `${duration || 0}s`,
        },
        {
          title: t('pages.resultComparison.createdTime'),
          dataIndex: 'created_at',
          key: 'created_at',
          render: (date: string) => formatDate(date),
        },
      ];
    }, [comparisonMode, t]);

  const formatMetricValue = (
    value: number | string,
    decimals: number = 2,
    unit?: string
  ) => {
    if (value === null || value === undefined || value === '') {
      return '-';
    }

    const numericValue =
      typeof value === 'number' ? value : Number.parseFloat(value);

    if (Number.isNaN(numericValue)) {
      return '-';
    }

    const fixed =
      Math.abs(numericValue) >= 1000
        ? numericValue.toFixed(0)
        : numericValue.toFixed(decimals);

    return unit ? `${fixed}${unit}` : fixed;
  };

  // Truncate long names for x-axis labels
  const truncateName = (name: string, maxLen: number = 14) => {
    if (name.length <= maxLen) return name;
    return `${name.slice(0, maxLen)}…`;
  };

  // Determine whether to use horizontal bar chart (when > 3 tasks)
  const useHorizontalBar = activeComparisonResults.length > 3;

  // Calculate dynamic chart height for horizontal bar charts
  const getChartHeight = () => {
    if (!useHorizontalBar) return 380;
    const count = activeComparisonResults.length;
    // Each bar takes ~60px, plus padding
    return Math.max(300, count * 60 + 80);
  };

  // Metrics that should display integers on axis
  const integerAxisMetrics = new Set([
    'total_tps',
    'completion_tps',
    'avg_total_tokens_per_req',
    'avg_completion_tokens_per_req',
  ]);

  // ECharts chart configuration
  const createEChartsOption = ({
    metricKey,
    chartTitle,
    decimals = 2,
    unit,
  }: MetricCardConfig | CommonMetricCardConfig) => {
    const data = activeComparisonResults.map((result, index) => {
      const rawName =
        result.task_name?.trim() ||
        ('model_name' in result ? (result as any).model_name : '') ||
        result.task_id;
      return {
        fullName: rawName,
        value: Number((result as any)[metricKey]) || 0,
        color: getTaskColor(result.task_id),
        taskId: result.task_id,
        index,
      };
    });

    const isHorizontal = data.length > 3;

    // Axis labels: no unit, and use integers for specific metrics
    const axisDecimals = integerAxisMetrics.has(metricKey) ? 0 : decimals;

    // Dynamic category gap based on number of bars
    const categoryGap =
      data.length <= 2
        ? '65%'
        : data.length <= 3
          ? '55%'
          : data.length <= 4
            ? '45%'
            : '35%';

    // DataZoom for scrolling when many items
    const needsZoom = data.length > CHART_VISIBLE_COUNT;
    const dataZoomConfig = needsZoom
      ? [
          {
            type: 'slider' as const,
            show: true,
            yAxisIndex: isHorizontal ? 0 : undefined,
            xAxisIndex: isHorizontal ? undefined : 0,
            start: 0,
            end: Math.round((CHART_VISIBLE_COUNT / data.length) * 100),
            ...(isHorizontal
              ? { width: 22, right: 4 }
              : { height: 22, bottom: 4 }),
            borderColor: 'rgba(102, 126, 234, 0.12)',
            fillerColor: 'rgba(102, 126, 234, 0.08)',
            backgroundColor: 'rgba(102, 126, 234, 0.03)',
            handleStyle: {
              color: '#fff',
              borderColor: 'rgba(102, 126, 234, 0.35)',
              borderWidth: 1,
            },
            textStyle: {
              color: '#8c8ea6',
              fontSize: 11,
            },
            dataBackground: {
              lineStyle: { color: 'rgba(102, 126, 234, 0.15)' },
              areaStyle: { color: 'rgba(102, 126, 234, 0.05)' },
            },
          },
        ]
      : undefined;

    // Tooltip (shared between both orientations)
    const tooltip = {
      trigger: 'axis' as const,
      axisPointer: {
        type: 'shadow' as const,
        shadowStyle: {
          color: 'rgba(102, 126, 234, 0.04)',
        },
      },
      backgroundColor: '#fff',
      borderColor: 'rgba(102, 126, 234, 0.15)',
      borderWidth: 1,
      padding: [12, 16],
      confine: true,
      textStyle: {
        color: '#333',
        fontSize: 13,
      },
      extraCssText: 'max-width:320px;white-space:normal;',
      formatter: (params: any) => {
        const items = Array.isArray(params) ? params : [params];
        const item = items[0];
        if (!item) return '';
        const dataItem = data[item.dataIndex];
        if (!dataItem) return '';
        const colorDot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${dataItem.color};margin-right:6px;vertical-align:middle;"></span>`;
        const displayName =
          dataItem.fullName.length > 40
            ? `${dataItem.fullName.slice(0, 40)}…`
            : dataItem.fullName;
        return `<div style="font-weight:600;margin-bottom:6px;font-size:13px;color:#282e58;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:288px;" title="${dataItem.fullName}">${displayName}</div>
            <div style="display:flex;align-items:center">${colorDot}<span style="color:#545983">${chartTitle}:</span><b style="color:#282e58;margin-left:6px">${formatMetricValue(item.value, decimals, unit)}</b></div>`;
      },
    };

    // Horizontal bar chart (data.length > 3)
    if (isHorizontal) {
      // Reverse data so that the first item appears at the top
      const reversedData = [...data].reverse();

      return {
        grid: {
          left: 16,
          right: needsZoom ? 48 : 60,
          top: 16,
          bottom: 12,
          containLabel: true,
        },
        tooltip,
        xAxis: {
          type: 'value' as const,
          axisLabel: {
            formatter: (val: number) => formatMetricValue(val, axisDecimals),
            color: '#8c8ea6',
            fontSize: 11,
          },
          splitLine: {
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.06)',
              type: 'dashed' as const,
            },
          },
          axisLine: { show: false },
          axisTick: { show: false },
        },
        yAxis: {
          type: 'category' as const,
          data: reversedData.map(d => d.fullName),
          axisLabel: {
            formatter: (val: string) => truncateName(val, 18),
            color: '#545983',
            fontSize: 11,
            fontWeight: 500,
          },
          axisLine: {
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.15)',
            },
          },
          axisTick: { show: false },
        },
        dataZoom: dataZoomConfig,
        series: [
          {
            type: 'bar' as const,
            data: reversedData.map(d => ({
              value: d.value,
              itemStyle: {
                color: {
                  type: 'linear' as const,
                  x: 0,
                  y: 0,
                  x2: 1,
                  y2: 0,
                  colorStops: [
                    { offset: 0, color: `${d.color}CC` },
                    { offset: 1, color: d.color },
                  ],
                },
                borderRadius: [0, 6, 6, 0],
              },
            })),
            barMaxWidth: 36,
            barCategoryGap: categoryGap,
            label: {
              show: data.length <= 8,
              position: 'right' as const,
              formatter: (params: any) =>
                formatMetricValue(params.value, decimals, unit),
              color: '#4a4a6a',
              fontSize: 12,
              fontWeight: 600,
            },
            emphasis: {
              itemStyle: {
                shadowBlur: 12,
                shadowColor: 'rgba(102, 126, 234, 0.25)',
                shadowOffsetX: 2,
              },
            },
          },
        ],
        animation: true,
        animationDuration: 600,
        animationEasing: 'cubicOut',
      };
    }

    // Vertical bar chart (data.length <= 3)
    return {
      grid: {
        left: 16,
        right: 16,
        top: 36,
        bottom: needsZoom ? 56 : 12,
        containLabel: true,
      },
      tooltip,
      xAxis: {
        type: 'category' as const,
        data: data.map(d => d.fullName),
        axisLabel: {
          formatter: (val: string) => truncateName(val),
          color: '#545983',
          fontSize: 11,
          fontWeight: 500,
          interval: 0,
        },
        axisLine: {
          lineStyle: {
            color: 'rgba(102, 126, 234, 0.15)',
          },
        },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value' as const,
        axisLabel: {
          formatter: (val: number) => formatMetricValue(val, axisDecimals),
          color: '#8c8ea6',
          fontSize: 11,
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(102, 126, 234, 0.06)',
            type: 'dashed' as const,
          },
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      dataZoom: dataZoomConfig,
      series: [
        {
          type: 'bar' as const,
          data: data.map(d => ({
            value: d.value,
            itemStyle: {
              color: {
                type: 'linear' as const,
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: d.color },
                  { offset: 1, color: `${d.color}CC` },
                ],
              },
              borderRadius: [6, 6, 0, 0],
            },
          })),
          barMaxWidth: 52,
          barCategoryGap: categoryGap,
          label: {
            show: data.length <= 8,
            position: 'top' as const,
            formatter: (params: any) =>
              formatMetricValue(params.value, decimals, unit),
            color: '#4a4a6a',
            fontSize: 12,
            fontWeight: 600,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 12,
              shadowColor: 'rgba(102, 126, 234, 0.25)',
              shadowOffsetY: 2,
            },
          },
        },
      ],
      animation: true,
      animationDuration: 600,
      animationEasing: 'cubicOut',
    };
  };

  const metricCardConfigs = useMemo<MetricCardConfig[]>(
    () => [
      {
        metricKey: 'first_token_latency',
        title: t('pages.resultComparison.timeToFirstToken'),
        description: t('pages.resultComparison.metricDescriptions.ttft'),
        chartTitle: t('pages.resultComparison.chartTitles.ttft'),
        unit: 's',
        decimals: 3,
      },
      {
        metricKey: 'total_time',
        title: t('pages.resultComparison.totalTime'),
        description: t('pages.resultComparison.metricDescriptions.totalTime'),
        chartTitle: t('pages.resultComparison.chartTitles.totalTime'),
        unit: 's',
        decimals: 3,
      },
      {
        metricKey: 'total_tps',
        title: t('pages.resultComparison.totalTokensPerSecond'),
        description: t('pages.resultComparison.metricDescriptions.totalTps'),
        chartTitle: t('pages.resultComparison.chartTitles.totalTps'),
        unit: ' tokens/s',
        decimals: 2,
      },
      {
        metricKey: 'completion_tps',
        title: t('pages.resultComparison.completionTokensPerSecond'),
        description: t(
          'pages.resultComparison.metricDescriptions.completionTps'
        ),
        chartTitle: t('pages.resultComparison.chartTitles.completionTps'),
        unit: ' tokens/s',
        decimals: 2,
      },
      {
        metricKey: 'avg_total_tokens_per_req',
        title: t('pages.resultComparison.averageTotalTokensPerRequest'),
        description: t('pages.resultComparison.metricDescriptions.avgTotalTpr'),
        chartTitle: t('pages.resultComparison.chartTitles.avgTotalTpr'),
        unit: ' tokens/req',
        decimals: 2,
      },
      {
        metricKey: 'avg_completion_tokens_per_req',
        title: t('pages.resultComparison.averageCompletionTokensPerRequest'),
        description: t(
          'pages.resultComparison.metricDescriptions.avgCompletionTpr'
        ),
        chartTitle: t('pages.resultComparison.chartTitles.avgCompletionTpr'),
        unit: ' tokens/req',
        decimals: 2,
      },
      {
        metricKey: 'rps',
        title: t('pages.resultComparison.requestsPerSecond'),
        description: t('pages.resultComparison.metricDescriptions.rps'),
        chartTitle: t('pages.resultComparison.chartTitles.rps'),
        unit: ' req/s',
        decimals: 2,
      },
    ],
    [t]
  );

  const commonMetricCardConfigs = useMemo<CommonMetricCardConfig[]>(
    () => [
      {
        metricKey: 'avg_response_time',
        title: t('pages.results.avgResponseTime', 'Avg Response Time'),
        description: t(
          'pages.resultComparison.metricDescriptions.avgResponseTime',
          'Average response time (seconds)'
        ),
        chartTitle: t('pages.results.avgResponseTime', 'Avg Response Time'),
        unit: 's',
        decimals: 3,
      },
      {
        metricKey: 'p95_response_time',
        title: t('pages.results.p95ResponseTime', 'P95 Response Time'),
        description: t(
          'pages.resultComparison.metricDescriptions.p95ResponseTime',
          '95th percentile response time (seconds)'
        ),
        chartTitle: t('pages.results.p95ResponseTime', 'P95 Response Time'),
        unit: 's',
        decimals: 3,
      },
      {
        metricKey: 'min_response_time',
        title: t('pages.results.minResponseTime', 'Min Response Time'),
        description: t(
          'pages.resultComparison.metricDescriptions.minResponseTime',
          'Minimum response time (seconds)'
        ),
        chartTitle: t('pages.results.minResponseTime', 'Min Response Time'),
        unit: 's',
        decimals: 3,
      },
      {
        metricKey: 'max_response_time',
        title: t('pages.results.maxResponseTime', 'Max Response Time'),
        description: t(
          'pages.resultComparison.metricDescriptions.maxResponseTime',
          'Maximum response time (seconds)'
        ),
        chartTitle: t('pages.results.maxResponseTime', 'Max Response Time'),
        unit: 's',
        decimals: 3,
      },
      {
        metricKey: 'rps',
        title: t('pages.results.rps', 'Requests Per Second'),
        description: t(
          'pages.resultComparison.metricDescriptions.rpsCommon',
          'Requests per second'
        ),
        chartTitle: t('pages.results.rps', 'Requests Per Second'),
        unit: ' req/s',
        decimals: 2,
      },
      {
        metricKey: 'success_rate',
        title: t('pages.results.successRate', 'Success Rate'),
        description: t(
          'pages.resultComparison.metricDescriptions.successRate',
          'Percentage of successful requests'
        ),
        chartTitle: t('pages.results.successRate', 'Success Rate'),
        unit: '%',
        decimals: 2,
      },
    ],
    [t]
  );

  const metricHasData = useCallback(
    (metricKey: NumericMetricKey | CommonNumericMetricKey) =>
      activeComparisonResults.some(result => {
        const value = (result as any)[metricKey];
        if (value === null || value === undefined) {
          return false;
        }
        const numericValue = Number(value);
        return Number.isFinite(numericValue) && numericValue !== 0;
      }),
    [activeComparisonResults]
  );

  const visibleMetricCardConfigs = useMemo(() => {
    const configs =
      comparisonMode === 'model' ? metricCardConfigs : commonMetricCardConfigs;
    return configs.filter(config => metricHasData(config.metricKey));
  }, [
    commonMetricCardConfigs,
    comparisonMode,
    metricCardConfigs,
    metricHasData,
  ]);

  // Helper function to create card title with tooltip
  const createCardTitle = (title: string, description: string) => (
    <Space>
      <span>{title}</span>
      <Tooltip title={description} placement='topRight'>
        <InfoCircleOutlined style={{ color: '#666', cursor: 'help' }} />
      </Tooltip>
    </Space>
  );

  const hasSelectedTasks = activeSelectedTasks.length > 0;
  const hasComparisonResults = activeComparisonResults.length > 0;

  // Function to download analysis result as image
  const handleDownloadAnalysis = async () => {
    if (!analysisModalContentRef.current) {
      messageApi.error(
        t('pages.resultComparison.analysisDownloadFailed', {
          error: t('pages.resultComparison.comparisonComponentsNotLoaded'),
        })
      );
      return;
    }

    setIsDownloadingAnalysis(true);
    messageApi.loading({
      content: t('pages.resultComparison.generatingComparisonReport'),
      key: 'downloadAnalysis',
      duration: 0,
    });

    try {
      const canvas = await html2canvas(analysisModalContentRef.current, {
        useCORS: true,
        scale: 2,
        backgroundColor: '#ffffff',
        width: analysisModalContentRef.current.scrollWidth,
        height: analysisModalContentRef.current.scrollHeight,
      } as any);

      // Convert canvas to image and download
      const image = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = image;
      link.download = `ai-analysis-comparison-${createFileTimestamp()}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      messageApi.success({
        content: t('pages.resultComparison.analysisDownloadSuccessful'),
        key: 'downloadAnalysis',
        duration: 3,
      });
    } catch (err: any) {
      messageApi.error({
        content: t('pages.resultComparison.analysisDownloadFailed', {
          error: err.message || t('pages.resultComparison.unknownError'),
        }),
        key: 'downloadAnalysis',
        duration: 4,
      });
    } finally {
      setIsDownloadingAnalysis(false);
    }
  };

  // Function to handle comparison results download
  // Handle AI analysis for comparison results
  const handleAnalyzeComparison = async () => {
    if (comparisonMode !== 'model') {
      messageApi.warning(
        t(
          'pages.resultComparison.analysisOnlyModel',
          'AI analysis is available for model tasks only'
        )
      );
      return;
    }

    if (selectedTasks.length < 1) {
      messageApi.warning(
        t('pages.resultComparison.selectAtLeast1TaskForAnalysis')
      );
      return;
    }

    if (selectedTasks.length > 5) {
      messageApi.warning(
        t('pages.resultComparison.max5TasksAllowedForAnalysis')
      );
      return;
    }

    setIsAnalyzing(true);
    try {
      const taskIds = selectedTasks.map(task => task.task_id);
      const response = await analysisApi.analyzeTasks(taskIds, currentLanguage);

      if (response.data.status === 'completed') {
        setAnalysisResult(response.data.analysis_report);
        setIsAnalysisModalVisible(true);
        messageApi.success(t('pages.resultComparison.analysisCompleted'));
      } else {
        messageApi.error(
          response.data.error_message ||
            t('pages.resultComparison.analysisFailed')
        );
      }
    } catch (error: any) {
      // Handle different types of errors
      let errorMessage = t('pages.resultComparison.analysisError');

      // Check for timeout errors specifically
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorMessage =
          t('pages.resultComparison.analysisTimeout') ||
          'AI analysis timeout, please try again later';
      } else if (error.data) {
        // API error response - prioritize error_message over error
        if (error.data.error_message) {
          errorMessage = error.data.error_message;
        } else if (error.data.error) {
          errorMessage = error.data.error;
        } else if (error.data.detail) {
          errorMessage = error.data.detail;
        }
      } else if (error.message) {
        // Network or other error
        errorMessage = error.message;
      }

      messageApi.error(errorMessage);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDownloadComparison = async () => {
    if (!modelInfoRef.current || !comparisonResultsRef.current) {
      messageApi.error(
        t('pages.resultComparison.comparisonComponentsNotLoaded')
      );
      return;
    }

    setIsDownloading(true);
    messageApi.loading({
      content: t('pages.resultComparison.generatingComparisonReport'),
      key: 'downloadComparison',
      duration: 0,
    });

    try {
      const elementsToCapture = [
        { ref: modelInfoRef, title: t('pages.resultComparison.taskInfo') },
        {
          ref: comparisonResultsRef,
          title: t('pages.resultComparison.comparisonResults'),
        },
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
        throw new Error(
          t('pages.resultComparison.unableToCaptureComparisonContent')
        );
      }

      // Calculate the total height and maximum width of the merged Canvas
      const padding = 30;
      let totalHeight = 0;
      let maxWidth = 0;

      validCanvases.forEach(canvas => {
        totalHeight += canvas.height;
        if (canvas.width > maxWidth) {
          maxWidth = canvas.width;
        }
      });
      if (validCanvases.length > 0) {
        totalHeight += (validCanvases.length - 1) * padding;
      }

      // Create a new Canvas for merging
      const mergedCanvas = document.createElement('canvas');
      mergedCanvas.width = maxWidth;
      mergedCanvas.height = totalHeight;
      const ctx = mergedCanvas.getContext('2d');

      if (!ctx) {
        throw new Error(
          t('pages.resultComparison.unableToCreateCanvasContext')
        );
      }

      // Set the background color of the merged image
      ctx.fillStyle = 'white';
      ctx.fillRect(0, 0, mergedCanvas.width, mergedCanvas.height);

      let currentY = 0;
      for (let i = 0; i < validCanvases.length; i++) {
        const canvas = validCanvases[i];
        const offsetX = (mergedCanvas.width - canvas.width) / 2;
        ctx.drawImage(canvas, offsetX > 0 ? offsetX : 0, currentY);
        currentY += canvas.height;

        if (i < validCanvases.length - 1) {
          currentY += padding;
        }
      }

      // Convert merged Canvas to image and download
      const image = mergedCanvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = image;
      link.download = `model-comparison-${createFileTimestamp()}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      messageApi.success({
        content: t('pages.resultComparison.downloadSuccessful'),
        key: 'downloadComparison',
        duration: 3,
      });
    } catch (err: any) {
      messageApi.error({
        content: t('pages.resultComparison.downloadFailed', {
          error: err.message || t('pages.resultComparison.unknownError'),
        }),
        key: 'downloadComparison',
        duration: 4,
      });
    } finally {
      setIsDownloading(false);
    }
  };

  useEffect(() => {
    fetchAvailableTasks('model');
    fetchAvailableTasks('common');
  }, [fetchAvailableTasks]);

  return (
    <div className='page-container'>
      {contextHolder}

      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.resultComparison.title')}
          description={t('pages.resultComparison.description')}
          icon={<BarChartOutlined />}
        />
      </div>

      {/* Mode Switch + Action Buttons */}
      <Tabs
        activeKey={comparisonMode}
        onChange={key => {
          setComparisonMode(key as ComparisonMode);
          setTempSelectedTasks([]);
          localStorage.setItem(MODE_STORAGE_KEY, key as ComparisonMode);
        }}
        items={[
          {
            key: 'model',
            label: (
              <span className='tab-label'>
                {t('pages.resultComparison.modelTasks') ||
                  t('pages.jobs.llmTab') ||
                  'LLM Tasks Comparison'}
              </span>
            ),
          },
          {
            key: 'common',
            label: (
              <span className='tab-label'>
                {t('pages.resultComparison.commonTasks') ||
                  t('pages.jobs.commonApiTab') ||
                  'Common Tasks Comparison'}
              </span>
            ),
          },
        ]}
        className='unified-tabs'
        tabBarExtraContent={
          hasSelectedTasks ? (
            <Space size={8}>
              <Button
                icon={<RobotOutlined />}
                onClick={handleAnalyzeComparison}
                loading={isAnalyzing}
                disabled={comparisonMode !== 'model'}
                className='modern-button-ai-summary'
              >
                {t('pages.resultComparison.aiAnalysis')}
              </Button>
              <Button
                type='primary'
                icon={<DownloadOutlined />}
                onClick={handleDownloadComparison}
                loading={isDownloading}
                disabled={!hasComparisonResults}
                className='modern-button-primary-light'
              >
                {t('pages.resultComparison.download')}
              </Button>
              <Button
                type='primary'
                icon={<PlusOutlined />}
                onClick={handleModalOpen}
              >
                {t('pages.resultComparison.selectTask')}
              </Button>
              <Button
                icon={<ClearOutlined />}
                onClick={clearAllTasks}
                style={{
                  color: '#8c8ea6',
                  borderColor: 'rgba(140, 142, 166, 0.35)',
                }}
              >
                {t('pages.resultComparison.clearAll')}
              </Button>
            </Space>
          ) : undefined
        }
      />

      {/* Model Info Section */}
      <div ref={modelInfoRef} className='mb-24'>
        {hasSelectedTasks && (
          <div className='section-header' style={{ borderBottom: 'none' }}>
            <span className='section-title'>
              {t('pages.resultComparison.taskInfo', 'Task Info')}
            </span>
          </div>
        )}

        <div className='section-content'>
          {activeSelectedTasks.length === 0 ? (
            <Empty
              description={t('pages.resultComparison.pleaseSelectTask')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button
                type='primary'
                icon={<PlusOutlined />}
                onClick={handleModalOpen}
                size='large'
              >
                {t('pages.resultComparison.selectTask')}
              </Button>
            </Empty>
          ) : (
            <Table
              columns={selectedTasksColumns}
              dataSource={activeSelectedTasks}
              rowKey='task_id'
              pagination={false}
              size='small'
            />
          )}
        </div>
      </div>

      {/* Comparison Results */}
      {hasComparisonResults && (
        <div ref={comparisonResultsRef}>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.resultComparison.comparisonResults')}
            </span>
          </div>

          <div className='section-content'>
            {visibleMetricCardConfigs.length > 0 ? (
              <Row gutter={[24, 24]}>
                {visibleMetricCardConfigs.map(config => (
                  <Col
                    xs={24}
                    md={12}
                    lg={8}
                    xl={visibleMetricCardConfigs.length <= 6 ? 8 : 6}
                    key={config.metricKey}
                  >
                    <div className='comparison-chart-wrapper'>
                      <div className='comparison-chart-title'>
                        {createCardTitle(config.title, config.description)}
                      </div>
                      <ReactECharts
                        option={createEChartsOption(config)}
                        style={{ height: getChartHeight() }}
                        notMerge
                      />
                    </div>
                  </Col>
                ))}
              </Row>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('pages.resultComparison.noMetricData')}
              />
            )}
          </div>
        </div>
      )}

      {/* Select Model/Common Modal */}
      <Modal
        title={t('pages.resultComparison.selectTasks', 'Select Tasks')}
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          setTempSelectedTasks([]);
        }}
        width={1000}
        footer={
          <div className='flex justify-between align-center'>
            <Text type='secondary'>
              {t('pages.resultComparison.tasksSelected', {
                count: tempSelectedTasks.length,
              })}
            </Text>
            <Space>
              <Button
                onClick={() => {
                  setIsModalVisible(false);
                  setTempSelectedTasks([]);
                }}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type='primary'
                icon={<SwapOutlined />}
                loading={comparing}
                disabled={tempSelectedTasks.length < 2}
                onClick={compareResult}
              >
                {t('pages.resultComparison.compareResult')}
              </Button>
            </Space>
          </div>
        }
      >
        <div className='mb-16'>
          <Space>
            <Input.Search
              placeholder={t('pages.resultComparison.searchTaskOrModel')}
              value={searchText}
              onChange={handleSearchChange}
              onSearch={handleSearch}
              allowClear
              className='w-300'
            />
            {comparisonMode === 'model' && (
              <Select
                placeholder={t('pages.resultComparison.filterModel')}
                value={selectedModel}
                onChange={handleModelFilterChange}
                className='w-200'
                allowClear
              >
                {uniqueModels.map(model => (
                  <Option key={model} value={model}>
                    {model}
                  </Option>
                ))}
              </Select>
            )}
            <Button
              icon={<ReloadOutlined />}
              onClick={() => fetchAvailableTasks(comparisonMode)}
              loading={loading}
            >
              {t('common.refresh')}
            </Button>
          </Space>
        </div>

        {loading ? (
          <div className='text-center p-24'>
            <LoadingSpinner size='large' />
          </div>
        ) : (
          <div>
            {filteredAvailableTasks.length === 0 ? (
              <Empty
                description={t('pages.resultComparison.noAvailableTasks')}
              />
            ) : (
              <div>
                <Alert
                  description={t(
                    'pages.resultComparison.selectTasksForComparison'
                  )}
                  type='info'
                  showIcon
                  className='mb-16'
                />
                <Table
                  columns={availableTasksColumns}
                  dataSource={sortedAvailableTasks}
                  rowKey='task_id'
                  pagination={{ pageSize: 10 }}
                  size='small'
                />
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* AI Analysis Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <RobotOutlined style={{ color: '#10b981' }} />
            {t('pages.resultComparison.aiAnalysisResults')}
          </div>
        }
        open={isAnalysisModalVisible}
        onCancel={() => setIsAnalysisModalVisible(false)}
        width={1200}
        style={{ maxWidth: '95vw' }}
        maskClosable={false}
        closable
        footer={[
          <Button
            key='download'
            type='primary'
            icon={<DownloadOutlined />}
            onClick={handleDownloadAnalysis}
            loading={isDownloadingAnalysis}
            disabled={!analysisResult}
          >
            {t('pages.resultComparison.downloadAnalysis')}
          </Button>,
          <Button key='close' onClick={() => setIsAnalysisModalVisible(false)}>
            {t('common.close')}
          </Button>,
        ]}
      >
        <div style={{ maxHeight: '70vh', overflow: 'auto' }}>
          {analysisResult ? (
            <div ref={analysisModalContentRef} style={{ position: 'relative' }}>
              <div
                style={{
                  position: 'absolute',
                  top: '8px',
                  right: '8px',
                  zIndex: 1,
                  backgroundColor: 'rgba(255, 255, 255, 0.9)',
                  borderRadius: '4px',
                  padding: '4px',
                }}
              >
                <CopyButton
                  text={analysisResult}
                  successMessage={t('pages.resultComparison.analysisCopied')}
                  tooltip={t('pages.resultComparison.copyAnalysis')}
                />
              </div>
              <div style={{ paddingRight: '50px', paddingTop: '8px' }}>
                <MarkdownRenderer
                  content={analysisResult}
                  className='analysis-content'
                />
              </div>
            </div>
          ) : (
            <Empty description={t('pages.resultComparison.noAnalysisResult')} />
          )}
        </div>
      </Modal>
    </div>
  );
};

export default ResultComparison;
