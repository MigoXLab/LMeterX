import {
  BugOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  InfoCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Row,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';

import { agentTaskApi, uploadDatasetFile } from '@/api/services';
import RequestHeadersEditor from '@/components/RequestHeadersEditor';
import TaskDatasetFields, {
  TaskDatasetSource,
} from '@/components/TaskDatasetFields';
import { useI18n } from '@/hooks/useI18n';
import { AgentTask, AgentTaskPayload, Cluster } from '@/types/job';
import { copyToClipboard } from '@/utils/clipboard';
import { INHERITED_SECRET_PLACEHOLDER } from '@/utils/requestHeaders';

const { TextArea } = Input;
const { Text } = Typography;
const SYSTEM_CONTENT_TYPE_HEADER = {
  key: 'Content-Type',
  value: 'application/json',
  fixed: true,
};
const MANAGED_AGENT_HEADERS = new Set([
  'accept',
  'content-type',
  'a2a-version',
  'mcp-protocol-version',
  'mcp-method',
  'mcp-name',
  'mcp-session-id',
  'traceparent',
  'x-lmeterx-run-id',
  'x-lmeterx-request-id',
]);

interface CreateAgentTaskFormProps {
  protocol: 'a2a' | 'mcp';
  clusters: Cluster[];
  loading: boolean;
  onSubmit: (payload: AgentTaskPayload) => Promise<boolean>;
  onCancel: () => void;
  initialData?: Partial<AgentTask> | null;
}

const CreateAgentTaskForm: React.FC<CreateAgentTaskFormProps> = ({
  protocol,
  clusters,
  loading,
  onSubmit,
  onCancel,
  initialData,
}) => {
  const { message } = App.useApp();
  const { t } = useI18n();
  const [form] = Form.useForm();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [testResultOpen, setTestResultOpen] = useState(false);
  const [scenarioModalOpen, setScenarioModalOpen] = useState(false);
  const [editingScenario, setEditingScenario] = useState<number | null>(null);
  const [scenarioCases, setScenarioCases] = useState<
    Array<Record<string, any>>
  >([]);
  const [scenarioForm] = Form.useForm();
  const [datasetUploading, setDatasetUploading] = useState(false);
  const [datasetFileName, setDatasetFileName] = useState('');
  const [tempTaskId, setTempTaskId] = useState(`temp-${Date.now()}`);
  const datasetSource =
    (Form.useWatch('dataset_source', form) as TaskDatasetSource | undefined) ||
    'none';
  const inheritSourceDataset = Boolean(
    Form.useWatch('inherit_source_dataset', form)
  );

  const initialValues = useMemo(
    () => ({
      name: '',
      protocol,
      target_url: '',
      protocol_version: protocol === 'a2a' ? '1.0' : '2026-07-28',
      agent_card_url: '',
      a2a_tenant: '',
      a2a_mode: 'async_poll',
      headers: [{ ...SYSTEM_CONTENT_TYPE_HEADER }],
      dataset_source: 'none',
      dataset_file: '',
      dataset_id: undefined,
      copy_source_task_id: undefined,
      inherit_source_headers: false,
      inherit_source_dataset: false,
      cascade_paths: '',
      token_count_path: '',
      concurrent_users: 1,
      spawn_rate: 1,
      duration: 60,
      request_timeout: 30,
      poll_interval: 1,
      task_timeout: 300,
      cluster_id: 'local',
    }),
    [protocol]
  );

  useEffect(() => {
    if (!initialData) return;
    const customHeaders = Array.isArray(initialData.headers)
      ? initialData.headers
          .filter(item => item.key.toLowerCase() !== 'content-type')
          .map(item => ({
            key: item.key,
            value: item.configured
              ? INHERITED_SECRET_PLACEHOLDER
              : (item.value ?? ''),
            fixed: false,
          }))
      : [];
    form.setFieldsValue({
      ...initialData,
      headers: [{ ...SYSTEM_CONTENT_TYPE_HEADER }, ...customHeaders],
      cascade_paths: (initialData.cascade_count_paths || []).join('\n'),
      copy_source_task_id: initialData.copy_source_task_id,
      inherit_source_headers: initialData.inherit_source_headers || false,
      inherit_source_dataset: initialData.inherit_source_dataset || false,
      dataset_source: initialData.dataset_id
        ? 'managed'
        : initialData.dataset_file ||
            initialData.dataset_configured ||
            initialData.inherit_source_dataset
          ? 'upload'
          : 'none',
    });
    const cases =
      protocol === 'a2a' ? initialData.a2a_scenarios : initialData.mcp_calls;
    setScenarioCases((cases || []).map(item => ({ ...item })));
    if (initialData.dataset_file || initialData.dataset_file_name) {
      setDatasetFileName(
        initialData.dataset_file_name ||
          initialData.dataset_file?.split('/').pop() ||
          'dataset.jsonl'
      );
    }
  }, [form, initialData, protocol]);

  const labelWithTooltip = (label: React.ReactNode, tooltip: string) => (
    <span>
      {label}
      <Tooltip title={tooltip}>
        <InfoCircleOutlined style={{ marginLeft: 5 }} />
      </Tooltip>
    </span>
  );

  const buildPayload = (values: any): AgentTaskPayload => {
    const inheritedKeys = new Set(
      (initialData?.redacted_header_keys || []).map(key => key.toLowerCase())
    );
    const submittedHeaders = (values.headers || []).flatMap((header: any) => {
      const key = String(header?.key || '').trim();
      if (header?.fixed || key.toLowerCase() === 'content-type') return [];
      if (!key) {
        throw new Error(t('components.createJobForm.headerNameRequired'));
      }
      const value = String(header?.value || '');
      const normalized = value.trim();
      if (
        inheritedKeys.has(key.toLowerCase()) &&
        (!normalized || normalized === INHERITED_SECRET_PLACEHOLDER)
      ) {
        return [];
      }
      if (!normalized) {
        throw new Error(
          t('components.createAgentTaskForm.headerValueRequired', {
            header: key,
          })
        );
      }
      return [{ key, value }];
    });
    if (scenarioCases.length === 0) {
      throw new Error(t('components.createAgentTaskForm.testCasesRequired'));
    }
    return {
      name: values.name.trim(),
      protocol,
      target_url: values.target_url.trim(),
      protocol_version: values.protocol_version.trim(),
      headers: submittedHeaders,
      duration: values.duration,
      concurrent_users: values.concurrent_users,
      spawn_rate: values.spawn_rate,
      request_timeout: values.request_timeout,
      cluster_id: values.cluster_id || 'local',
      dataset_file:
        values.dataset_source === 'upload'
          ? values.dataset_file || undefined
          : undefined,
      dataset_id:
        values.dataset_source === 'managed'
          ? values.dataset_id || undefined
          : undefined,
      copy_source_task_id: values.copy_source_task_id || undefined,
      inherit_source_headers: Boolean(values.inherit_source_headers),
      inherit_source_dataset:
        values.dataset_source === 'upload' &&
        Boolean(values.inherit_source_dataset),
      ...(protocol === 'a2a'
        ? {
            a2a_mode: values.a2a_mode,
            agent_card_url: values.agent_card_url?.trim() || undefined,
            a2a_tenant: values.a2a_tenant || undefined,
            poll_interval: values.poll_interval,
            task_timeout: values.task_timeout,
            a2a_scenarios: scenarioCases,
            cascade_count_paths: String(values.cascade_paths || '')
              .split('\n')
              .map((item: string) => item.trim())
              .filter(Boolean),
          }
        : {
            mcp_calls: scenarioCases,
            token_count_path: values.token_count_path?.trim() || undefined,
          }),
    };
  };

  const validatePayload = async () => {
    const values = await form.validateFields();
    return buildPayload(values);
  };

  const handleCreate = async () => {
    try {
      const payload = await validatePayload();
      if (await onSubmit(payload)) {
        form.resetFields();
        setScenarioCases([]);
        setDatasetFileName('');
        setTempTaskId(`temp-${Date.now()}`);
      }
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(
        error?.message || t('components.createAgentTaskForm.createFailed')
      );
    }
  };

  const openScenarioEditor = (index: number | null = null) => {
    const current = index === null ? null : scenarioCases[index];
    setEditingScenario(index);
    scenarioForm.setFieldsValue({
      id:
        current?.id ||
        `${protocol === 'a2a' ? 'scenario' : 'tool'}-${scenarioCases.length + 1}`,
      name: current?.name || '',
      weight: current?.weight || 1,
      message_json: JSON.stringify(
        current?.message || { role: 'ROLE_USER', parts: [{ text: '' }] },
        null,
        2
      ),
      tool_name: current?.tool_name || '',
      arguments_json: JSON.stringify(current?.arguments || {}, null, 2),
    });
    setScenarioModalOpen(true);
  };

  const saveScenario = async () => {
    try {
      const values = await scenarioForm.validateFields();
      const id = values.id.trim();
      if (
        scenarioCases.some(
          (item, index) => item.id === id && index !== editingScenario
        )
      ) {
        throw new Error(
          t('components.createAgentTaskForm.scenarioIdDuplicate')
        );
      }
      let scenario: Record<string, any>;
      if (protocol === 'a2a') {
        let messageValue: unknown;
        try {
          messageValue = JSON.parse(values.message_json);
        } catch {
          throw new Error(
            t('components.createAgentTaskForm.invalidA2aMessage')
          );
        }
        if (
          !messageValue ||
          typeof messageValue !== 'object' ||
          !Array.isArray((messageValue as any).parts) ||
          (messageValue as any).parts.length === 0
        ) {
          throw new Error(
            t('components.createAgentTaskForm.invalidA2aMessage')
          );
        }
        scenario = {
          id,
          name: values.name.trim(),
          weight: values.weight,
          message: messageValue,
        };
      } else {
        let argumentsValue: unknown;
        try {
          argumentsValue = JSON.parse(values.arguments_json || '{}');
        } catch {
          throw new Error(
            t('components.createAgentTaskForm.invalidMcpArguments')
          );
        }
        if (
          !argumentsValue ||
          typeof argumentsValue !== 'object' ||
          Array.isArray(argumentsValue)
        ) {
          throw new Error(
            t('components.createAgentTaskForm.invalidMcpArguments')
          );
        }
        scenario = {
          id,
          name: values.name.trim(),
          weight: values.weight,
          tool_name: values.tool_name.trim(),
          arguments: argumentsValue,
        };
      }
      setScenarioCases(current => {
        if (editingScenario === null) return [...current, scenario];
        return current.map((item, index) =>
          index === editingScenario ? scenario : item
        );
      });
      setScenarioModalOpen(false);
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message);
    }
  };

  const removeScenario = (index: number) => {
    setScenarioCases(current =>
      current.filter((_, itemIndex) => itemIndex !== index)
    );
  };

  const handleDatasetUpload = async (options: any) => {
    const { file, onError, onSuccess } = options;
    if (
      !String(file.name || '')
        .toLowerCase()
        .endsWith('.jsonl')
    ) {
      const error = new Error(t('components.createAgentTaskForm.jsonlOnly'));
      message.error(error.message);
      onError?.(error);
      return;
    }
    try {
      setDatasetUploading(true);
      const response = await uploadDatasetFile(file, tempTaskId);
      const datasetPath =
        (response as any)?.test_data ||
        (response as any)?.files?.[0]?.path ||
        (response as any)?.files?.[0]?.url;
      if (!datasetPath) {
        throw new Error(t('components.createAgentTaskForm.datasetPathMissing'));
      }
      form.setFieldsValue({
        dataset_source: 'upload',
        dataset_file: datasetPath,
        dataset_id: undefined,
        inherit_source_dataset: false,
      });
      setDatasetFileName(file.name);
      message.success(t('components.createAgentTaskForm.datasetUploadSuccess'));
      onSuccess?.(response, file);
    } catch (error: any) {
      message.error(
        error?.message ||
          t('components.createAgentTaskForm.datasetUploadFailed')
      );
      onError?.(error);
    } finally {
      setDatasetUploading(false);
    }
  };

  const handleDatasetRemove = () => {
    setDatasetFileName('');
    form.setFieldsValue({
      dataset_file: undefined,
      inherit_source_dataset: false,
    });
    return true;
  };

  const handleTest = async () => {
    let payload: AgentTaskPayload | undefined;
    try {
      payload = await validatePayload();
      setTesting(true);
      const response = await agentTaskApi.testConnection(payload);
      const body: any = response.data;
      setTestResult(body);
      setTestResultOpen(true);
      if (body?.status === 'error') {
        message.error(
          body?.error || t('components.createAgentTaskForm.connectionFailed')
        );
      } else if (payload.protocol === 'mcp') {
        message.success(
          t('components.createAgentTaskForm.mcpConnectionSuccess', {
            count: (body?.tools || []).length,
          })
        );
      } else {
        message.success(
          t('components.createAgentTaskForm.a2aConnectionSuccess', {
            name:
              body?.agent_card?.name ||
              t('components.createAgentTaskForm.agentCardVerified'),
          })
        );
      }
    } catch (error: any) {
      if (error?.errorFields) return;
      // apiClient rejects with { data, status, statusText }. Keep Axios's
      // native shape as a fallback for callers that bypass that wrapper.
      const errorData = error?.data ?? error?.response?.data;
      const detail = errorData?.detail;
      let detailText = '';
      if (Array.isArray(detail)) {
        detailText = detail
          .map((item: any) =>
            typeof item === 'string'
              ? item
              : item?.msg || item?.message || JSON.stringify(item)
          )
          .filter(Boolean)
          .join('; ');
      } else if (typeof detail === 'string') {
        detailText = detail;
      } else if (detail && typeof detail === 'object') {
        detailText = detail.message || detail.error || JSON.stringify(detail);
      }
      const errorMessage =
        errorData?.message ||
        errorData?.error ||
        detailText ||
        error?.message ||
        error?.statusText ||
        t('components.createAgentTaskForm.connectionFailed');
      message.error(errorMessage);
      setTestResult({
        status: 'error',
        protocol: payload?.protocol || protocol,
        error: errorMessage,
        error_type: errorData?.code || 'backend_request_error',
        service_status: error?.status ?? error?.response?.status,
        response: errorData
          ? {
              status_code: error?.status ?? error?.response?.status,
              data: errorData,
            }
          : null,
      });
      setTestResultOpen(true);
    } finally {
      setTesting(false);
    }
  };

  return (
    <>
      <Form form={form} layout='vertical' initialValues={initialValues}>
        <Row>
          <Col span={24}>
            <Form.Item
              name='name'
              label={t('components.createJobForm.taskName')}
              rules={[
                {
                  required: true,
                  message: t('components.createJobForm.pleaseEnterTaskName'),
                },
              ]}
            >
              <Input
                placeholder={
                  protocol === 'a2a'
                    ? t('components.createAgentTaskForm.a2aTaskNamePlaceholder')
                    : t('components.createAgentTaskForm.mcpTaskNamePlaceholder')
                }
              />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={16}>
            <Form.Item
              name='target_url'
              label={labelWithTooltip(
                t(
                  protocol === 'a2a'
                    ? 'components.createAgentTaskForm.a2aTargetUrl'
                    : 'components.createAgentTaskForm.mcpTargetUrl'
                ),
                t(
                  protocol === 'a2a'
                    ? 'components.createAgentTaskForm.a2aTargetUrlTooltip'
                    : 'components.createAgentTaskForm.mcpTargetUrlTooltip'
                )
              )}
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createAgentTaskForm.targetUrlRequired'
                  ),
                },
                {
                  type: 'url',
                  message: t('components.createJobForm.invalidUrlFormat'),
                },
              ]}
            >
              <Input
                placeholder={
                  protocol === 'a2a'
                    ? 'https://agent.example.com/a2a'
                    : 'https://mcp.example.com/mcp'
                }
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name='protocol_version'
              label={labelWithTooltip(
                t('components.createAgentTaskForm.protocolVersion'),
                t('components.createAgentTaskForm.protocolVersionTooltip')
              )}
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createAgentTaskForm.protocolVersionRequired'
                  ),
                },
              ]}
            >
              <Select
                options={
                  protocol === 'a2a'
                    ? [{ label: '1.0', value: '1.0' }]
                    : [
                        {
                          label: `2026-07-28 (${t(
                            'components.createAgentTaskForm.stateless'
                          )})`,
                          value: '2026-07-28',
                        },
                        {
                          label: `2025-11-25 (${t(
                            'components.createAgentTaskForm.compatible'
                          )})`,
                          value: '2025-11-25',
                        },
                      ]
                }
              />
            </Form.Item>
          </Col>
        </Row>
        {protocol === 'a2a' && (
          <>
            <Row gutter={16}>
              <Col span={16}>
                <Form.Item
                  name='agent_card_url'
                  label={labelWithTooltip(
                    t('components.createAgentTaskForm.agentCardUrl'),
                    t('components.createAgentTaskForm.agentCardUrlTooltip')
                  )}
                >
                  <Input
                    placeholder={t(
                      'components.createAgentTaskForm.agentCardUrlPlaceholder'
                    )}
                  />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name='a2a_mode'
                  label={labelWithTooltip(
                    t('components.createAgentTaskForm.executionMode'),
                    t('components.createAgentTaskForm.executionModeTooltip')
                  )}
                >
                  <Select
                    options={[
                      {
                        label: t('components.createAgentTaskForm.asyncPoll'),
                        value: 'async_poll',
                      },
                      {
                        label: t('components.createAgentTaskForm.streamSse'),
                        value: 'stream',
                      },
                      {
                        label: t('components.createAgentTaskForm.sync'),
                        value: 'sync',
                      },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name='a2a_tenant'
              label={labelWithTooltip(
                t('components.createAgentTaskForm.a2aTenant'),
                t('components.createAgentTaskForm.a2aTenantTooltip')
              )}
            >
              <Input
                placeholder={t(
                  'components.createAgentTaskForm.a2aTenantPlaceholder'
                )}
              />
            </Form.Item>
          </>
        )}
        <RequestHeadersEditor
          form={form}
          title={t('components.createAgentTaskForm.requestHeaders')}
          tooltip={t('components.createAgentTaskForm.requestHeadersTooltip')}
          redactedHeaderKeys={initialData?.redacted_header_keys}
          managedHeaderNames={MANAGED_AGENT_HEADERS}
          maxValueLength={4000}
        />
        <Form.Item
          required
          label={t(
            protocol === 'a2a'
              ? 'components.createAgentTaskForm.a2aScenarioWeights'
              : 'components.createAgentTaskForm.mcpScenarioWeights'
          )}
        >
          <List
            bordered
            locale={{
              emptyText: t('components.createAgentTaskForm.noScenarios'),
            }}
            dataSource={scenarioCases}
            renderItem={(item, index) => (
              <List.Item
                actions={[
                  <Button
                    key='edit'
                    type='text'
                    icon={<EditOutlined />}
                    aria-label={t(
                      'components.createAgentTaskForm.editScenario'
                    )}
                    onClick={() => openScenarioEditor(index)}
                  />,
                  <Button
                    key='delete'
                    type='text'
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={t(
                      'components.createAgentTaskForm.deleteScenario'
                    )}
                    onClick={() => removeScenario(index)}
                  />,
                ]}
              >
                <List.Item.Meta
                  title={item.name}
                  description={
                    <Space direction='vertical' size={0}>
                      <span>
                        {protocol === 'a2a'
                          ? `SendMessage · ${item.message?.parts?.length || 0} Part`
                          : `tools/call · ${item.tool_name}`}
                      </span>
                      <Text type='secondary' copyable={{ text: item.id }}>
                        scenario_id: {item.id}
                      </Text>
                    </Space>
                  }
                />
                <Text strong>
                  {t('components.createAgentTaskForm.weightValue', {
                    weight: item.weight || 1,
                  })}
                </Text>
              </List.Item>
            )}
          />
          <Button
            block
            style={{ marginTop: 8 }}
            icon={<PlusOutlined />}
            onClick={() => openScenarioEditor()}
          >
            {t(
              protocol === 'a2a'
                ? 'components.createAgentTaskForm.addA2aScenario'
                : 'components.createAgentTaskForm.addMcpScenario'
            )}
          </Button>
        </Form.Item>
        <Form.Item name='copy_source_task_id' hidden>
          <Input />
        </Form.Item>
        <Form.Item name='inherit_source_headers' hidden>
          <Input />
        </Form.Item>
        <Form.Item name='inherit_source_dataset' hidden>
          <Input />
        </Form.Item>
        <TaskDatasetFields
          source={datasetSource}
          sourceName='dataset_source'
          datasetType={protocol}
          uploadValueName='dataset_file'
          uploadValueRequired={!inheritSourceDataset}
          uploadFileName={datasetFileName}
          uploadLoading={datasetUploading}
          uploadTitle={t('components.createAgentTaskForm.uploadJsonlPrompt')}
          uploadHint={t(
            protocol === 'a2a'
              ? 'components.createAgentTaskForm.a2aJsonlHint'
              : 'components.createAgentTaskForm.mcpJsonlHint'
          )}
          showUploadRemoveIcon
          sourceTooltip={t(
            'components.createAgentTaskForm.protocolDatasetTooltip'
          )}
          onSourceChange={source => {
            setDatasetFileName('');
            form.setFieldsValue({
              dataset_id: undefined,
              dataset_file: undefined,
              inherit_source_dataset: false,
              dataset_source: source,
            });
          }}
          onUpload={handleDatasetUpload}
          onUploadRemove={handleDatasetRemove}
        />
        {protocol === 'a2a' ? (
          <>
            <Form.Item
              name='cascade_paths'
              label={labelWithTooltip(
                t('components.createAgentTaskForm.cascadePaths'),
                t('components.createAgentTaskForm.cascadePathsTooltip')
              )}
            >
              <TextArea
                rows={2}
                placeholder='result.task.metadata.metrics.mcpCallCount'
              />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name='poll_interval'
                  label={labelWithTooltip(
                    t('components.createAgentTaskForm.pollInterval'),
                    t('components.createAgentTaskForm.pollIntervalTooltip')
                  )}
                >
                  <InputNumber min={0.05} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name='task_timeout'
                  label={labelWithTooltip(
                    t('components.createAgentTaskForm.taskTimeout'),
                    t('components.createAgentTaskForm.taskTimeoutTooltip')
                  )}
                >
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
          </>
        ) : (
          <Form.Item
            name='token_count_path'
            label={labelWithTooltip(
              t('components.createAgentTaskForm.tokenCountPath'),
              t('components.createAgentTaskForm.tokenCountPathTooltip')
            )}
          >
            <Input placeholder='result.usage.outputTokens' />
          </Form.Item>
        )}
        <Row gutter={16}>
          <Col span={6}>
            <Form.Item
              name='concurrent_users'
              label={labelWithTooltip(
                t('components.createJobForm.concurrentUsers'),
                t('components.createJobForm.concurrentUsersTooltip')
              )}
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createJobForm.pleaseEnterConcurrentUsers'
                  ),
                },
              ]}
            >
              <InputNumber min={1} max={5000} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name='spawn_rate'
              label={labelWithTooltip(
                t('components.createJobForm.userSpawnRate'),
                t('components.createJobForm.userSpawnRateTooltip')
              )}
              rules={[
                {
                  required: true,
                  message: t('components.createJobForm.pleaseEnterSpawnRate'),
                },
              ]}
            >
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name='duration'
              label={labelWithTooltip(
                t('components.createJobForm.testDuration'),
                t('components.createJobForm.testDurationTooltip')
              )}
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createJobForm.pleaseEnterTestDuration'
                  ),
                },
              ]}
            >
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name='request_timeout'
              label={labelWithTooltip(
                t('components.createJobForm.requestTimeout'),
                t('components.createAgentTaskForm.requestTimeoutTooltip')
              )}
            >
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item
          name='cluster_id'
          label={labelWithTooltip(
            t('components.createJobForm.env'),
            t('components.createAgentTaskForm.envTooltip')
          )}
          rules={[
            {
              required: true,
              message: t('components.createJobForm.envRequired'),
            },
          ]}
        >
          <Select
            placeholder={t('components.createJobForm.envPlaceholder')}
            options={(clusters.length
              ? clusters
              : [{ id: 'local', name: 'Local' }]
            ).map(item => ({ label: item.name, value: item.id }))}
          />
        </Form.Item>
        <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
          <Space>
            <Button
              icon={<ExperimentOutlined />}
              loading={testing}
              onClick={handleTest}
            >
              {t('components.createAgentTaskForm.testConnection')}
            </Button>
            <Button onClick={onCancel}>
              {t('components.createAgentTaskForm.cancel')}
            </Button>
            <Button
              type='primary'
              className='modern-button-primary'
              loading={loading}
              onClick={handleCreate}
            >
              {t('components.createAgentTaskForm.create')}
            </Button>
          </Space>
        </Form.Item>
      </Form>
      <Drawer
        title={
          <Space>
            <BugOutlined />
            <span>{t('components.createAgentTaskForm.apiTestTitle')}</span>
          </Space>
        }
        open={testResultOpen}
        onClose={() => setTestResultOpen(false)}
        width={560}
        destroyOnClose
        className='api-test-drawer'
      >
        {testResult && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
            }}
          >
            <Descriptions column={1} bordered size='small'>
              <Descriptions.Item
                label={t('components.createAgentTaskForm.testResultStatus')}
              >
                <Tag
                  color={testResult.status === 'success' ? 'green' : 'red'}
                  style={{ fontSize: 14, padding: '2px 12px' }}
                >
                  {t(
                    testResult.status === 'success'
                      ? 'components.createAgentTaskForm.testSucceeded'
                      : 'components.createAgentTaskForm.testFailed'
                  )}
                </Tag>
              </Descriptions.Item>
              {testResult.protocol && (
                <Descriptions.Item label='Protocol'>
                  {String(testResult.protocol).toUpperCase()}
                </Descriptions.Item>
              )}
              {testResult.http_status !== undefined && (
                <Descriptions.Item
                  label={t('components.createAgentTaskForm.targetStatusCode')}
                >
                  <Tag
                    color={
                      testResult.http_status >= 200 &&
                      testResult.http_status < 300
                        ? 'green'
                        : 'red'
                    }
                  >
                    {testResult.http_status}
                  </Tag>
                </Descriptions.Item>
              )}
              {testResult.service_status !== undefined && (
                <Descriptions.Item
                  label={t('components.createAgentTaskForm.serviceStatusCode')}
                >
                  <Tag color='red'>{testResult.service_status}</Tag>
                </Descriptions.Item>
              )}
              {testResult.operation && (
                <Descriptions.Item
                  label={t('components.createAgentTaskForm.testOperation')}
                >
                  {testResult.operation}
                </Descriptions.Item>
              )}
              {testResult.elapsed_ms !== undefined && (
                <Descriptions.Item
                  label={t('components.createAgentTaskForm.elapsedTime')}
                >
                  {testResult.elapsed_ms} ms
                </Descriptions.Item>
              )}
              {testResult.error_type && (
                <Descriptions.Item
                  label={t('components.createAgentTaskForm.errorType')}
                >
                  {testResult.error_type}
                </Descriptions.Item>
              )}
            </Descriptions>
            {testResult.status === 'error' && testResult.error && (
              <Alert
                type='error'
                message={testResult.error}
                style={{ marginTop: 12 }}
              />
            )}
            {(testResult.response?.data !== undefined ||
              testResult.status === 'success') && (
              <div
                style={{
                  marginTop: 12,
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 4,
                  }}
                >
                  <Text type='secondary'>
                    {t('components.createAgentTaskForm.responseDetails')}
                  </Text>
                  <Button
                    type='text'
                    size='small'
                    icon={<CopyOutlined />}
                    onClick={() => {
                      const responseData =
                        testResult.response?.data ??
                        (testResult.protocol === 'mcp'
                          ? {
                              server: testResult.server,
                              protocol_version: testResult.protocol_version,
                              capabilities: testResult.capabilities,
                              tools: testResult.tools,
                            }
                          : { agent_card: testResult.agent_card });
                      const textToCopy =
                        typeof responseData === 'string'
                          ? responseData
                          : JSON.stringify(responseData, null, 2);
                      copyToClipboard(
                        textToCopy,
                        t('common.copySuccess'),
                        t('common.copyFailed')
                      );
                    }}
                  >
                    {t('common.copy')}
                  </Button>
                </div>
                <TextArea
                  readOnly
                  value={(() => {
                    const responseData =
                      testResult.response?.data ??
                      (testResult.protocol === 'mcp'
                        ? {
                            server: testResult.server,
                            protocol_version: testResult.protocol_version,
                            capabilities: testResult.capabilities,
                            tools: testResult.tools,
                          }
                        : { agent_card: testResult.agent_card });
                    return typeof responseData === 'string'
                      ? responseData
                      : JSON.stringify(responseData, null, 2);
                  })()}
                  style={{
                    flex: 1,
                    minHeight: 300,
                    fontFamily:
                      "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
                    fontSize: 12,
                    resize: 'vertical',
                  }}
                />
              </div>
            )}
          </div>
        )}
      </Drawer>
      <Modal
        title={t(
          protocol === 'a2a'
            ? 'components.createAgentTaskForm.editA2aScenarioTitle'
            : 'components.createAgentTaskForm.editMcpScenarioTitle'
        )}
        open={scenarioModalOpen}
        onCancel={() => setScenarioModalOpen(false)}
        onOk={saveScenario}
        destroyOnHidden
      >
        <Form form={scenarioForm} layout='vertical'>
          <Form.Item
            name='id'
            label={t('components.createAgentTaskForm.scenarioId')}
            rules={[
              {
                required: true,
                message: t('components.createAgentTaskForm.scenarioIdRequired'),
              },
            ]}
          >
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col span={18}>
              <Form.Item
                name='name'
                label={t('components.createAgentTaskForm.scenarioName')}
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createAgentTaskForm.scenarioNameRequired'
                    ),
                  },
                ]}
              >
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name='weight'
                label={t('components.createAgentTaskForm.weight')}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          {protocol === 'a2a' ? (
            <Form.Item
              name='message_json'
              label='Message'
              rules={[{ required: true }]}
            >
              <TextArea rows={10} spellCheck={false} />
            </Form.Item>
          ) : (
            <>
              <Form.Item
                name='tool_name'
                label={t('components.createAgentTaskForm.toolName')}
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createAgentTaskForm.toolNameRequired'
                    ),
                  },
                ]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name='arguments_json'
                label='arguments'
                rules={[{ required: true }]}
              >
                <TextArea rows={8} spellCheck={false} />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </>
  );
};

export default CreateAgentTaskForm;
