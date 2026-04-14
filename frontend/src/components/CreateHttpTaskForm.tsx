/**
 * @file CreateHttpTaskForm.tsx
 * @description Form for creating HTTP API tasks
 */
import {
  BugOutlined,
  CopyOutlined,
  InfoCircleOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  Upload,
  theme,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { httpTaskApi, uploadDatasetFile } from '@/api/services';
import { HttpTask } from '@/types/job';
import { copyToClipboard } from '@/utils/clipboard';
import parseCurlCommand from '@/utils/curl';

const { TextArea } = Input;
const { Dragger } = Upload;
const { Text } = Typography;

interface Props {
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  initialData?: Partial<HttpTask> | null;
}

const HTTP_METHOD_OPTIONS = [
  'GET',
  'POST',
  'PUT',
  'PATCH',
  'DELETE',
  'HEAD',
  'OPTIONS',
];

/** Methods that typically carry a request body. */
const METHODS_WITH_BODY = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

const CreateHttpTaskForm: React.FC<Props> = ({
  onSubmit,
  onCancel,
  loading,
  initialData,
}) => {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [testing, setTesting] = useState(false);
  const [datasetUploading, setDatasetUploading] = useState(false);
  const [datasetFileName, setDatasetFileName] = useState<string>('');
  const [tempTaskId, setTempTaskId] = useState(`temp-${Date.now()}`);
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const { token } = theme.useToken();

  const toSingleUploadFileList = (filename?: string, uid: string = '-1') =>
    filename
      ? [
          {
            uid,
            name: String(filename),
            status: 'done' as const,
          },
        ]
      : [];

  const methodValue = Form.useWatch('method', form);
  const urlValue = Form.useWatch('target_url', form);
  const datasetSource = Form.useWatch('dataset_source', form);
  const loadMode = Form.useWatch('load_mode', form) || 'fixed';
  const [assertEnabled, setAssertEnabled] = useState(false);

  /** Whether the currently selected method supports a request body. */
  const methodSupportsBody = useMemo(
    () => METHODS_WITH_BODY.has(methodValue),
    [methodValue]
  );

  const isFormReady = useMemo(() => {
    const hasUrl = urlValue && /^https?:\/\//i.test(urlValue);
    const hasMethod = !!methodValue;
    return !!(hasUrl && hasMethod);
  }, [methodValue, urlValue]);

  // Create fresh default values function
  const createDefaultValues = (taskId: string) => ({
    name: '',
    method: 'GET',
    response_mode: 'non-stream',
    target_url: '',
    headers: 'Content-Type: application/json',
    request_body: '',
    load_mode: 'fixed' as const,
    concurrent_users: 1,
    spawn_rate: 1,
    duration: 60,
    // Stepped load defaults
    step_start_users: 10,
    step_increment: 10,
    step_duration: 30,
    step_max_users: 100,
    step_sustain_duration: 60,
    curl_command: '',
    dataset_source: 'none',
    dataset_file: '',
    // Success assertion defaults
    success_assert_field: 'code',
    success_assert_operator: 'eq',
    success_assert_value: '0',
    temp_task_id: taskId,
  });

  const defaultValues = useMemo(
    () => createDefaultValues(tempTaskId),
    [tempTaskId]
  );

  const initialValues = useMemo(() => {
    if (initialData) {
      // When copying template, copy the headers value from the template
      let headersValue = 'Content-Type: application/json';
      const { headers } = initialData;
      if (headers) {
        if (typeof headers === 'string') {
          const trimmed = (headers as string).trim();
          headersValue = trimmed ? headers : 'Content-Type: application/json';
        } else if (Array.isArray(headers) && headers.length > 0) {
          // Convert array format to string format
          headersValue = (headers as Array<{ key: string; value: string }>)
            .map(h => `${h.key}: ${h.value}`)
            .join('\n');
        }
      }

      // When copying template, ensure request_body is properly handled
      let requestBodyValue = '';
      const requestBody = initialData.request_body;
      if (requestBody !== undefined && requestBody !== null) {
        // Preserve the request body value, convert to string if needed
        requestBodyValue =
          typeof requestBody === 'string' ? requestBody : String(requestBody);
      }

      return {
        ...defaultValues,
        ...initialData,
        headers: headersValue,
        request_body: requestBodyValue,
        dataset_source:
          (initialData as any).dataset_source ??
          ((initialData as any).dataset_file
            ? 'upload'
            : defaultValues.dataset_source),
        dataset_file:
          (initialData as any).dataset_file ?? defaultValues.dataset_file,
        temp_task_id: tempTaskId, // Always use new tempTaskId
      };
    }
    return defaultValues;
  }, [initialData, defaultValues, tempTaskId]);

  // Initialize form with default values on mount if no initialData
  useEffect(() => {
    if (!initialData) {
      form.setFieldsValue(defaultValues);
    }
  }, []);

  // Reset form when initialData changes (especially when it becomes null)
  useEffect(() => {
    if (initialData) {
      // Set form values when copying template
      form.setFieldsValue(initialValues);
      // Preserve uploaded dataset path and show filename for clarity
      const datasetPath = (initialValues as any).dataset_file;
      if (datasetPath) {
        const guessedName =
          typeof datasetPath === 'string'
            ? datasetPath.split('/').pop() || datasetPath
            : '';
        setDatasetFileName(guessedName);
      } else {
        setDatasetFileName('');
      }
      // Restore success assertion state from template
      if (initialData.success_assert) {
        try {
          const parsed = JSON.parse(initialData.success_assert);
          setAssertEnabled(true);
          form.setFieldsValue({
            success_assert_field: parsed.field || 'code',
            success_assert_operator: parsed.operator || 'eq',
            success_assert_value: String(
              Array.isArray(parsed.value)
                ? parsed.value.join(',')
                : (parsed.value ?? '0')
            ),
          });
        } catch {
          setAssertEnabled(false);
        }
      } else {
        setAssertEnabled(false);
      }
    } else {
      // When creating new task (initialData is null), generate new tempTaskId and reset form completely
      const newTempTaskId = `temp-${Date.now()}`;
      setTempTaskId(newTempTaskId);
      // Create fresh default values with new tempTaskId
      const freshDefaults = createDefaultValues(newTempTaskId);
      // Reset form completely to avoid any caching
      form.resetFields();
      form.setFieldsValue(freshDefaults);
      setDatasetFileName('');
      setAssertEnabled(false);
      // Clear test modal state
      setTestModalVisible(false);
      setTestResult(null);
    }
  }, [initialData]);

  // When switching to a method that does NOT carry a body, clear body-related fields
  useEffect(() => {
    if (methodValue && !METHODS_WITH_BODY.has(methodValue)) {
      form.setFieldsValue({
        request_body: '',
        dataset_source: 'none',
        dataset_file: '',
      });
      setDatasetFileName('');
    }
  }, [methodValue]);

  const buildPayload = (values: any, includeTempId: boolean = false) => {
    const curlCommand = (values.curl_command || '').trim();
    const maxCurlLength = 8000;
    const isCurlTooLong = curlCommand.length > maxCurlLength;
    const safeCurlCommand = isCurlTooLong
      ? curlCommand.slice(0, maxCurlLength)
      : curlCommand;

    const hasBody = METHODS_WITH_BODY.has((values.method || '').toUpperCase());
    const datasetFile =
      hasBody && values.dataset_source === 'upload'
        ? values.dataset_file || ''
        : '';

    const mode = values.load_mode || 'fixed';

    // Build success_assert JSON if enabled
    let successAssert: string | undefined;
    if (assertEnabled) {
      const field = (values.success_assert_field || '').trim();
      const operator = values.success_assert_operator || 'eq';
      const rawValue = (values.success_assert_value || '').trim();

      if (field && rawValue) {
        let parsedValue: any = rawValue;
        // For 'in' / 'not_in' operators, split comma-separated values
        if (operator === 'in' || operator === 'not_in') {
          parsedValue = rawValue.split(',').map((v: string) => {
            const trimmed = v.trim();
            const num = Number(trimmed);
            return Number.isNaN(num) ? trimmed : num;
          });
        } else {
          // Try to parse as number for numeric comparisons
          const num = Number(rawValue);
          if (!Number.isNaN(num)) {
            parsedValue = num;
          }
        }
        successAssert = JSON.stringify({
          field,
          operator,
          value: parsedValue,
        });
      }
    }

    const payload: any = {
      ...values,
      load_mode: mode,
      response_mode: values.response_mode,
      request_body: hasBody ? values.request_body || '' : '',
      dataset_file: datasetFile,
      dataset_source: hasBody ? values.dataset_source || 'none' : 'none',
      curl_command: safeCurlCommand,
      success_assert: successAssert || null,
      headers: (values.headers || '').trim()
        ? values.headers
            .split('\n')
            .filter((line: string) => line.trim())
            .map((line: string) => {
              const [key, ...rest] = line.split(':');
              return { key: key.trim(), value: rest.join(':').trim() };
            })
        : [],
      ...(includeTempId
        ? { temp_task_id: values.temp_task_id || tempTaskId }
        : {}),
    };

    // Clean up internal assert fields that should not be sent to backend
    delete payload.success_assert_field;
    delete payload.success_assert_operator;
    delete payload.success_assert_value;

    if (mode === 'fixed') {
      // Clear stepped fields for fixed mode
      delete payload.step_start_users;
      delete payload.step_increment;
      delete payload.step_duration;
      delete payload.step_max_users;
      delete payload.step_sustain_duration;
    } else {
      // For stepped mode, set fixed fields to placeholder values
      // Backend will derive actual values from stepped config
      payload.concurrent_users = Math.max(
        1,
        Number(values.step_max_users) || 1
      );
      payload.spawn_rate = Math.max(1, Number(values.step_increment) || 1);
      // Calculate approximate total duration for stepped mode
      // steps = ceil((max - start) / increment), total ≈ steps * step_duration + sustain
      const startU = Math.max(1, Number(values.step_start_users) || 1);
      const maxU = Math.max(1, Number(values.step_max_users) || 1);
      const incr = Math.max(1, Number(values.step_increment) || 1);
      const stepDur = Math.max(1, Number(values.step_duration) || 30);
      const sustainDur = Math.max(
        1,
        Number(values.step_sustain_duration) || 60
      );
      const steps = Math.max(1, Math.ceil((maxU - startU) / incr));
      payload.duration = Math.max(1, steps * stepDur + sustainDur);
    }

    return payload;
  };

  const handleCurlParse = () => {
    const curl = form.getFieldValue('curl_command') as string;
    if (!curl) {
      message.warning(t('components.createHttpTaskForm.curlParseEmpty'));
      return;
    }
    const maxCurlLength = 8000;
    if (curl.length > maxCurlLength) {
      message.warning(
        t('components.createHttpTaskForm.curlTooLong', { max: maxCurlLength })
      );
    }
    const parsed = parseCurlCommand(curl);
    if (!parsed.url) {
      message.error(t('components.createHttpTaskForm.curlParseNoUrl'));
      return;
    }
    const headerText = (parsed.headers || [])
      .map(h => `${h.key}: ${h.value}`)
      .join('\n');
    form.setFieldsValue({
      target_url: parsed.url,
      method: parsed.method || 'GET',
      headers: headerText,
      request_body: parsed.body || '',
    });
    message.success(t('components.createHttpTaskForm.curlParseSuccess'));
  };

  const handleFinish = async (values: any) => {
    const payload = buildPayload(values, true);
    await onSubmit(payload);
  };

  const handleTest = async () => {
    try {
      const requiredFields = ['method', 'target_url'];
      // Validate minimal set
      await form.validateFields(requiredFields as any);

      // Get current form values
      const allValues = form.getFieldsValue(true);

      // Build test-only payload - only include fields needed by HttpTaskTestReq
      const headersStr = (allValues.headers || '').trim();
      const parsedHeaders = headersStr
        ? headersStr
            .split('\n')
            .filter((line: string) => line.trim())
            .map((line: string) => {
              const [key, ...rest] = line.split(':');
              return { key: key.trim(), value: rest.join(':').trim() };
            })
        : [];

      const testHasBody = METHODS_WITH_BODY.has(
        (allValues.method || '').toUpperCase()
      );
      const payload: any = {
        method: allValues.method,
        target_url: allValues.target_url,
        headers: parsedHeaders,
        cookies: allValues.cookies || [],
        request_body: testHasBody ? allValues.request_body || null : null,
      };

      setTesting(true);
      const res = await httpTaskApi.testJob(payload);
      const data = (res as any)?.data ?? {};
      const httpStatus = data?.http_status ?? data?.status ?? res?.status;
      setTestResult({
        status: data?.status || 'success',
        http_status: httpStatus,
        headers: data?.headers,
        body: data?.body ?? data,
      });
      setTestModalVisible(true);
    } catch (err: any) {
      // apiClient throws { data, status, statusText } — not wrapped in .response
      const errData = err?.data ?? err?.response?.data;
      const detail = errData?.detail;
      let detailText = '';
      if (Array.isArray(detail)) {
        detailText = detail
          .map((d: any) => d?.msg || d?.error || JSON.stringify(d))
          .join('; ');
      } else if (typeof detail === 'string') {
        detailText = detail;
      } else if (detail) {
        detailText = JSON.stringify(detail);
      }

      const errorMsg =
        errData?.error ||
        detailText ||
        err?.message ||
        t('components.createHttpTaskForm.testFailed');

      message.error(errorMsg);
      setTestResult({
        status: 'error',
        error: errorMsg,
        body: errData || errorMsg,
      });
      setTestModalVisible(true);
    } finally {
      setTesting(false);
    }
  };

  const handleDatasetUpload = async (options: any) => {
    const { file, onSuccess, onError } = options;
    try {
      setDatasetUploading(true);
      const effectiveTaskId = form.getFieldValue('temp_task_id') || tempTaskId;
      const res = await uploadDatasetFile(file, effectiveTaskId);
      const datasetPath =
        (res as any)?.test_data ||
        (res as any)?.files?.[0]?.path ||
        (res as any)?.files?.[0]?.url;
      if (!datasetPath) {
        throw new Error('No dataset path returned');
      }
      form.setFieldsValue({
        dataset_file: datasetPath,
        temp_task_id: (res as any)?.task_id || effectiveTaskId,
        dataset_source: 'upload', // explicitly set to avoid any ambiguity
      });
      setDatasetFileName(file.name);
      message.success(t('components.createHttpTaskForm.datasetUploadSuccess'));
      if (onSuccess) onSuccess(res, file);
    } catch (err: any) {
      message.error(
        err?.message || t('components.createHttpTaskForm.datasetUploadFailed')
      );
      if (onError) onError(err);
    } finally {
      setDatasetUploading(false);
    }
  };

  const handleDatasetRemove = () => {
    setDatasetFileName('');
    form.setFieldsValue({ dataset_file: undefined });
  };

  return (
    <Card variant='borderless'>
      <Form
        key={tempTaskId}
        layout='vertical'
        form={form}
        onFinish={handleFinish}
      >
        <Form.Item name='temp_task_id' hidden>
          <Input />
        </Form.Item>

        <Form.Item
          label={t('components.createHttpTaskForm.taskName')}
          name='name'
          rules={[
            {
              required: true,
              message: t('components.createHttpTaskForm.taskNameRequired'),
            },
          ]}
        >
          <Input
            placeholder={t('components.createHttpTaskForm.taskNamePlaceholder')}
            maxLength={100}
          />
        </Form.Item>

        <Form.Item
          label={
            <Space>
              {t('components.createHttpTaskForm.curlLabel')}
              <Tooltip
                title={t(
                  'components.createHttpTaskForm.curlParseHint',
                  'Paste full curl to auto-fill request info'
                )}
              >
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
          }
          name='curl_command'
        >
          <TextArea
            rows={3}
            placeholder={t('components.createHttpTaskForm.curlPlaceholder')}
          />
        </Form.Item>
        <Button
          type='primary'
          onClick={handleCurlParse}
          style={{ marginBottom: 12 }}
        >
          {t('components.createHttpTaskForm.curlParseButtonOneClick')}
        </Button>

        <Form.Item
          label={t('components.createHttpTaskForm.targetUrl')}
          name='target_url'
          rules={[
            {
              required: true,
              message: t('components.createHttpTaskForm.targetUrlRequired'),
            },
            {
              validator(_, value) {
                if (!value || /^https?:\/\//i.test(value))
                  return Promise.resolve();
                return Promise.reject(
                  new Error(t('components.createHttpTaskForm.targetUrlInvalid'))
                );
              },
            },
          ]}
        >
          <Input
            placeholder={t(
              'components.createHttpTaskForm.targetUrlPlaceholder'
            )}
          />
        </Form.Item>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label={t('components.createHttpTaskForm.httpMethod')}
              name='method'
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createHttpTaskForm.httpMethodRequired'
                  ),
                },
              ]}
            >
              <Select
                showSearch
                optionFilterProp='label'
                placeholder={t(
                  'components.createHttpTaskForm.httpMethodPlaceholder'
                )}
                options={HTTP_METHOD_OPTIONS.map(m => ({
                  label: m,
                  value: m,
                }))}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label={t('components.createHttpTaskForm.responseMode')}
              name='response_mode'
            >
              <Select
                disabled
                value='non-stream'
                options={[
                  {
                    label: t('components.createHttpTaskForm.stream'),
                    value: 'stream',
                  },
                  {
                    label: t('components.createHttpTaskForm.nonStreaming'),
                    value: 'non-stream',
                  },
                ]}
              />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          label={
            <Space>
              {t('components.createHttpTaskForm.headers')}
              <Tooltip
                title={t(
                  'components.createHttpTaskForm.headersHint',
                  'One per line, e.g. Key: Value'
                )}
              >
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
          }
          name='headers'
        >
          <TextArea
            rows={4}
            placeholder={t('components.createHttpTaskForm.headersPlaceholder')}
          />
        </Form.Item>

        {/* Request body & dataset – only shown for methods that carry a body */}
        {methodSupportsBody && (
          <>
            <Form.Item
              label={t('components.createHttpTaskForm.body')}
              name='request_body'
              rules={[
                {
                  required: datasetSource === 'none',
                  message: t('components.createHttpTaskForm.bodyRequired'),
                },
              ]}
            >
              <TextArea
                rows={4}
                placeholder={t('components.createHttpTaskForm.bodyPlaceholder')}
                maxLength={100000}
                showCount
              />
            </Form.Item>

            <Form.Item
              label={t('components.createHttpTaskForm.datasetSource')}
              name='dataset_source'
              tooltip={t(
                'components.createHttpTaskForm.datasetInfoTip',
                'If not using dataset, original body will be used; if upload, provide full request body JSONL.'
              )}
            >
              <Select
                options={[
                  {
                    label: t('components.createHttpTaskForm.datasetNone'),
                    value: 'none',
                  },
                  {
                    label: t('components.createHttpTaskForm.datasetUpload'),
                    value: 'upload',
                  },
                ]}
              />
            </Form.Item>

            {datasetSource === 'upload' && (
              <Form.Item
                label={t('components.createHttpTaskForm.datasetFile')}
                required
              >
                <Form.Item
                  name='dataset_file'
                  noStyle
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createHttpTaskForm.datasetFileRequired'
                      ),
                    },
                  ]}
                >
                  <Input type='hidden' />
                </Form.Item>
                <Dragger
                  name='file'
                  maxCount={1}
                  accept='.jsonl,.json'
                  customRequest={handleDatasetUpload}
                  onRemove={handleDatasetRemove}
                  disabled={datasetUploading}
                  fileList={toSingleUploadFileList(datasetFileName)}
                  showUploadList={{ showRemoveIcon: false }}
                  style={{
                    borderRadius: 12,
                    borderColor: token.colorBorderSecondary,
                    background: token.colorFillAlter,
                  }}
                >
                  <p
                    className='ant-upload-drag-icon'
                    style={{ marginBottom: 12 }}
                  >
                    <UploadOutlined
                      style={{ color: token.colorPrimary, fontSize: 24 }}
                    />
                  </p>
                  <Text strong style={{ fontSize: 16 }}>
                    {t('components.createHttpTaskForm.datasetUploadTip')}
                  </Text>
                </Dragger>
              </Form.Item>
            )}
          </>
        )}

        {/* Success Response Assertion — optional business-level check */}
        <Form.Item
          label={
            <Space>
              {t('components.createHttpTaskForm.successAssert')}
              <Tooltip
                title={t('components.createHttpTaskForm.successAssertTip')}
              >
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
          }
        >
          <Switch
            checked={assertEnabled}
            onChange={setAssertEnabled}
            checkedChildren={t('components.createHttpTaskForm.successAssertOn')}
            unCheckedChildren={t(
              'components.createHttpTaskForm.successAssertOff'
            )}
          />
        </Form.Item>

        {assertEnabled && (
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                label={t('components.createHttpTaskForm.successAssertField')}
                name='success_assert_field'
                rules={[
                  {
                    required: assertEnabled,
                    message: t(
                      'components.createHttpTaskForm.successAssertFieldRequired'
                    ),
                  },
                ]}
              >
                <Input
                  placeholder={t(
                    'components.createHttpTaskForm.successAssertFieldPlaceholder'
                  )}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label={t('components.createHttpTaskForm.successAssertOperator')}
                name='success_assert_operator'
              >
                <Select
                  options={[
                    { label: '= (eq)', value: 'eq' },
                    { label: '≠ (neq)', value: 'neq' },
                    { label: '> (gt)', value: 'gt' },
                    { label: '≥ (gte)', value: 'gte' },
                    { label: '< (lt)', value: 'lt' },
                    { label: '≤ (lte)', value: 'lte' },
                    { label: '∈ (in)', value: 'in' },
                    { label: '∉ (not_in)', value: 'not_in' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label={t('components.createHttpTaskForm.successAssertValue')}
                name='success_assert_value'
                rules={[
                  {
                    required: assertEnabled,
                    message: t(
                      'components.createHttpTaskForm.successAssertValueRequired'
                    ),
                  },
                ]}
              >
                <Input
                  placeholder={t(
                    'components.createHttpTaskForm.successAssertValuePlaceholder'
                  )}
                />
              </Form.Item>
            </Col>
          </Row>
        )}

        {/* Load mode selector: fixed concurrency vs stepped */}
        <Form.Item
          label={t('components.createHttpTaskForm.loadMode')}
          name='load_mode'
        >
          <Radio.Group>
            <Radio.Button value='fixed'>
              {t('components.createHttpTaskForm.loadModeFixed')}
            </Radio.Button>
            <Radio.Button value='stepped'>
              {t('components.createHttpTaskForm.loadModeStepped')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        {/* Fixed concurrency configuration */}
        {loadMode === 'fixed' && (
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                label={t('components.createHttpTaskForm.concurrentUsers')}
                name='concurrent_users'
                rules={[
                  {
                    required: loadMode === 'fixed',
                    message: t(
                      'components.createHttpTaskForm.concurrentUsersRequired'
                    ),
                  },
                ]}
              >
                <InputNumber min={1} max={5000} className='w-full' />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label={
                  <Space>
                    {t('components.createHttpTaskForm.spawnRate')}
                    <Tooltip
                      title={t('components.createHttpTaskForm.spawnRateTip')}
                    >
                      <InfoCircleOutlined />
                    </Tooltip>
                  </Space>
                }
                name='spawn_rate'
                rules={[
                  {
                    required: loadMode === 'fixed',
                    message: t(
                      'components.createHttpTaskForm.spawnRateRequired'
                    ),
                  },
                ]}
              >
                <InputNumber min={1} max={10000} className='w-full' />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label={t('components.createHttpTaskForm.duration')}
                name='duration'
                rules={[
                  {
                    required: loadMode === 'fixed',
                    message: t(
                      'components.createHttpTaskForm.durationRequired'
                    ),
                  },
                ]}
              >
                <InputNumber min={1} max={172800} className='w-full' />
              </Form.Item>
            </Col>
          </Row>
        )}

        {/* Stepped load configuration */}
        {loadMode === 'stepped' && (
          <>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item
                  label={t('components.createHttpTaskForm.stepStartUsers')}
                  name='step_start_users'
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createHttpTaskForm.stepStartUsersRequired'
                      ),
                    },
                  ]}
                >
                  <InputNumber min={1} max={5000} className='w-full' />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  label={t('components.createHttpTaskForm.stepIncrement')}
                  name='step_increment'
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createHttpTaskForm.stepIncrementRequired'
                      ),
                    },
                  ]}
                >
                  <InputNumber min={1} max={1000} className='w-full' />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  label={t('components.createHttpTaskForm.stepDuration')}
                  name='step_duration'
                  tooltip={t('components.createHttpTaskForm.stepDurationTip')}
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createHttpTaskForm.stepDurationRequired'
                      ),
                    },
                  ]}
                >
                  <InputNumber min={5} max={3600} className='w-full' />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  label={t('components.createHttpTaskForm.stepMaxUsers')}
                  name='step_max_users'
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createHttpTaskForm.stepMaxUsersRequired'
                      ),
                    },
                  ]}
                >
                  <InputNumber min={1} max={5000} className='w-full' />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  label={t('components.createHttpTaskForm.stepSustainDuration')}
                  name='step_sustain_duration'
                  tooltip={t(
                    'components.createHttpTaskForm.stepSustainDurationTip'
                  )}
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createHttpTaskForm.stepSustainDurationRequired'
                      ),
                    },
                  ]}
                >
                  <InputNumber min={1} max={172800} className='w-full' />
                </Form.Item>
              </Col>
            </Row>
          </>
        )}

        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type='primary'
            icon={<BugOutlined />}
            onClick={handleTest}
            loading={testing}
            disabled={!isFormReady || testing}
          >
            {t('components.createHttpTaskForm.test')}
          </Button>
          <Button onClick={onCancel}>
            {t('components.createHttpTaskForm.cancel')}
          </Button>
          <Button type='primary' htmlType='submit' loading={loading}>
            {t('components.createHttpTaskForm.create')}
          </Button>
        </Space>
      </Form>

      <Drawer
        title={
          <Space>
            <BugOutlined />
            <span>{t('components.createHttpTaskForm.apiTestTitle')}</span>
          </Space>
        }
        open={testModalVisible}
        onClose={() => setTestModalVisible(false)}
        width={560}
        destroyOnClose
        className='api-test-drawer'
      >
        {testResult ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
            }}
          >
            {/* Status Section */}
            <Descriptions column={1} bordered size='small'>
              {testResult.http_status !== undefined && (
                <Descriptions.Item
                  label={t('components.createHttpTaskForm.testStatusCode')}
                >
                  <Tag
                    color={testResult.http_status === 200 ? 'green' : 'red'}
                    style={{ fontSize: 14, padding: '2px 12px' }}
                  >
                    {testResult.http_status}
                  </Tag>
                </Descriptions.Item>
              )}
            </Descriptions>

            {/* Error Message — only show when no response body */}
            {testResult.status === 'error' &&
              testResult.error &&
              testResult.body === undefined && (
                <Alert
                  type='error'
                  message={testResult.error}
                  style={{ marginTop: 12 }}
                />
              )}

            {/* Response Body */}
            {testResult.body !== undefined && (
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
                    {t('components.createHttpTaskForm.testResponse')}
                  </Text>
                  <Button
                    type='text'
                    size='small'
                    icon={<CopyOutlined />}
                    onClick={() => {
                      const textToCopy =
                        typeof testResult.body === 'string'
                          ? testResult.body
                          : JSON.stringify(testResult.body ?? {}, null, 2);
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
                  value={
                    typeof testResult.body === 'string'
                      ? testResult.body
                      : JSON.stringify(testResult.body ?? {}, null, 2)
                  }
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
        ) : (
          <div>{t('common.noData')}</div>
        )}
      </Drawer>
    </Card>
  );
};

export default CreateHttpTaskForm;
