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
import { Column } from '@ant-design/plots';
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
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import html2canvas from 'html2canvas';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
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

const TASK_COLORS = [
  '#1890ff', // Blue
  '#52c41a', // Green
  '#fa8c16', // Orange
  '#eb2f96', // Pink
  '#722ed1', // Purple
  '#13c2c2', // Cyan
  '#f5222d', // Red
  '#a0d911', // Lime
  '#fa541c', // Dark Orange
  '#2f54eb', // Dark Blue
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
  p90_response_time: number;
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
  | 'p90_response_time'
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
  const [comparisonMode, setComparisonMode] = useState<ComparisonMode>(() => {
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

  const getModelColor = (modelName: string) => {
    // Assign colors based on the actual order of data appearance to maintain consistency with data display order
    const allTasks =
      comparisonMode === 'model'
        ? [
            ...availableTasks,
            ...selectedTasks,
            ...comparisonResults.map(result => ({
              model_name: result.model_name,
              created_at: '', // No need for specific time, only model name is needed
            })),
          ]
        : [];

    // Get unique model names in order of appearance, without alphabetical sorting
    const uniqueModelsList: string[] = [];
    allTasks.forEach(task => {
      if (!uniqueModelsList.includes(task.model_name)) {
        uniqueModelsList.push(task.model_name);
      }
    });

    const index =
      uniqueModelsList.length > 0 ? uniqueModelsList.indexOf(modelName) : 0;
    return TASK_COLORS[index % TASK_COLORS.length];
  };

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
            width: 60,
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
            width: 200,
            ellipsis: true,
            render: (model: string) => (
              <Tooltip title={model} placement='topLeft'>
                <Tag
                  color={getModelColor(model)}
                  style={{
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {model}
                </Tag>
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
          title: t('pages.resultComparison.select'),
          key: 'select',
          width: 60,
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

  // Helper function to wrap text for x-axis labels
  const wrapTaskName = (text: string, maxCharsPerLine: number = 18) => {
    if (text.length <= maxCharsPerLine) {
      return text;
    }

    const lines: string[] = [];
    let currentLine = '';

    // split text by characters
    const chars = text.split('');

    chars.forEach((char, index) => {
      if (currentLine.length >= maxCharsPerLine) {
        // check if we can break the line at the separator
        if (char === ' ' || char === '-' || char === '_') {
          lines.push(currentLine);
          currentLine = char === ' ' ? '' : char;
        } else if (
          currentLine.length === maxCharsPerLine ||
          index === chars.length - 1
        ) {
          lines.push(currentLine);
          currentLine = char;
        } else {
          currentLine += char;
        }
      } else {
        currentLine += char;
      }
    });

    if (currentLine) {
      lines.push(currentLine);
    }

    // Limit to max 2 lines with ellipsis
    if (lines.length > 2) {
      return `${lines.slice(0, 2).join('\n')}...`;
    }

    return lines.join('\n');
  };

  // Generate unique display label for x-axis when task names are duplicated
  const generateUniqueLabel = (
    taskName: string,
    taskId: string,
    index: number,
    allResults: typeof activeComparisonResults
  ) => {
    // Check if there are duplicate task names
    const duplicateCount = allResults.filter(
      r => r.task_name === taskName
    ).length;

    if (duplicateCount > 1) {
      // Add short task ID suffix to differentiate
      const shortId = taskId.slice(0, 6);
      return `${wrapTaskName(taskName)}\n(${shortId})`;
    }

    return wrapTaskName(taskName);
  };

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

  // Chart configurations
  const createChartConfig = ({
    metricKey,
    chartTitle,
    decimals = 2,
    unit,
  }: MetricCardConfig | CommonMetricCardConfig) => {
    // Use unique key combining task_id to prevent stacking of same-named tasks
    const data = activeComparisonResults.map((result, index) => ({
      // Use unique identifier for x-axis to prevent stacking
      taskKey: `${result.task_id}`,
      // Display label with unique suffix for duplicate names
      task: generateUniqueLabel(
        result.task_name,
        result.task_id,
        index,
        activeComparisonResults
      ),
      rawTaskName: result.task_name,
      value: Number((result as any)[metricKey]) || 0,
      taskId: result.task_id,
      index,
    }));

    const showLabels = data.length <= 8;
    const slider =
      data.length > CHART_VISIBLE_COUNT
        ? {
            start: 0,
            end: Math.min(1, CHART_VISIBLE_COUNT / data.length),
          }
        : undefined;

    return {
      data,
      xField: 'taskKey', // Use unique taskKey instead of task name
      yField: 'value',
      colorField: 'taskId',
      height: 380,
      maxColumnWidth: 56,
      columnWidthRatio: 0.6,
      appendPadding: [28, 20, slider ? 72 : 56, 20],
      color: (datum: { taskId: string; index: number }) =>
        getTaskColor(datum.taskId) ||
        TASK_COLORS[datum.index % TASK_COLORS.length],
      columnStyle: {
        radius: [6, 6, 0, 0],
        fillOpacity: 0.95,
        shadowColor: 'rgba(0, 0, 0, 0.06)',
        shadowBlur: 4,
        shadowOffsetY: 2,
      },
      tooltip: {
        showMarkers: false,
        shared: true,
        domStyles: {
          'g2-tooltip': {
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.12)',
            padding: '12px 16px',
          },
        },
        formatter: (datum: any) => {
          const value = datum?.value ?? datum;
          return {
            name: datum?.rawTaskName || chartTitle,
            value: formatMetricValue(value, decimals, unit),
          };
        },
      },
      label: showLabels
        ? {
            position: 'top' as const,
            style: {
              fill: '#1a1a1a',
              fontSize: 12,
              fontWeight: 600,
              textShadow: '0 1px 2px rgba(255,255,255,0.8)',
            },
            formatter: (_value: any, datum: any) => {
              const val = datum?.value ?? _value ?? 0;
              return formatMetricValue(val, decimals, unit);
            },
          }
        : undefined,
      legend: false,
      meta: {
        value: {
          alias: chartTitle,
        },
        taskKey: {
          // Custom formatter to show task display name instead of taskKey
          formatter: (val: string) => {
            const item = data.find(d => d.taskKey === val);
            return item?.task || val;
          },
        },
      },
      xAxis: {
        label: {
          autoRotate: false,
          autoHide: false,
          autoEllipsis: false,
          formatter: (val: string) => {
            // Find the corresponding task data and return display label
            const item = data.find(d => d.taskKey === val);
            return item?.task || val;
          },
          style: {
            fontSize: 11,
            textAlign: 'center',
            lineHeight: 16,
            fill: '#595959',
            fontWeight: 500,
          },
        },
        line: {
          style: {
            stroke: '#e8e8e8',
            lineWidth: 1,
          },
        },
        tickLine: null,
      },
      yAxis: {
        nice: true,
        label: {
          formatter: (val: string) =>
            formatMetricValue(Number(val), decimals, unit),
          style: {
            fontSize: 11,
            fill: '#8c8c8c',
          },
        },
        grid: {
          line: {
            style: {
              stroke: '#f0f0f0',
              lineDash: [4, 4],
            },
          },
        },
        line: null,
      },
      interactions: [{ type: 'active-region' }, { type: 'element-active' }],
      slider: slider
        ? {
            ...slider,
            height: 24,
            trendCfg: {
              backgroundStyle: {
                fill: '#f5f5f5',
              },
            },
            backgroundStyle: {
              fill: '#f5f5f5',
            },
            foregroundStyle: {
              fill: 'rgba(0, 0, 0, 0.1)',
            },
            handlerStyle: {
              width: 20,
              height: 20,
              fill: '#fff',
              stroke: '#d9d9d9',
              radius: 10,
            },
          }
        : undefined,
      animation: {
        appear: {
          animation: 'scale-in-y',
          duration: 500,
          easing: 'ease-out',
        },
      },
      state: {
        active: {
          style: {
            fillOpacity: 1,
            shadowColor: 'rgba(0, 0, 0, 0.15)',
            shadowBlur: 10,
            stroke: 'rgba(255, 255, 255, 0.5)',
            lineWidth: 1,
          },
        },
      },
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
        metricKey: 'p90_response_time',
        title: t('pages.results.p90ResponseTime', 'P90 Response Time'),
        description: t(
          'pages.resultComparison.metricDescriptions.p90ResponseTime',
          '90th percentile response time (seconds)'
        ),
        chartTitle: t('pages.results.p90ResponseTime', 'P90 Response Time'),
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

      {/* Mode Switch */}
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
              <span style={{ fontSize: 18, fontWeight: 600 }}>
                {t('pages.resultComparison.modelTasks') ||
                  t('pages.jobs.llmTab') ||
                  'LLM Tasks Comparison'}
              </span>
            ),
          },
          {
            key: 'common',
            label: (
              <span style={{ fontSize: 18, fontWeight: 600 }}>
                {t('pages.resultComparison.commonTasks') ||
                  t('pages.jobs.commonApiTab') ||
                  'Common Tasks Comparison'}
              </span>
            ),
          },
        ]}
        className='modern-tabs'
      />

      {/* Model Info Section */}
      <div ref={modelInfoRef} className='mb-24'>
        <div className='section-header' style={{ borderBottom: 'none' }}>
          <span className='section-title'>
            {t('pages.resultComparison.taskInfo', 'Task Info')}
          </span>
          <Space>
            <Button
              type='default'
              icon={<RobotOutlined />}
              onClick={handleAnalyzeComparison}
              loading={isAnalyzing}
              disabled={comparisonMode !== 'model' || !hasSelectedTasks}
              style={{
                backgroundColor: '#52c41a',
                borderColor: '#52c41a',
                color: '#ffffff',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.backgroundColor = '#73d13d';
                e.currentTarget.style.borderColor = '#73d13d';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.backgroundColor = '#52c41a';
                e.currentTarget.style.borderColor = '#52c41a';
              }}
            >
              {t('pages.resultComparison.aiAnalysis')}
            </Button>
            <Button
              type='primary'
              icon={<DownloadOutlined />}
              onClick={handleDownloadComparison}
              loading={isDownloading}
              disabled={!hasComparisonResults}
            >
              {t('pages.resultComparison.download')}
            </Button>
            <Button
              type='primary'
              className='btn-warning'
              icon={<PlusOutlined />}
              onClick={handleModalOpen}
            >
              {t('pages.resultComparison.selectTask')}
            </Button>
            {hasSelectedTasks && (
              <Button
                type='primary'
                danger
                icon={<ClearOutlined />}
                onClick={clearAllTasks}
              >
                {t('pages.resultComparison.clearAll')}
              </Button>
            )}
          </Space>
        </div>

        <div className='section-content'>
          {activeSelectedTasks.length === 0 ? (
            <Empty
              description={t('pages.resultComparison.pleaseSelectTask')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
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
                  <Col span={12} key={config.metricKey}>
                    <div className='comparison-chart-wrapper'>
                      <div className='comparison-chart-title'>
                        {createCardTitle(config.title, config.description)}
                      </div>
                      <Column {...createChartConfig(config)} />
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
                  dataSource={filteredAvailableTasks}
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
