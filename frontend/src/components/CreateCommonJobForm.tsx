/**
 * @file CreateCommonJobForm.tsx
 * @description Form for creating common API jobs
 */
import { BugOutlined, InfoCircleOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Tooltip,
  Upload,
  theme,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { commonJobApi, uploadDatasetFile } from '@/api/services';
import { CommonJob } from '@/types/job';
import parseCurlCommand from '@/utils/curl';

const { TextArea } = Input;
const { Dragger } = Upload;

interface Props {
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  initialData?: Partial<CommonJob> | null;
}

const HTTP_METHOD_OPTIONS = [
  'GET',
  'POST',
  // 'PUT',
  // 'PATCH',
  // 'DELETE',
  // 'HEAD',
  // 'OPTIONS',
];

const CreateCommonJobForm: React.FC<Props> = ({
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
  const methodValue = Form.useWatch('method', form);
  const urlValue = Form.useWatch('target_url', form);
  const datasetSource = Form.useWatch('dataset_source', form);

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
    concurrent_users: 1,
    spawn_rate: 1,
    duration: 60,
    curl_command: '',
    dataset_source: 'none',
    dataset_file: '',
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
          (initialData as any).dataset_source ?? defaultValues.dataset_source,
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
      // Clear test modal state
      setTestModalVisible(false);
      setTestResult(null);
    }
  }, [initialData]);

  const buildPayload = (values: any, includeTempId: boolean = false) => {
    const curlCommand = (values.curl_command || '').trim();
    const maxCurlLength = 8000;
    const isCurlTooLong = curlCommand.length > maxCurlLength;
    const safeCurlCommand = isCurlTooLong
      ? curlCommand.slice(0, maxCurlLength)
      : curlCommand;

    const datasetFile =
      values.dataset_source === 'upload' ? values.dataset_file || '' : '';

    return {
      ...values,
      response_mode: values.response_mode,
      dataset_file: datasetFile,
      curl_command: safeCurlCommand,
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
  };

  const handleCurlParse = () => {
    const curl = form.getFieldValue('curl_command') as string;
    if (!curl) {
      message.warning(t('components.createCommonJobForm.curlParseEmpty'));
      return;
    }
    const maxCurlLength = 8000;
    if (curl.length > maxCurlLength) {
      message.warning(
        t('components.createCommonJobForm.curlTooLong', { max: maxCurlLength })
      );
    }
    const parsed = parseCurlCommand(curl);
    if (!parsed.url) {
      message.error(t('components.createCommonJobForm.curlParseNoUrl'));
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
    message.success(t('components.createCommonJobForm.curlParseSuccess'));
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

      // Merge all current form values with initial defaults
      const allValues = form.getFieldsValue(true);
      const mergedValues: any = {
        ...initialValues,
        ...allValues,
      };

      // Fallbacks for required backend fields
      mergedValues.name =
        mergedValues.name?.toString().trim() || `temp-${Date.now()}`;
      mergedValues.temp_task_id =
        mergedValues.temp_task_id || `temp-${Date.now()}`;
      mergedValues.concurrent_users = mergedValues.concurrent_users || 1;
      mergedValues.spawn_rate =
        mergedValues.spawn_rate || mergedValues.concurrent_users || 1;
      mergedValues.duration = mergedValues.duration || 60;
      mergedValues.dataset_source = mergedValues.dataset_source || 'none';

      const payload = buildPayload(mergedValues);
      setTesting(true);
      const res = await commonJobApi.testJob(payload);
      const data = (res as any)?.data ?? {};
      const httpStatus = data?.http_status ?? data?.status ?? res?.status;
      setTestResult({
        status: data?.status || 'success',
        http_status: httpStatus,
        headers: data?.headers,
        body: data?.body ?? data,
      });
      setTestModalVisible(true);
      message.success(
        t('components.createCommonJobForm.testSuccess', {
          status: httpStatus ?? 'OK',
        })
      );
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
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
        err?.response?.data?.error ||
        detailText ||
        err?.message ||
        t('components.createCommonJobForm.testFailed');

      message.error(errorMsg);
      setTestResult({
        status: 'error',
        error: errorMsg,
        body: err?.response?.data || errorMsg,
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
      });
      setDatasetFileName(file.name);
      message.success(t('components.createCommonJobForm.datasetUploadSuccess'));
      if (onSuccess) onSuccess(res, file);
    } catch (err: any) {
      message.error(
        err?.message || t('components.createCommonJobForm.datasetUploadFailed')
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
        <Form.Item name='dataset_file' hidden>
          <Input />
        </Form.Item>

        <Form.Item
          label={t('components.createCommonJobForm.taskName')}
          name='name'
          rules={[
            {
              required: true,
              message: t('components.createCommonJobForm.taskNameRequired'),
            },
          ]}
        >
          <Input
            placeholder={t(
              'components.createCommonJobForm.taskNamePlaceholder'
            )}
            maxLength={100}
          />
        </Form.Item>

        <Form.Item
          label={
            <Space>
              {t('components.createCommonJobForm.curlLabel')}
              <Tooltip
                title={t(
                  'components.createCommonJobForm.curlParseHint',
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
            placeholder={t('components.createCommonJobForm.curlPlaceholder')}
          />
        </Form.Item>
        <Button
          type='primary'
          onClick={handleCurlParse}
          style={{ marginBottom: 12 }}
        >
          {t('components.createCommonJobForm.curlParseButtonOneClick')}
        </Button>

        <Form.Item
          label={t('components.createCommonJobForm.targetUrl')}
          name='target_url'
          rules={[
            {
              required: true,
              message: t('components.createCommonJobForm.targetUrlRequired'),
            },
            {
              validator(_, value) {
                if (!value || /^https?:\/\//i.test(value))
                  return Promise.resolve();
                return Promise.reject(
                  new Error(
                    t('components.createCommonJobForm.targetUrlInvalid')
                  )
                );
              },
            },
          ]}
        >
          <Input
            placeholder={t(
              'components.createCommonJobForm.targetUrlPlaceholder'
            )}
          />
        </Form.Item>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label={t('components.createCommonJobForm.httpMethod')}
              name='method'
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createCommonJobForm.httpMethodRequired'
                  ),
                },
              ]}
            >
              <Select
                showSearch
                optionFilterProp='label'
                placeholder={t(
                  'components.createCommonJobForm.httpMethodPlaceholder'
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
              label={t('components.createCommonJobForm.responseMode')}
              name='response_mode'
            >
              <Select
                disabled
                value='non-stream'
                options={[
                  {
                    label: t('components.createCommonJobForm.stream'),
                    value: 'stream',
                  },
                  {
                    label: t('components.createCommonJobForm.nonStreaming'),
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
              {t('components.createCommonJobForm.headers')}
              <Tooltip
                title={t(
                  'components.createCommonJobForm.headersHint',
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
            placeholder={t('components.createCommonJobForm.headersPlaceholder')}
          />
        </Form.Item>

        <Form.Item
          label={t('components.createCommonJobForm.body')}
          name='request_body'
        >
          <TextArea
            rows={4}
            placeholder={t('components.createCommonJobForm.bodyPlaceholder')}
            maxLength={100000}
            showCount
          />
        </Form.Item>

        <Form.Item
          label={t('components.createCommonJobForm.datasetSource')}
          name='dataset_source'
          tooltip={t(
            'components.createCommonJobForm.datasetInfoTip',
            'If not using dataset, original body will be used; if upload, provide full request body JSONL.'
          )}
        >
          <Select
            options={[
              {
                label: t('components.createCommonJobForm.datasetNone'),
                value: 'none',
              },
              {
                label: t('components.createCommonJobForm.datasetUpload'),
                value: 'upload',
              },
            ]}
          />
        </Form.Item>

        {datasetSource === 'upload' && (
          <Form.Item
            label={t('components.createCommonJobForm.datasetFile')}
            name='dataset_file'
            rules={[
              {
                required: true,
                message: t(
                  'components.createCommonJobForm.datasetFileRequired'
                ),
              },
            ]}
          >
            <Dragger
              name='file'
              multiple={false}
              customRequest={handleDatasetUpload}
              onRemove={handleDatasetRemove}
              disabled={datasetUploading}
              showUploadList={false}
              accept='.jsonl,.json'
            >
              <p>{t('components.createCommonJobForm.datasetUploadTip')}</p>
              {datasetFileName && <p>{datasetFileName}</p>}
            </Dragger>
          </Form.Item>
        )}

        <Row gutter={16}>
          <Col span={8}>
            <Form.Item
              label={t('components.createCommonJobForm.concurrentUsers')}
              name='concurrent_users'
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createCommonJobForm.concurrentUsersRequired'
                  ),
                },
              ]}
            >
              <InputNumber min={1} max={5000} className='w-full' />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              label={t('components.createCommonJobForm.spawnRate')}
              name='spawn_rate'
              required
              rules={[
                {
                  required: true,
                  message: t(
                    'components.createCommonJobForm.spawnRateRequired'
                  ),
                },
              ]}
            >
              <InputNumber min={1} max={10000} className='w-full' />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              label={t('components.createCommonJobForm.duration')}
              name='duration'
              required
              rules={[
                {
                  required: true,
                  message: t('components.createCommonJobForm.durationRequired'),
                },
              ]}
            >
              <InputNumber min={1} max={172800} className='w-full' />
            </Form.Item>
          </Col>
        </Row>

        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            icon={<BugOutlined />}
            onClick={handleTest}
            loading={testing}
            disabled={!isFormReady || testing}
            style={
              !isFormReady || testing
                ? {}
                : { backgroundColor: '#fa8c16', borderColor: '#fa8c16' }
            }
          >
            {t('components.createCommonJobForm.test')}
          </Button>
          <Button onClick={onCancel}>
            {t('components.createCommonJobForm.cancel')}
          </Button>
          <Button type='primary' htmlType='submit' loading={loading}>
            {t('components.createCommonJobForm.create')}
          </Button>
        </Space>
      </Form>

      <Modal
        title={
          <Space>
            <BugOutlined />
            <span>{t('components.createCommonJobForm.apiTestTitle')}</span>
          </Space>
        }
        open={testModalVisible}
        onCancel={() => setTestModalVisible(false)}
        footer={[
          <Button
            key='close'
            type='primary'
            onClick={() => setTestModalVisible(false)}
          >
            {t('common.close')}
          </Button>,
        ]}
        width={760}
        destroyOnHidden
        centered={false}
        mask={false}
        maskClosable={false}
        keyboard={false}
        getContainer={false}
        style={{
          position: 'fixed',
          right: 20,
          top: '50%',
          transform: 'translateY(-50%)',
          margin: 0,
          paddingBottom: 0,
        }}
        styles={{
          body: {
            padding: 16,
            maxHeight: 'calc(100vh - 160px)',
            overflow: 'auto',
          },
          content: {
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1)',
            margin: 0,
          },
          wrapper: {
            overflow: 'visible',
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            pointerEvents: 'none',
          },
        }}
        wrapClassName='api-test-modal-right-side'
      >
        {testResult ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {testResult.http_status !== undefined && (
              <div
                style={{
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                {t('components.createCommonJobForm.testStatusCode')}:{' '}
                <div
                  style={{
                    padding: '4px 12px',
                    borderRadius: 6,
                    border: `1px solid ${
                      testResult.http_status === 200
                        ? token.colorSuccessBorder
                        : token.colorErrorBorder
                    }`,
                    backgroundColor:
                      testResult.http_status === 200
                        ? token.colorSuccessBg
                        : token.colorErrorBg,
                    color:
                      testResult.http_status === 200
                        ? token.colorSuccess
                        : token.colorError,
                    fontWeight: 'bold',
                    minWidth: 60,
                    textAlign: 'center',
                  }}
                >
                  {testResult.http_status}
                </div>
              </div>
            )}
            {testResult.status === 'error' && testResult.error && (
              <div style={{ color: '#d4380d' }}>{testResult.error}</div>
            )}
            <div
              style={{
                background: '#fafafa',
                border: '1px solid #f0f0f0',
                borderRadius: 6,
                padding: 12,
                maxHeight: 360,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                fontFamily: 'Monaco, Consolas, "Courier New", monospace',
                fontSize: 12,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                {t('components.createCommonJobForm.testResponse')}
              </div>
              {typeof testResult.body === 'string'
                ? testResult.body
                : JSON.stringify(testResult.body ?? {}, null, 2)}
            </div>
          </div>
        ) : (
          <div>{t('common.noData')}</div>
        )}
      </Modal>
    </Card>
  );
};

export default CreateCommonJobForm;
