/**
 * @file CreateLlmTaskForm.tsx
 * @description Create LLM task form component
 * @author Charm
 * @copyright 2025
 * */
import {
  ApiOutlined,
  BugOutlined,
  CloudOutlined,
  CopyOutlined,
  DatabaseOutlined,
  FireOutlined,
  InfoCircleOutlined,
  LeftOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  RightOutlined,
  RocketOutlined,
  SettingOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  CardProps,
  Col,
  Collapse,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Row,
  Select,
  Space,
  Tabs,
  Tag,
  theme,
  Tooltip,
  Typography,
  Upload,
} from 'antd';
import React, { useCallback, useEffect, useRef, useState } from 'react';

import {
  llmTaskApi,
  uploadCertificateFiles,
  uploadDatasetFile,
} from '@/api/services';
import { useI18n } from '@/hooks/useI18n';
import { LlmTask } from '@/types/job';
import { copyToClipboard } from '@/utils/clipboard';
import { safeJsonParse } from '@/utils/data';

const { TextArea } = Input;
const { Text } = Typography;

// API Type definitions
type ApiType = 'openai-chat' | 'claude-chat' | 'embeddings' | 'custom-chat';

interface CreateLlmTaskFormProps {
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  initialData?: Partial<LlmTask> | null;
  suppressCopyWarning?: boolean;
}

const CreateLlmTaskFormContent: React.FC<CreateLlmTaskFormProps> = ({
  onSubmit,
  onCancel,
  loading,
  initialData,
  suppressCopyWarning,
}) => {
  const { message } = App.useApp();
  const { t } = useI18n();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(loading || false);
  const [testing, setTesting] = useState(false);
  const { token } = theme.useToken();
  const [tempTaskId] = useState(`temp-${Date.now()}`);
  // add state to track if auto sync spawn_rate
  const [autoSyncSpawnRate, setAutoSyncSpawnRate] = useState(true);
  const loadMode = Form.useWatch('load_mode', form) || 'fixed';
  const watchedApiType = Form.useWatch('api_type', form) || 'openai-chat';
  const [isCopyMode, setIsCopyMode] = useState(false);
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  // Add state for tab management
  const [activeTabKey, setActiveTabKey] = useState('1');
  // Add state to track upload loading
  const [uploading, setUploading] = useState(false);
  const [datasetFile, setDatasetFile] = useState<File | null>(null);
  // Ref to prevent infinite loops during bidirectional sync between payload and form fields
  const isSyncingRef = useRef(false);

  // Get default API path based on API type
  const getDefaultApiPath = (type: ApiType): string => {
    switch (type) {
      case 'openai-chat':
        return '/v1/chat/completions';
      case 'claude-chat':
        return '/v1/messages';
      case 'embeddings':
        return '/v1/embeddings';
      case 'custom-chat':
        return '/v1/custom-model-path';
      default:
        return '/v1/chat/completions';
    }
  };

  // Get default field_mapping based on API type and stream mode
  const getDefaultFieldMapping = (type: ApiType) => {
    switch (type) {
      case 'openai-chat':
      case 'claude-chat':
        // For standard chat APIs, backend will auto-generate field mapping
        return {};

      case 'embeddings':
        return {
          prompt: 'input',
          image: '',
          stream_prefix: '',
          data_format: 'json',
          content: '',
          reasoning_content: '',
          prompt_tokens: '',
          completion_tokens: '',
          total_tokens: '',
          end_prefix: '',
          stop_flag: '',
          end_field: '',
        };

      case 'custom-chat':
        return {
          prompt: '',
          image: '',
          stream_prefix: 'data:',
          data_format: 'json',
          content: '',
          reasoning_content: '',
          prompt_tokens: '',
          completion_tokens: '',
          total_tokens: '',
          end_prefix: 'data:',
          stop_flag: '[DONE]',
          end_field: '',
        };

      default:
        return {};
    }
  };

  // Generate default request payload based on API type, model and stream mode
  const generateDefaultPayload = (
    type: ApiType,
    model: string,
    streamMode: boolean
  ) => {
    switch (type) {
      case 'openai-chat':
        return JSON.stringify(
          {
            model: model || 'none',
            stream: streamMode,
            ...(streamMode ? { stream_options: { include_usage: true } } : {}),
            messages: [
              {
                role: 'user',
                content: 'Hi',
              },
            ],
          },
          null,
          2
        );

      case 'claude-chat':
        return JSON.stringify(
          {
            model: model || 'none',
            max_tokens: 8192,
            stream: streamMode,
            ...(streamMode ? { stream_options: { include_usage: true } } : {}),
            messages: [
              {
                role: 'user',
                content: 'Hi',
              },
            ],
          },
          null,
          2
        );

      case 'embeddings':
        return JSON.stringify(
          {
            input: 'The food was delicious and the waiter...',
            model: model || 'none',
          },
          null,
          2
        );

      case 'custom-chat':
        return JSON.stringify({}, null, 2);

      default:
        return JSON.stringify(
          {
            model: model || 'none',
            stream: streamMode,
            ...(streamMode ? { stream_options: { include_usage: true } } : {}),
            messages: [
              {
                role: 'user',
                content: 'Hi',
              },
            ],
          },
          null,
          2
        );
    }
  };

  const normalizeRequestPayloadString = (payload: string): string => {
    const parsed = safeJsonParse<any>(payload, null);
    if (parsed && typeof parsed === 'object') {
      return JSON.stringify(parsed, null, 2);
    }
    return payload;
  };

  // Helper: update specific fields in the current payload JSON without regenerating the entire payload
  const updatePayloadFields = (updates: Record<string, any>): string | null => {
    const currentPayload = form.getFieldValue('request_payload');
    if (!currentPayload) return null;
    const parsed = safeJsonParse<any>(currentPayload, null);
    if (!parsed || typeof parsed !== 'object') return null;
    let changed = false;
    Object.entries(updates).forEach(([key, value]) => {
      if (parsed[key] !== value) {
        parsed[key] = value;
        changed = true;
      }
    });
    return changed ? JSON.stringify(parsed, null, 2) : null;
  };

  // Helper: extract model and stream values from payload JSON
  const extractFieldsFromPayload = (
    payloadStr: string
  ): { model?: string; stream?: boolean } => {
    const parsed = safeJsonParse<any>(payloadStr, null);
    if (!parsed || typeof parsed !== 'object') return {};
    const result: { model?: string; stream?: boolean } = {};
    if ('model' in parsed && typeof parsed.model === 'string') {
      result.model = parsed.model;
    }
    if ('stream' in parsed && typeof parsed.stream === 'boolean') {
      result.stream = parsed.stream;
    }
    return result;
  };

  // Tab navigation functions
  const goToNextTab = () => {
    const currentApiType = form.getFieldValue('api_type') || 'openai-chat';
    const isStandardChatApi =
      currentApiType === 'openai-chat' || currentApiType === 'claude-chat';

    if (activeTabKey === '1') {
      setActiveTabKey('2');
    } else if (!isStandardChatApi && activeTabKey === '2') {
      // For custom-chat and embeddings: Tab2 (Field Mapping) -> Tab3 (Data/Load)
      setActiveTabKey('3');
    }
  };

  const goToPreviousTab = () => {
    const currentApiType = form.getFieldValue('api_type') || 'openai-chat';
    const isStandardChatApi =
      currentApiType === 'openai-chat' || currentApiType === 'claude-chat';

    if (activeTabKey === '2') {
      setActiveTabKey('1');
    } else if (!isStandardChatApi && activeTabKey === '3') {
      // For custom-chat and embeddings: Tab3 (Data/Load) -> Tab2 (Field Mapping)
      setActiveTabKey('2');
    }
  };

  // Check if current tab is valid for navigation
  const isCurrentTabValid = useCallback(async () => {
    try {
      if (activeTabKey === '1') {
        // Tab 1: Basic Configuration and Request Configuration
        const requiredFields = [
          'name',
          'api_type',
          'target_host',
          'api_path',
          'model',
          'stream_mode',
          'request_payload',
        ];
        await form.validateFields(requiredFields);
        return true;
      }
      if (activeTabKey === '2') {
        // Tab 2: Field Mapping
        const currentApiType = form.getFieldValue('api_type') || 'openai-chat';
        const isEmbedType = currentApiType === 'embeddings';
        const isStandardChatApi =
          currentApiType === 'openai-chat' || currentApiType === 'claude-chat';
        const currentStreamMode = form.getFieldValue('stream_mode');

        // Skip validation for standard chat APIs (backend will handle field mapping)
        if (isStandardChatApi) {
          return true;
        }

        const requiredFields = [['field_mapping', 'prompt']];

        // Add stop_flag validation for non-embed streaming types
        if (!isEmbedType && currentStreamMode) {
          requiredFields.push(['field_mapping', 'stop_flag']);
        }

        await form.validateFields(requiredFields);
        return true;
      }
      // Data/Load configuration tab (key '2' for standard APIs, '3' for others)
      const currentApiType = form.getFieldValue('api_type') || 'openai-chat';
      const isStandardChatApi =
        currentApiType === 'openai-chat' || currentApiType === 'claude-chat';
      const dataLoadTabKey = isStandardChatApi ? '2' : '3';

      if (activeTabKey === dataLoadTabKey) {
        // Test Data and Load Configuration
        const currentLoadMode = form.getFieldValue('load_mode') || 'fixed';
        const requiredFields: string[] = ['test_data_input_type'];
        if (currentLoadMode === 'fixed') {
          requiredFields.push('duration', 'concurrent_users', 'spawn_rate');
        } else {
          requiredFields.push(
            'step_start_users',
            'step_increment',
            'step_duration',
            'step_max_users',
            'step_sustain_duration'
          );
        }

        // Add chat_type validation when using default dataset and chat API
        const currentTestDataInputType =
          form.getFieldValue('test_data_input_type') || 'default';
        if (
          currentTestDataInputType === 'default' &&
          (currentApiType === 'openai-chat' || currentApiType === 'claude-chat')
        ) {
          requiredFields.push('chat_type');
        }

        // Add validation for custom data input and file upload
        if (currentTestDataInputType === 'input') {
          requiredFields.push('test_data');
        } else if (currentTestDataInputType === 'upload') {
          requiredFields.push('test_data_file');
        }

        await form.validateFields(requiredFields);
        return true;
      }
      return true;
    } catch (error) {
      return false;
    }
  }, [activeTabKey, form]);

  // Handle next tab with validation
  const handleNextTab = async () => {
    const isValid = await isCurrentTabValid();
    if (isValid) {
      goToNextTab();
    } else {
      message.error(t('components.createJobForm.pleaseFillRequiredFields'));
    }
  };

  // Body class management removed — Drawer handles overflow natively

  // Form values states to replace Form.useWatch
  const [concurrentUsers, setConcurrentUsers] = useState<number>();
  const [streamMode, setStreamMode] = useState<boolean>(true);
  const [isFormReady, setIsFormReady] = useState(false);

  // Initialize form ready state
  useEffect(() => {
    setIsFormReady(true);
  }, []);

  // Initialize field_mapping based on current API type when not in copy mode
  useEffect(() => {
    if (isFormReady && !isCopyMode && !initialData) {
      const currentApiType = form.getFieldValue('api_type') || 'openai-chat';
      const defaultFieldMapping = getDefaultFieldMapping(currentApiType);
      form.setFieldsValue({ field_mapping: defaultFieldMapping });

      // If API type is embeddings, set stream_mode to false
      const currentStreamMode = form.getFieldValue('stream_mode');
      if (currentApiType === 'embeddings' && currentStreamMode !== false) {
        form.setFieldsValue({ stream_mode: false });
        setStreamMode(false);

        // Update request_payload for embeddings API
        const currentModel = form.getFieldValue('model') || '';
        const newPayload = generateDefaultPayload(
          currentApiType,
          currentModel,
          false
        );
        form.setFieldsValue({ request_payload: newPayload });
      }
    }
  }, [isFormReady, isCopyMode, initialData, form]);

  // when concurrent_users changes and autoSyncSpawnRate is true, auto update spawn_rate
  useEffect(() => {
    if (autoSyncSpawnRate && isFormReady) {
      if (concurrentUsers && typeof concurrentUsers === 'number') {
        const spawnRateValue = Math.min(concurrentUsers, 1000);
        form.setFieldsValue({ spawn_rate: spawnRateValue });
      }
    }
  }, [concurrentUsers, autoSyncSpawnRate, form, isFormReady]);

  // listen to concurrent_users field changes
  const handleConcurrentUsersChange = (value: number) => {
    setConcurrentUsers(value);
    if (autoSyncSpawnRate && value) {
      const spawnRateValue = Math.min(value, 1000);
      form.setFieldsValue({ spawn_rate: spawnRateValue });
    }
  };

  // when user manually changes spawn_rate, close auto sync
  const handleSpawnRateChange = () => {
    setAutoSyncSpawnRate(false);
  };

  // handle api_path change
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleApiPathChange = (value: string) => {
    // Currently no additional handling needed for api_path changes
    // The main logic is handled in the form's onValuesChange callback
  };

  // update submitting state using loading prop
  useEffect(() => {
    setSubmitting(loading || false);
  }, [loading]);

  // Effect to populate form when initialData is provided (for copy mode)
  useEffect(() => {
    if (initialData) {
      setIsCopyMode(true);

      const dataToFill: any = { ...initialData };

      if (
        dataToFill.stream_mode !== undefined &&
        dataToFill.stream_mode !== null
      ) {
        const streamValue = String(dataToFill.stream_mode);
        if (streamValue === '1') {
          dataToFill.stream_mode = true; // "stream"
        } else if (streamValue === '0') {
          dataToFill.stream_mode = false; // "non-stream"
        }
      }

      // use temp_task_id
      dataToFill.temp_task_id = tempTaskId;

      // handle headers
      const currentHeaders = initialData.headers
        ? JSON.parse(JSON.stringify(initialData.headers))
        : [];

      // ensure Content-Type exists and is fixed
      const contentTypeHeader = currentHeaders.find(
        (h: { key: string }) => h.key === 'Content-Type'
      );
      if (contentTypeHeader) {
        contentTypeHeader.value = 'application/json';
        contentTypeHeader.fixed = true;
      } else {
        currentHeaders.unshift({
          key: 'Content-Type',
          value: 'application/json',
          fixed: true,
        });
      }

      // ensure Authorization exists (even if the value is empty)
      const authHeader = currentHeaders.find(
        (h: { key: string }) => h.key === 'Authorization'
      );
      if (!authHeader) {
        currentHeaders.push({
          key: 'Authorization',
          value: '',
          fixed: false,
        });
      }
      dataToFill.headers = currentHeaders;

      // handle cookies
      const currentCookies = initialData.cookies
        ? JSON.parse(JSON.stringify(initialData.cookies))
        : [];
      dataToFill.cookies = currentCookies;

      // Preserve original field_mapping and request_payload when copying
      const originalFieldMapping = dataToFill.field_mapping
        ? JSON.parse(JSON.stringify(dataToFill.field_mapping))
        : {};
      const originalRequestPayload = dataToFill.request_payload;
      const normalizedRequestPayload =
        typeof originalRequestPayload === 'string'
          ? normalizeRequestPayloadString(originalRequestPayload)
          : originalRequestPayload;

      // Always preserve original values when copying
      dataToFill.field_mapping = originalFieldMapping || {
        prompt: 'messages.0.content',
        stream_prefix: 'data:',
        data_format: 'json',
        content: 'choices.0.message.content',
        reasoning_content: 'choices.0.message.reasoning_content',
        prompt_tokens: 'usage.prompt_tokens',
        completion_tokens: 'usage.completion_tokens',
        total_tokens: 'usage.total_tokens',
        end_prefix: 'data:',
        end_field: '',
        stop_flag: '[DONE]',
      };
      dataToFill.request_payload = normalizedRequestPayload;

      // clean fields that should not be copied directly or provided by the user
      delete dataToFill.id;
      delete dataToFill.status;
      delete dataToFill.created_at;
      delete dataToFill.updated_at;
      // actual certificate file needs to be uploaded again

      form.setFieldsValue(dataToFill);

      // Update stream mode state for proper field mapping
      if (dataToFill.stream_mode !== undefined) {
        setStreamMode(dataToFill.stream_mode);
      }

      if (
        dataToFill.concurrent_users &&
        dataToFill.spawn_rate &&
        dataToFill.concurrent_users === dataToFill.spawn_rate
      ) {
        setAutoSyncSpawnRate(true);
      } else {
        setAutoSyncSpawnRate(false);
      }

      // Show message for advanced settings that need attention
      const hasCustomHeaders =
        dataToFill.headers &&
        dataToFill.headers.some(
          (h: any) => h.key !== 'Content-Type' && h.key !== 'Authorization'
        );
      const hasCookies = dataToFill.cookies && dataToFill.cookies.length > 0;
      const hasCertConfig = !!(initialData as any).cert_config;

      if (hasCustomHeaders || hasCookies || hasCertConfig) {
        if (!suppressCopyWarning) {
          message.warning(t('components.createJobForm.taskTemplateCopied'), 5);
        }
      }
    } else if (!isCopyMode) {
      setIsCopyMode(false);
      // reset form fields
      const currentTempTaskId = form.getFieldValue('temp_task_id');
      if (currentTempTaskId !== tempTaskId) {
        form.resetFields();
        setDatasetFile(null);
        const currentConcurrentUsers =
          form.getFieldValue('concurrent_users') || 1;
        form.setFieldsValue({
          temp_task_id: tempTaskId,
          spawn_rate: currentConcurrentUsers,
        });
        setAutoSyncSpawnRate(true);
      }
    }
  }, [initialData, form, tempTaskId, message]);

  // handle certificate file upload
  const handleCertFileUpload = async (options: any) => {
    const { file, onSuccess, onError } = options;
    try {
      // Validate file size (2GB limit)
      const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
      if (file.size > maxSize) {
        message.error(t('components.createJobForm.fileSizeExceedsLimit'));
        onError();
        return;
      }

      form.setFieldsValue({
        temp_task_id: tempTaskId,
        cert_file: file,
      });
      message.success(
        t('components.createJobForm.fileSelected', { fileName: file.name })
      );
      onSuccess();
    } catch (error) {
      message.error(
        t('components.createJobForm.fileUploadFailed', { fileName: file.name })
      );
      onError();
    }
  };

  // handle private key file upload
  const handleKeyFileUpload = async (options: any) => {
    const { file, onSuccess, onError } = options;
    try {
      // Validate file size (2GB limit)
      const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
      if (file.size > maxSize) {
        message.error(
          t('components.createJobForm.fileSizeExceedsLimitWithSize', {
            size: (file.size / (1024 * 1024)).toFixed(3),
          })
        );
        onError();
        return;
      }

      form.setFieldsValue({
        temp_task_id: tempTaskId,
        key_file: file,
      });
      message.success(
        t('components.createJobForm.fileSelected', { fileName: file.name })
      );
      onSuccess();
    } catch (error) {
      message.error(
        t('components.createJobForm.fileUploadFailed', { fileName: file.name })
      );
      onError();
    }
  };

  // handle combined certificate file upload
  const handleCombinedCertUpload = async (options: any) => {
    const { file, onSuccess, onError } = options;
    try {
      // Validate file size (10MB limit)
      const maxSize = 10 * 1024 * 1024; // 10MB
      if (file.size > maxSize) {
        message.error(
          t('components.createJobForm.fileSizeExceedsLimitWithSize', {
            size: (file.size / (1024 * 1024)).toFixed(3),
          })
        );
        onError();
        return;
      }

      form.setFieldsValue({
        temp_task_id: tempTaskId,
        cert_file: file,
        key_file: null,
      });
      message.success(
        t('components.createJobForm.fileSelected', { fileName: file.name })
      );
      onSuccess();
    } catch (error) {
      message.error(
        t('components.createJobForm.fileUploadFailed', { fileName: file.name })
      );
      onError();
    }
  };

  // handle dataset file upload
  const handleDatasetFileUpload = async (options: any) => {
    const { file, onSuccess, onError } = options;
    try {
      // Validate file size (1GB limit)
      const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
      if (file.size > maxSize) {
        message.error(
          t('components.createJobForm.fileSizeExceedsLimitWithSize', {
            size: (file.size / (1024 * 1024)).toFixed(3),
          })
        );
        onError();
        return;
      }

      setDatasetFile(file as File);
      form.setFieldsValue({
        temp_task_id: tempTaskId,
        test_data_file: file.name,
      });
      message.success(
        t('components.createJobForm.fileSelected', { fileName: file.name })
      );
      onSuccess();
    } catch (error) {
      message.error(
        t('components.createJobForm.fileUploadFailed', { fileName: file.name })
      );
      onError();
    }
  };

  const handleDatasetFileRemove = () => {
    setDatasetFile(null);
    form.setFieldsValue({
      test_data_file: undefined,
    });
    return true;
  };

  // Helper function to normalize warmup_duration with default value
  const normalizeWarmupDuration = (values: any) => {
    const defaultWarmupDuration = 120;
    if (
      values.warmup_duration === undefined ||
      values.warmup_duration === null
    ) {
      values.warmup_duration = defaultWarmupDuration;
    }
    if (values.warmup_enabled === false) {
      values.warmup_duration = values.warmup_duration || defaultWarmupDuration;
    }
  };

  // Test API endpoint
  const handleTestAPI = async () => {
    try {
      setTesting(true);

      // Only validate required fields for testing from the first tab
      const requiredFields = ['target_host', 'api_path', 'stream_mode'];

      // Validate only the required fields for testing
      await form.validateFields(requiredFields);

      // Get all form values after validation (include unmounted fields)
      const values = form.getFieldsValue(true);
      const sanitizedModel = values.model?.trim();
      values.model = sanitizedModel || 'none';

      // Ensure request_payload is available - auto-generate if empty
      if (!values.request_payload || !values.request_payload.trim()) {
        const currentApiType = values.api_type || 'openai-chat';
        const currentModel = values.model || '';
        const currentStreamMode =
          values.stream_mode !== undefined ? values.stream_mode : true;
        values.request_payload = generateDefaultPayload(
          currentApiType,
          currentModel,
          currentStreamMode
        );
        // Update form with generated payload
        form.setFieldsValue({ request_payload: values.request_payload });
      }

      // Additional validation for request payload JSON format
      if (!values.request_payload) {
        message.error(t('components.createJobForm.requestPayloadRequired'));
        return;
      }

      // Handle certificate files if present
      if (values.cert_file || values.key_file) {
        try {
          const certType = form.getFieldValue('cert_type') || 'combined';

          // Upload certificate files
          const result = await uploadCertificateFiles(
            values.cert_file,
            certType === 'separate' ? values.key_file : null,
            tempTaskId,
            certType
          );

          // Update values with certificate configuration
          values.cert_config = result.cert_config;
          values.temp_task_id = tempTaskId;

          // Clean up file references
          delete values.cert_file;
          delete values.key_file;
        } catch (error) {
          console.error('Certificate upload error:', error);
          let errorMessage = t(
            'components.createJobForm.certificateUploadFailed'
          );

          if (error?.message) {
            errorMessage = error.message;
          } else if (error?.response?.data?.detail) {
            errorMessage = error.response.data.detail;
          } else if (error?.response?.data?.error) {
            errorMessage = error.response.data.error;
          }

          message.error(errorMessage);
          return;
        }
      }

      // Ensure default headers when none are provided
      if (!values.headers || values.headers.length === 0) {
        values.headers = [
          { key: 'Content-Type', value: 'application/json', fixed: true },
        ];
      }

      // Prepare test data - only include fields needed by backend TaskTestReq
      const testData: any = {
        target_host: values.target_host,
        api_path: values.api_path,
        model: values.model,
        stream_mode: values.stream_mode,
        headers: values.headers,
        cookies: values.cookies,
        request_payload: values.request_payload,
        api_type: values.api_type,
      };

      // Include cert_config if present (uploaded via certificate flow)
      if (values.cert_config) {
        testData.cert_config = values.cert_config;
      }

      // Call test API
      const apiResponse = await llmTaskApi.testApiEndpoint(testData);
      // Extract the actual backend response data
      const result = apiResponse.data;

      setTestResult(result);
      setTestModalVisible(true);
    } catch (error: any) {
      // Try to extract error message from backend response with priority order
      let errorMessage = t('components.createJobForm.testFailedCheckConfig');

      // Priority 1: Backend API error field (most specific)
      if (error?.response?.data?.error) {
        errorMessage = error.response.data.error;
      }
      // Priority 2: Backend API message field
      else if (error?.response?.data?.message) {
        errorMessage = error.response.data.message;
      }
      // Priority 3: Network timeout or connection errors
      else if (
        error?.code === 'ECONNABORTED' &&
        error?.message?.includes('timeout')
      ) {
        errorMessage = t(
          'components.createJobForm.networkTimeoutCheckConnection'
        );
      }
      // Priority 4: Other axios errors
      else if (error?.message) {
        errorMessage = error.message;
      }

      message.error(errorMessage);
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async () => {
    if (submitting || uploading) return;

    try {
      setSubmitting(true);
      const values = await form.validateFields();
      const sanitizedModel = values.model?.trim();
      values.model = sanitizedModel || 'none';
      normalizeWarmupDuration(values);

      // Normalize payload based on load_mode (fixed vs stepped)
      const mode = values.load_mode || 'fixed';
      if (mode === 'fixed') {
        // Clear stepped fields for fixed mode
        delete values.step_start_users;
        delete values.step_increment;
        delete values.step_duration;
        delete values.step_max_users;
        delete values.step_sustain_duration;
      } else {
        // For stepped mode, set fixed fields to valid placeholder values
        // Backend will derive actual values from stepped config
        values.concurrent_users = Math.max(
          1,
          Number(values.step_max_users) || 1
        );
        values.spawn_rate = Math.max(1, Number(values.step_increment) || 1);
        // Calculate approximate total duration for stepped mode
        const startU = Math.max(1, Number(values.step_start_users) || 1);
        const maxU = Math.max(1, Number(values.step_max_users) || 1);
        const incr = Math.max(1, Number(values.step_increment) || 1);
        const stepDur = Math.max(1, Number(values.step_duration) || 30);
        const sustainDur = Math.max(
          1,
          Number(values.step_sustain_duration) || 60
        );
        const steps = Math.max(1, Math.ceil((maxU - startU) / incr));
        values.duration = Math.max(1, steps * stepDur + sustainDur);
      }

      // Normalize and validate field_mapping for non-standard APIs
      const apiType = values.api_type || 'openai-chat';
      const normalizedFieldMapping =
        typeof values.field_mapping === 'string'
          ? safeJsonParse<Record<string, string>>(values.field_mapping, {})
          : values.field_mapping || {};

      if (['custom-chat', 'embeddings'].includes(apiType)) {
        if (
          !normalizedFieldMapping ||
          Object.keys(normalizedFieldMapping).length === 0
        ) {
          message.error('Field mapping is required for this API type');
          setSubmitting(false);
          return;
        }
        if (
          !normalizedFieldMapping.prompt ||
          !String(normalizedFieldMapping.prompt).trim()
        ) {
          message.error(
            t('components.createJobForm.pleaseSpecifyPromptFieldPath')
          );
          setSubmitting(false);
          return;
        }
        if (
          apiType === 'custom-chat' &&
          values.stream_mode !== false &&
          (!normalizedFieldMapping.stop_flag ||
            !String(normalizedFieldMapping.stop_flag).trim())
        ) {
          message.error(t('components.createJobForm.pleaseSpecifyStopSignal'));
          setSubmitting(false);
          return;
        }
      }
      values.field_mapping = normalizedFieldMapping;

      // Ensure request_payload is available - auto-generate if empty
      if (!values.request_payload || !values.request_payload.trim()) {
        const currentApiType = values.api_type || 'openai-chat';
        const currentModel = values.model || '';
        const currentStreamMode =
          values.stream_mode !== undefined ? values.stream_mode : true;
        values.request_payload = generateDefaultPayload(
          currentApiType,
          currentModel,
          currentStreamMode
        );
      }

      if (values.cert_file) {
        try {
          setUploading(true);
          const certType = form.getFieldValue('cert_type') || 'combined';

          const result = await uploadCertificateFiles(
            values.cert_file,
            certType === 'separate' ? values.key_file : null,
            tempTaskId,
            certType
          );

          values.cert_config = result.cert_config;

          // delete file objects from form to avoid serialization issues
          delete values.cert_file;
          delete values.key_file;

          // keep temp_task_id for backend association
          values.temp_task_id = tempTaskId;
        } catch (error: any) {
          let errorMessage = t(
            'components.createJobForm.certificateUploadFailed'
          );

          if (error?.message) {
            errorMessage = error.message;
          } else if (error?.response?.data?.detail) {
            errorMessage = error.response.data.detail;
          } else if (error?.response?.data?.error) {
            errorMessage = error.response.data.error;
          }

          message.error(errorMessage);
          setSubmitting(false);
          setUploading(false);
          return;
        } finally {
          setUploading(false);
        }
      }

      // Handle test data input type
      const inputType = values.test_data_input_type || 'default';
      if (inputType === 'upload') {
        if (!datasetFile) {
          message.error(t('components.createJobForm.pleaseUploadDatasetFile'));
          setSubmitting(false);
          setUploading(false);
          return;
        }
        try {
          setUploading(true);
          const result = await uploadDatasetFile(datasetFile, tempTaskId);
          values.test_data = result.test_data;
          values.temp_task_id = tempTaskId;
        } catch (error: any) {
          let errorMessage = t('components.createJobForm.testDataUploadFailed');

          if (error?.message) {
            errorMessage = error.message;
          } else if (error?.response?.data?.detail) {
            errorMessage = error.response.data.detail;
          } else if (error?.response?.data?.error) {
            errorMessage = error.response.data.error;
          }

          message.error(errorMessage);
          setSubmitting(false);
          setUploading(false);
          return;
        } finally {
          setUploading(false);
        }
      }

      // Clean up temporary dataset holder
      delete values.test_data_file;

      if (inputType === 'default') {
        values.test_data = 'default'; // use default dataset
      } else if (inputType === 'input') {
        // test_data is already set from the form field
      } else if (inputType === 'none') {
        // No dataset mode - clear test_data
        values.test_data = '';
      }
      // For upload type, test_data is set above from file upload result

      // Clean up form-specific fields
      delete values.test_data_input_type;

      await onSubmit(values);
    } catch (error) {
      setSubmitting(false); // Only reset state here when error occurs
      setUploading(false);
    }
  };

  // State to track form validity for testing
  const [isTestButtonEnabled, setIsTestButtonEnabled] = useState(false);

  // Check if form is valid for testing
  const checkFormValidForTest = useCallback(() => {
    try {
      const values = form.getFieldsValue();

      // Only check fields required for testing (from tab 1)
      if (!values.target_host || !values.api_path) {
        return false;
      }

      // Stream mode is required
      if (values.stream_mode === undefined || values.stream_mode === null) {
        return false;
      }

      // Request payload is no longer required for testing - will be auto-generated if empty
      // if (!values.request_payload) {
      //   return false;
      // }

      return true;
    } catch (error) {
      return false;
    }
  }, [form]);

  // Update test button state when form values change
  useEffect(() => {
    const isValid = checkFormValidForTest();
    setIsTestButtonEnabled(isValid);
  }, [checkFormValidForTest]);

  // Initial check after form is ready
  useEffect(() => {
    if (isFormReady) {
      const isValid = checkFormValidForTest();
      setIsTestButtonEnabled(isValid);
    }
  }, [isFormReady, checkFormValidForTest]);

  // Function for external use (backwards compatibility)
  const isFormValidForTest = () => {
    return isTestButtonEnabled;
  };

  // These useEffect hooks are removed since we no longer differentiate API types

  // create advanced settings panel content
  const advancedPanelContent = (
    <div style={{ marginLeft: '8px' }}>
      {/* Header configuration */}
      <div
        style={{
          marginBottom: 24,
          padding: '16px',
          backgroundColor: token.colorFillAlter,
          borderRadius: '8px',
        }}
      >
        <div style={{ marginBottom: 12, fontWeight: 'bold', fontSize: '14px' }}>
          <Space>
            <span>{t('components.createJobForm.httpHeaders')}</span>
            <Tooltip title={t('components.createJobForm.httpHeadersTooltip')}>
              <InfoCircleOutlined />
            </Tooltip>
          </Space>
        </div>
        <Form.List name='headers'>
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => {
                const isFixed = form.getFieldValue(['headers', name, 'fixed']);
                const headerKey = form.getFieldValue(['headers', name, 'key']);
                const isAuth = headerKey === 'Authorization';

                return (
                  <Space
                    key={key}
                    style={{ display: 'flex', marginBottom: 8, width: '100%' }}
                  >
                    <Form.Item
                      {...restField}
                      name={[name, 'key']}
                      style={{ flex: 1, minWidth: '140px' }}
                      rules={[
                        {
                          required: true,
                          message: t(
                            'components.createJobForm.headerNameRequired'
                          ),
                        },
                        {
                          max: 100,
                          message: t(
                            'components.createJobForm.headerNameLengthLimit'
                          ),
                        },
                      ]}
                    >
                      <Input
                        placeholder={
                          isFixed
                            ? t('components.createJobForm.systemHeader')
                            : t(
                                'components.createJobForm.headerNamePlaceholder'
                              )
                        }
                        disabled={isFixed}
                        maxLength={100}
                        style={
                          isFixed
                            ? {
                                backgroundColor: token.colorBgContainerDisabled,
                              }
                            : {}
                        }
                      />
                    </Form.Item>
                    <Form.Item
                      {...restField}
                      name={[name, 'value']}
                      style={{ flex: 2 }}
                      rules={[
                        {
                          max: 1000,
                          message: t(
                            'components.createJobForm.headerValueLengthLimit'
                          ),
                        },
                        ...(isAuth
                          ? [
                              {
                                required: false,
                                message:
                                  'Please enter API key (include Bearer prefix if required)',
                              },
                            ]
                          : []),
                      ]}
                    >
                      <Input
                        placeholder={
                          isAuth
                            ? t('components.createJobForm.pleaseEnterApiKey')
                            : t(
                                'components.createJobForm.headerValuePlaceholder'
                              )
                        }
                        disabled={isFixed}
                        maxLength={1000}
                        style={
                          isFixed
                            ? {
                                backgroundColor: token.colorBgContainerDisabled,
                              }
                            : {}
                        }
                      />
                    </Form.Item>
                    {!isFixed && (
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ marginTop: 8, color: token.colorTextTertiary }}
                      />
                    )}
                  </Space>
                );
              })}
              <Button
                type='dashed'
                onClick={() => add()}
                block
                icon={<PlusOutlined />}
                style={{ marginTop: 8 }}
              >
                {t('components.createJobForm.addHeaderButton')}
              </Button>
            </>
          )}
        </Form.List>
      </div>

      {/* Cookies */}
      <div
        style={{
          marginBottom: 24,
          padding: '16px',
          backgroundColor: token.colorFillAlter,
          borderRadius: '8px',
        }}
      >
        <div style={{ marginBottom: 12, fontWeight: 'bold', fontSize: '14px' }}>
          <Space>
            <span>{t('components.createJobForm.requestCookies')}</span>
            <Tooltip
              title={t('components.createJobForm.requestCookiesTooltip')}
            >
              <InfoCircleOutlined />
            </Tooltip>
          </Space>
        </div>
        <Form.List name='cookies'>
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => {
                return (
                  <Space
                    key={key}
                    style={{ display: 'flex', marginBottom: 8, width: '100%' }}
                  >
                    <Form.Item
                      {...restField}
                      name={[name, 'key']}
                      style={{ flex: 1, minWidth: '140px' }}
                      rules={[
                        {
                          required: true,
                          message: t(
                            'components.createJobForm.cookieNameRequired'
                          ),
                        },
                        {
                          max: 100,
                          message: t(
                            'components.createJobForm.cookieNameLengthLimit'
                          ),
                        },
                      ]}
                    >
                      <Input
                        placeholder={t(
                          'components.createJobForm.cookieNamePlaceholder'
                        )}
                        maxLength={100}
                      />
                    </Form.Item>
                    <Form.Item
                      {...restField}
                      name={[name, 'value']}
                      style={{ flex: 2 }}
                      rules={[
                        {
                          max: 1000,
                          message: t(
                            'components.createJobForm.cookieValueLengthLimit'
                          ),
                        },
                      ]}
                    >
                      <Input
                        placeholder={t(
                          'components.createJobForm.cookieValuePlaceholder'
                        )}
                        maxLength={1000}
                      />
                    </Form.Item>
                    <MinusCircleOutlined
                      onClick={() => remove(name)}
                      style={{ marginTop: 8, color: token.colorTextTertiary }}
                    />
                  </Space>
                );
              })}
              <Button
                type='dashed'
                onClick={() => add()}
                block
                icon={<PlusOutlined />}
                style={{ marginTop: 8 }}
              >
                {t('components.createJobForm.addCookieButton')}
              </Button>
            </>
          )}
        </Form.List>
      </div>

      {/* Client certificate upload */}
      <div
        style={{
          marginBottom: 24,
          padding: '16px',
          backgroundColor: token.colorFillAlter,
          borderRadius: '8px',
        }}
      >
        <div style={{ marginBottom: 12, fontWeight: 'bold', fontSize: '14px' }}>
          <Space>
            <span>{t('components.createJobForm.sslClientCertificate')}</span>
            <Tooltip
              title={t('components.createJobForm.sslClientCertificateTooltip')}
            >
              <InfoCircleOutlined />
            </Tooltip>
          </Space>
        </div>
        <div style={{ marginTop: '8px' }}>
          <Radio.Group
            defaultValue='combined'
            onChange={e => form.setFieldsValue({ cert_type: e.target.value })}
            style={{ marginBottom: 16 }}
          >
            <Radio value='combined'>
              {t('components.createJobForm.combinedCertificateKeyFile')}
            </Radio>
            <Radio value='separate'>
              {t('components.createJobForm.separateCertificateKeyFiles')}
            </Radio>
          </Radio.Group>

          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => {
              const certType = getFieldValue('cert_type') || 'combined';
              return certType === 'combined' ? (
                <div style={{ padding: '8px 0' }}>
                  <Upload
                    maxCount={1}
                    accept='.pem'
                    customRequest={handleCombinedCertUpload}
                    listType='text'
                    style={{ width: '100%' }}
                  >
                    <Button
                      icon={<UploadOutlined />}
                      size='middle'
                      style={{ width: '200px', height: '40px' }}
                    >
                      {t('components.createJobForm.selectCombinedPemFile')}
                    </Button>
                  </Upload>
                  <div
                    style={{
                      marginTop: 8,
                      color: token.colorTextSecondary,
                      fontSize: '12px',
                    }}
                  >
                    {t('components.createJobForm.combinedPemDescription')}
                  </div>
                </div>
              ) : (
                <div style={{ padding: '8px 0' }}>
                  <Space
                    direction='horizontal'
                    size='large'
                    style={{
                      width: '100%',
                      display: 'flex',
                      justifyContent: 'flex-start',
                    }}
                  >
                    <div>
                      <Upload
                        maxCount={1}
                        accept='.crt,.pem'
                        customRequest={handleCertFileUpload}
                        listType='text'
                      >
                        <Button
                          icon={<UploadOutlined />}
                          size='middle'
                          style={{ width: '180px', height: '40px' }}
                        >
                          {t('components.createJobForm.selectCertificate')}
                        </Button>
                      </Upload>
                      <div
                        style={{
                          marginTop: 4,
                          color: token.colorTextSecondary,
                          fontSize: '12px',
                        }}
                      >
                        {t('components.createJobForm.clientCertificate')} (.crt,
                        .pem)
                      </div>
                    </div>

                    <div>
                      <Upload
                        maxCount={1}
                        accept='.key,.pem'
                        customRequest={handleKeyFileUpload}
                        listType='text'
                      >
                        <Button
                          icon={<UploadOutlined />}
                          size='middle'
                          style={{ width: '180px', height: '40px' }}
                        >
                          {t('components.createJobForm.selectPrivateKey')}
                        </Button>
                      </Upload>
                      <div
                        style={{
                          marginTop: 4,
                          color: token.colorTextSecondary,
                          fontSize: '12px',
                        }}
                      >
                        {t('components.createJobForm.privateKeyFile')} (.key,
                        .pem)
                      </div>
                    </div>
                  </Space>
                </div>
              );
            }}
          </Form.Item>
        </div>
      </div>
    </div>
  );

  // Tab content rendering functions
  const renderTab1Content = () => (
    <div>
      {/* Section 1: Basic Configuration */}
      <div
        style={{
          margin: '32px 0 16px',
          fontWeight: 'bold',
          fontSize: '18px',
          paddingBottom: '8px',
        }}
      >
        <Space>
          <SettingOutlined />
          <span>{t('components.createJobForm.basicConfiguration')}</span>
        </Space>
      </div>

      <Row gutter={24}>
        <Col span={24}>
          <Form.Item
            name='name'
            label={t('components.createJobForm.taskName')}
            rules={[
              {
                required: true,
                message: t('components.createJobForm.pleaseEnterTaskName'),
              },
              {
                min: 1,
                max: 100,
                message: t('components.createJobForm.taskNameLengthLimit'),
              },
            ]}
            normalize={value => value?.trim() || ''}
          >
            <Input
              placeholder={t('components.createJobForm.taskNamePlaceholder')}
              maxLength={100}
              showCount
            />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={24}>
        <Col span={12}>
          <Form.Item
            name='api_type'
            label={t('components.createJobForm.apiType')}
            rules={[
              {
                required: true,
                message: t('components.createJobForm.pleaseSelectApiType'),
              },
            ]}
            required
          >
            <Select placeholder={t('components.createJobForm.apiType')}>
              <Select.Option value='openai-chat'>OpenAI Chat</Select.Option>
              <Select.Option value='claude-chat'>Claude Chat</Select.Option>
              <Select.Option value='embeddings'>Embeddings</Select.Option>
              <Select.Option value='custom-chat'>Custom Chat</Select.Option>
            </Select>
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name='model'
            label={
              <span>
                {t('components.createJobForm.modelName')}
                <Tooltip title={t('components.createJobForm.modelNameTooltip')}>
                  <InfoCircleOutlined style={{ marginLeft: 5 }} />
                </Tooltip>
              </span>
            }
            rules={[
              {
                max: 255,
                message: t('components.createJobForm.modelNameLengthLimit'),
              },
            ]}
            normalize={value => value?.trim() || ''}
          >
            <Input placeholder='e.g. gpt-4' maxLength={255} showCount />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={24}>
        <Col span={24}>
          <Form.Item
            name='api_url'
            label={
              <span>
                {t('components.createJobForm.apiEndpoint')}
                <Tooltip
                  title={t('components.createJobForm.apiEndpointTooltip')}
                >
                  <InfoCircleOutlined style={{ marginLeft: 5 }} />
                </Tooltip>
              </span>
            }
            required
          >
            <div style={{ display: 'flex', width: '100%' }}>
              <Form.Item
                name='target_host'
                noStyle
                rules={[
                  {
                    required: true,
                    message: t('components.createJobForm.pleaseEnterApiUrl'),
                  },
                  {
                    min: 1,
                    max: 255,
                    message: t('components.createJobForm.apiUrlLengthLimit'),
                  },
                  {
                    validator: (_, value) => {
                      if (!value?.trim()) return Promise.resolve();

                      const trimmedValue = value.trim();

                      // Check for spaces in URL
                      if (trimmedValue.includes(' ')) {
                        return Promise.reject(
                          new Error(
                            t('components.createJobForm.urlCannotContainSpaces')
                          )
                        );
                      }

                      // Check for proper protocol
                      if (
                        !trimmedValue.startsWith('http://') &&
                        !trimmedValue.startsWith('https://')
                      ) {
                        return Promise.reject(
                          new Error(
                            t('components.createJobForm.invalidUrlFormat')
                          )
                        );
                      }

                      try {
                        const url = new URL(trimmedValue);
                        if (!url.hostname || url.hostname.length === 0) {
                          return Promise.reject(
                            new Error(
                              t('components.createJobForm.invalidUrlFormat')
                            )
                          );
                        }
                        return Promise.resolve();
                      } catch (error) {
                        return Promise.reject(
                          new Error(
                            t('components.createJobForm.invalidUrlFormat')
                          )
                        );
                      }
                    },
                  },
                ]}
                normalize={value => value?.trim() || ''}
              >
                <Input
                  style={{ width: '70%' }}
                  placeholder='https://your-api-domain.com'
                  maxLength={255}
                />
              </Form.Item>
              <Form.Item
                name='api_path'
                noStyle
                rules={[
                  {
                    required: true,
                    message: t('components.createJobForm.pleaseEnterApiPath'),
                  },
                  {
                    min: 1,
                    max: 255,
                    message: t('components.createJobForm.apiPathLengthLimit'),
                  },
                  {
                    validator: (_, value) => {
                      if (!value?.trim()) return Promise.resolve();

                      const trimmedValue = value.trim();
                      if (!trimmedValue.startsWith('/')) {
                        return Promise.reject(
                          new Error(
                            t(
                              'components.createJobForm.apiPathMustStartWithSlash'
                            )
                          )
                        );
                      }
                      return Promise.resolve();
                    },
                  },
                ]}
                normalize={value => value?.trim() || ''}
              >
                <Input
                  style={{ width: '30%' }}
                  placeholder='/chat/completions'
                  maxLength={255}
                />
              </Form.Item>
            </div>
          </Form.Item>
        </Col>
      </Row>

      {/* Section 2: Request Configuration */}
      <div
        style={{
          margin: '32px 0 16px',
          fontWeight: 'bold',
          fontSize: '18px',
          paddingBottom: '8px',
        }}
      >
        <Space>
          <CloudOutlined />
          <span>{t('components.createJobForm.requestConfiguration')}</span>
        </Space>
      </div>

      {/* Request Method and Response Mode */}
      <Row gutter={24}>
        <Col span={12}>
          <Form.Item
            label={
              <span>
                {t('components.createJobForm.requestMethod')}
                <Tooltip
                  title={t('components.createJobForm.requestMethodTooltip')}
                >
                  <InfoCircleOutlined style={{ marginLeft: 5 }} />
                </Tooltip>
              </span>
            }
            required
          >
            <Input
              value='POST'
              disabled
              style={{ backgroundColor: token.colorBgContainerDisabled }}
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => {
              const currentApiType = getFieldValue('api_type') || 'openai-chat';
              const isEmbedType = currentApiType === 'embeddings';

              return (
                <Form.Item
                  name='stream_mode'
                  label={
                    <span>
                      {t('components.createJobForm.responseMode')}
                      <Tooltip
                        title={t(
                          'components.createJobForm.responseModeTooltip'
                        )}
                      >
                        <InfoCircleOutlined style={{ marginLeft: 5 }} />
                      </Tooltip>
                    </span>
                  }
                  rules={[
                    {
                      required: true,
                      message: t(
                        'components.createJobForm.pleaseSelectResponseMode'
                      ),
                    },
                  ]}
                >
                  <Select
                    placeholder={t('components.createJobForm.responseMode')}
                    disabled={isEmbedType}
                  >
                    <Select.Option value>
                      {t('components.createJobForm.stream')}
                    </Select.Option>
                    <Select.Option value={false}>
                      {t('components.createJobForm.nonStreaming')}
                    </Select.Option>
                  </Select>
                </Form.Item>
              );
            }}
          </Form.Item>
        </Col>
      </Row>

      {/* Request Payload - always show for all APIs */}
      <Row gutter={24}>
        <Col span={24}>
          <Form.Item
            name='request_payload'
            label={
              <span>
                {t('components.createJobForm.requestPayload')}
                <Tooltip
                  title={t('components.createJobForm.requestPayloadTooltip')}
                >
                  <InfoCircleOutlined style={{ marginLeft: 5 }} />
                </Tooltip>
              </span>
            }
            rules={[
              {
                max: 50000,
                message: t(
                  'components.createJobForm.requestPayloadLengthLimit'
                ),
              },
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (e) {
                    return Promise.reject(
                      new Error(
                        t('components.createJobForm.pleaseEnterValidJson')
                      )
                    );
                  }
                },
              },
            ]}
          >
            <TextArea
              autoSize={{ minRows: 3, maxRows: 12 }}
              placeholder='{"model":"your-model-name","stream": true,"stream_options": {"include_usage": true},"messages": [{"role": "user","content":"Hi"}]}'
              maxLength={50000}
              showCount
            />
          </Form.Item>
        </Col>
      </Row>

      {/* Advanced Settings - Collapsed by default */}
      <div>
        <Collapse
          ghost
          defaultActiveKey={[]}
          className='more-settings-collapse'
          items={[
            {
              key: 'advanced',
              label: (
                <span style={{ fontSize: '14px', lineHeight: '22px' }}>
                  {t('components.createJobForm.advancedSettings')}
                </span>
              ),
              children: advancedPanelContent,
              styles: { header: { paddingLeft: 0 } },
              forceRender: true,
            },
          ]}
        />
      </div>
    </div>
  );

  const renderTab2Content = () => (
    <div>
      {/* Section 3: Test Data */}
      <div
        style={{
          margin: '32px 0 16px',
          fontWeight: 'bold',
          fontSize: '18px',
          paddingBottom: '8px',
        }}
      >
        <Space>
          <DatabaseOutlined />
          <span>{t('components.createJobForm.testData')}</span>
        </Space>
      </div>

      {/* Dataset Type Specific Options */}
      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const inputType = getFieldValue('test_data_input_type');
          const currentApiType = getFieldValue('api_type') || 'openai-chat';
          const isChatApi =
            currentApiType === 'openai-chat' ||
            currentApiType === 'claude-chat';

          const cardStyle = {
            background: token.colorFillAlter,
            borderRadius: 12,
            boxShadow: token.boxShadowTertiary,
            border: `1px solid ${token.colorBorder}`,
          };

          const cardBodyStyle = { padding: '16px 20px' };
          const cardProps: CardProps = {
            variant: 'borderless',
            style: cardStyle,
            bodyStyle: cardBodyStyle,
          };

          const renderBuiltInDatasetPanel = () => {
            if (!isChatApi) {
              return null;
            }

            return (
              <Form.Item
                name='chat_type'
                label={
                  <Space size={6}>
                    <span>{t('components.createJobForm.datasetType')}</span>
                  </Space>
                }
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createJobForm.pleaseSelectDatasetType'
                    ),
                  },
                  {
                    type: 'number',
                    min: 0,
                    max: 2,
                    message: t('components.createJobForm.chatTypeRangeLimit'),
                  },
                ]}
              >
                <Select
                  size='large'
                  placeholder={t('components.createJobForm.datasetType')}
                >
                  <Select.Option value={0}>
                    {t('components.createJobForm.datasetOptionTextSelfBuilt')}
                  </Select.Option>
                  <Select.Option value={1}>
                    {t('components.createJobForm.datasetOptionShareGPTPartial')}
                  </Select.Option>
                  <Select.Option value={2}>
                    {t('components.createJobForm.datasetOptionVisionSelfBuilt')}
                  </Select.Option>
                </Select>
              </Form.Item>
            );
          };

          const renderUploadDatasetPanel = () => (
            <Form.Item
              name='test_data_file'
              style={{ marginBottom: 0 }}
              rules={[
                {
                  required: inputType === 'upload',
                  message: t(
                    'components.createJobForm.pleaseUploadDatasetFile'
                  ),
                },
              ]}
            >
              <Upload.Dragger
                maxCount={1}
                accept='.json,.jsonl'
                customRequest={handleDatasetFileUpload}
                onRemove={handleDatasetFileRemove}
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
                  {t('components.createJobForm.selectDatasetFile')}
                </Text>
                <div
                  style={{
                    marginTop: 12,
                    color: token.colorTextSecondary,
                    fontSize: 12,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                  }}
                >
                  <span style={{ whiteSpace: 'pre-line' }}>
                    {t('components.createJobForm.datasetFileFormatDescription')}
                  </span>
                  <span>
                    {t('components.createJobForm.datasetImageMountWarning')}
                  </span>
                </div>
              </Upload.Dragger>
            </Form.Item>
          );

          const renderManualDatasetPanel = () => (
            <Card {...cardProps}>
              <Space direction='vertical' size={12} style={{ width: '100%' }}>
                <Text strong>{t('components.createJobForm.jsonlData')}</Text>
                <Text type='secondary' style={{ fontSize: 12 }}>
                  {t('components.createJobForm.jsonlDataTooltip')}
                </Text>
                <Form.Item
                  name='test_data'
                  style={{ marginBottom: 0 }}
                  rules={[
                    {
                      required: inputType === 'input',
                      message: t(
                        'components.createJobForm.pleaseEnterJsonlData'
                      ),
                    },
                    {
                      validator: (_, value) => {
                        if (inputType !== 'input' || !value) {
                          return Promise.resolve();
                        }
                        try {
                          const lines = value
                            .trim()
                            .split('\n')
                            .filter(line => line.trim());
                          lines.forEach(line => {
                            const jsonObj = JSON.parse(line);
                            if (!jsonObj.id || !jsonObj.prompt) {
                              throw new Error(
                                t(
                                  'components.createJobForm.eachLineMustContainFields'
                                )
                              );
                            }
                          });
                          return Promise.resolve();
                        } catch (e) {
                          return Promise.reject(
                            new Error(
                              t('components.createJobForm.invalidJsonlFormat')
                            )
                          );
                        }
                      },
                    },
                  ]}
                >
                  <TextArea
                    rows={6}
                    placeholder={`{"id": "1", "prompt": "Hello, how are you?"}\n{"id": "2", "prompt": "What is artificial intelligence?"}\n{"id": "3", "prompt": "Explain machine learning in simple terms"}`}
                    maxLength={50000}
                    showCount
                    style={{
                      fontFamily: 'Monaco, Consolas, "Courier New", monospace',
                    }}
                  />
                </Form.Item>
              </Space>
            </Card>
          );

          let additionalContent: React.ReactNode = null;
          if (inputType === 'default') {
            additionalContent = renderBuiltInDatasetPanel();
          } else if (inputType === 'upload') {
            additionalContent = renderUploadDatasetPanel();
          } else if (inputType === 'input') {
            additionalContent = renderManualDatasetPanel();
          }

          const datasetSourceTooltip = t(
            'components.createJobForm.datasetSourceTooltip'
          );

          return (
            <Space
              direction='vertical'
              size={16}
              style={{ display: 'flex', width: '100%' }}
            >
              <Form.Item
                name='test_data_input_type'
                label={
                  <span>
                    {t('components.createJobForm.datasetSource')}
                    <Tooltip title={datasetSourceTooltip}>
                      <InfoCircleOutlined style={{ marginLeft: 5 }} />
                    </Tooltip>
                  </span>
                }
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createJobForm.pleaseSelectDatasetSource'
                    ),
                  },
                ]}
                style={{ marginBottom: 0 }}
              >
                <Select
                  size='large'
                  placeholder={t('components.createJobForm.datasetSource')}
                >
                  <Select.Option value='default'>
                    {t('components.createJobForm.builtInDataset')}
                  </Select.Option>
                  <Select.Option value='input'>
                    {t('components.createJobForm.customJsonlData')}
                  </Select.Option>
                  <Select.Option value='upload'>
                    {t('components.createJobForm.uploadJsonlFile')}
                  </Select.Option>
                  <Select.Option value='none'>
                    {t('components.createJobForm.noDataset')}
                  </Select.Option>
                </Select>
              </Form.Item>
              {additionalContent}
            </Space>
          );
        }}
      </Form.Item>

      {/* Section 4: Load Configuration */}
      <div
        style={{
          margin: '32px 0 16px',
          fontWeight: 'bold',
          fontSize: '18px',
          paddingBottom: '8px',
        }}
      >
        <Space>
          <RocketOutlined />
          <span>{t('components.createJobForm.loadConfiguration')}</span>
        </Space>
      </div>

      {/* Load mode selector: fixed concurrency vs stepped */}
      <Form.Item
        label={t('components.createJobForm.loadMode')}
        name='load_mode'
        required
      >
        <Radio.Group>
          <Radio.Button value='fixed'>
            {t('components.createJobForm.loadModeFixed')}
          </Radio.Button>
          <Radio.Button value='stepped'>
            {t('components.createJobForm.loadModeStepped')}
          </Radio.Button>
        </Radio.Group>
      </Form.Item>

      {/* Fixed concurrency configuration */}
      {loadMode === 'fixed' && (
        <Row gutter={24}>
          <Col span={8}>
            <Form.Item
              name='duration'
              label={
                <span>
                  {t('components.createJobForm.testDuration')}
                  <Tooltip
                    title={t('components.createJobForm.testDurationTooltip')}
                  >
                    <InfoCircleOutlined style={{ marginLeft: 5 }} />
                  </Tooltip>
                </span>
              }
              rules={[
                {
                  required: loadMode === 'fixed',
                  message: t(
                    'components.createJobForm.pleaseEnterTestDuration'
                  ),
                },
                {
                  type: 'number',
                  min: 1,
                  max: 172800,
                  message: t('components.createJobForm.durationRangeLimit'),
                },
              ]}
            >
              <InputNumber
                min={1}
                max={172800}
                style={{ width: '100%' }}
                placeholder='60'
              />
            </Form.Item>
          </Col>

          <Col span={8}>
            <Form.Item
              name='concurrent_users'
              label={
                <span>
                  {t('components.createJobForm.concurrentUsers')}
                  <Tooltip
                    title={t('components.createJobForm.concurrentUsersTooltip')}
                  >
                    <InfoCircleOutlined style={{ marginLeft: 5 }} />
                  </Tooltip>
                </span>
              }
              rules={[
                {
                  required: loadMode === 'fixed',
                  message: t(
                    'components.createJobForm.pleaseEnterConcurrentUsers'
                  ),
                },
                {
                  type: 'number',
                  min: 1,
                  max: 5000,
                  message: t(
                    'components.createJobForm.concurrentUsersRangeLimit'
                  ),
                },
              ]}
            >
              <InputNumber
                min={1}
                max={5000}
                style={{ width: '100%' }}
                placeholder='10'
                onChange={handleConcurrentUsersChange}
              />
            </Form.Item>
          </Col>

          <Col span={8}>
            <Form.Item
              name='spawn_rate'
              label={
                <span>
                  {t('components.createJobForm.userSpawnRate')}
                  <Tooltip
                    title={t('components.createJobForm.userSpawnRateTooltip')}
                  >
                    <InfoCircleOutlined style={{ marginLeft: 5 }} />
                  </Tooltip>
                </span>
              }
              rules={[
                {
                  required: loadMode === 'fixed',
                  message: t('components.createJobForm.pleaseEnterSpawnRate'),
                },
                {
                  type: 'number',
                  min: 1,
                  max: 1000,
                  message: t('components.createJobForm.spawnRateRangeLimit'),
                },
              ]}
            >
              <InputNumber
                min={1}
                max={1000}
                style={{ width: '100%' }}
                placeholder='1'
                onChange={handleSpawnRateChange}
              />
            </Form.Item>
          </Col>
        </Row>
      )}

      {/* Stepped load configuration */}
      {loadMode === 'stepped' && (
        <>
          <Row gutter={24}>
            <Col span={8}>
              <Form.Item
                label={t('components.createJobForm.stepStartUsers')}
                name='step_start_users'
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createJobForm.stepStartUsersRequired'
                    ),
                  },
                ]}
              >
                <InputNumber min={1} max={5000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label={t('components.createJobForm.stepIncrement')}
                name='step_increment'
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createJobForm.stepIncrementRequired'
                    ),
                  },
                ]}
              >
                <InputNumber min={1} max={5000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label={t('components.createJobForm.stepDuration')}
                name='step_duration'
                tooltip={t('components.createJobForm.stepDurationTip')}
                rules={[
                  {
                    required: true,
                    message: t('components.createJobForm.stepDurationRequired'),
                  },
                ]}
              >
                <InputNumber min={5} max={3600} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={24}>
            <Col span={12}>
              <Form.Item
                label={t('components.createJobForm.stepMaxUsers')}
                name='step_max_users'
                rules={[
                  {
                    required: true,
                    message: t('components.createJobForm.stepMaxUsersRequired'),
                  },
                ]}
              >
                <InputNumber min={1} max={10000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label={t('components.createJobForm.stepSustainDuration')}
                name='step_sustain_duration'
                tooltip={t('components.createJobForm.stepSustainDurationTip')}
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createJobForm.stepSustainDurationRequired'
                    ),
                  },
                ]}
              >
                <InputNumber min={1} max={172800} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </>
      )}

      {/* Section 5: Warmup Configuration */}
      <div
        style={{
          margin: '32px 0 16px',
          fontWeight: 'bold',
          fontSize: '18px',
          paddingBottom: '8px',
        }}
      >
        <Space>
          <FireOutlined />
          <span>{t('components.createJobForm.warmupConfiguration')}</span>
        </Space>
      </div>

      <Row gutter={24} align='middle'>
        <Col span={12}>
          <Form.Item
            name='warmup_enabled'
            label={
              <span>
                {t('components.createJobForm.warmupMode')}
                <Tooltip
                  title={t('components.createJobForm.warmupModeTooltip')}
                >
                  <InfoCircleOutlined style={{ marginLeft: 5 }} />
                </Tooltip>
              </span>
            }
            rules={[
              {
                required: true,
                message: t('components.createJobForm.pleaseSelectWarmupMode'),
              },
            ]}
          >
            <Radio.Group>
              <Radio value>{t('components.createJobForm.warmupEnabled')}</Radio>
              <Radio value={false}>
                {t('components.createJobForm.warmupDisabled')}
              </Radio>
            </Radio.Group>
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => {
              const warmupEnabled = getFieldValue('warmup_enabled');
              return (
                <Form.Item
                  name='warmup_duration'
                  label={t('components.createJobForm.warmupDuration')}
                  rules={[
                    {
                      required: warmupEnabled === true,
                      message: t(
                        'components.createJobForm.pleaseEnterWarmupDuration'
                      ),
                    },
                    {
                      type: 'number',
                      min: 10,
                      max: 1800,
                      message: t(
                        'components.createJobForm.warmupDurationRangeLimit'
                      ),
                    },
                  ]}
                >
                  <InputNumber
                    min={10}
                    max={1800}
                    disabled={warmupEnabled === false}
                    style={{
                      width: '120px',
                      backgroundColor:
                        warmupEnabled === false
                          ? token.colorBgContainerDisabled
                          : undefined,
                    }}
                    addonAfter='s'
                    placeholder='120'
                  />
                </Form.Item>
              );
            }}
          </Form.Item>
        </Col>
      </Row>
    </div>
  );

  // Field mapping section
  const fieldMappingSection = (
    <div
      style={{ marginBottom: 24, marginLeft: '8px' }}
      className='field-mapping-section'
    >
      <div
        style={{
          marginBottom: '16px',
          color: token.colorTextSecondary,
          fontSize: '14px',
          lineHeight: '1.5',
        }}
      >
        {t('components.createJobForm.fieldMappingDescription')}
      </div>

      {/* Prompt Field Path - always show for all APIs */}
      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const currentApiType = getFieldValue('api_type') || 'openai-chat';
          const isEmbedType = currentApiType === 'embeddings';

          // Get placeholder based on API type
          const getPromptPlaceholder = () => {
            switch (currentApiType) {
              case 'openai-chat':
                return 'messages.0.content.-1.text';
              case 'claude-chat':
                return 'messages.0.content.-1.text';
              case 'embeddings':
                return 'input';
              case 'custom-chat':
                return 'e.g. query, prompt, input';
              default:
                return 'e.g. query, prompt, input, message';
            }
          };

          const getImagePlaceholder = () => {
            switch (currentApiType) {
              case 'openai-chat':
                return 'messages.0.content.0.image_url';
              case 'claude-chat':
                return 'messages.0.content.0.source.data';
              case 'custom-chat':
                return 'e.g. image, image_url, image_base64';
              default:
                return '';
            }
          };

          return (
            <div
              style={{
                marginBottom: 24,
                padding: '16px',
                backgroundColor: token.colorFillAlter,
                borderRadius: '8px',
              }}
            >
              <div
                style={{
                  marginBottom: 12,
                  fontWeight: 'bold',
                  fontSize: '14px',
                }}
              >
                {t('components.createJobForm.requestFieldMapping')}
              </div>
              <Row gutter={24}>
                <Col span={isEmbedType ? 24 : 12}>
                  <Form.Item
                    name={['field_mapping', 'prompt']}
                    label={
                      <span>
                        {t('components.createJobForm.promptFieldPath')}
                        <Tooltip
                          title={t(
                            'components.createJobForm.promptFieldPathTooltip'
                          )}
                        >
                          <InfoCircleOutlined style={{ marginLeft: 5 }} />
                        </Tooltip>
                      </span>
                    }
                    rules={[
                      {
                        required: true,
                        message: t(
                          'components.createJobForm.pleaseSpecifyPromptFieldPath'
                        ),
                      },
                    ]}
                    required
                  >
                    <Input placeholder={getPromptPlaceholder()} />
                  </Form.Item>
                </Col>
                {!isEmbedType && (
                  <Col span={12}>
                    <Form.Item
                      name={['field_mapping', 'image']}
                      label={
                        <span>
                          {t('components.createJobForm.imageFieldPath')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.imageFieldPathTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                    >
                      <Input placeholder={getImagePlaceholder()} />
                    </Form.Item>
                  </Col>
                )}
              </Row>
            </div>
          );
        }}
      </Form.Item>

      {/* Only show response field mapping for non-embed types */}
      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const currentApiType = getFieldValue('api_type') || 'openai-chat';
          const isEmbedType = currentApiType === 'embeddings';

          // Get placeholders based on API type
          const getContentPlaceholder = () => {
            if (currentApiType === 'claude-chat') {
              return streamMode ? 'content.-1.text' : 'content.-1.text';
            }
            return streamMode
              ? 'choices.0.delta.content'
              : 'choices.0.message.content';
          };

          const getReasoningPlaceholder = () => {
            if (currentApiType === 'claude-chat') {
              return streamMode ? 'content.0.thinking' : 'content.0.thinking';
            }
            return streamMode
              ? 'choices.0.delta.reasoning_content'
              : 'choices.0.message.reasoning_content';
          };

          const getPromptTokensPlaceholder = () => {
            return currentApiType === 'claude-chat'
              ? 'usage.input_tokens'
              : 'usage.prompt_tokens';
          };

          const getCompletionTokensPlaceholder = () => {
            return currentApiType === 'claude-chat'
              ? 'usage.output_tokens'
              : 'usage.completion_tokens';
          };

          const getEndFieldPlaceholder = () => {
            return currentApiType === 'claude-chat'
              ? 'type'
              : 'choices.0.finish_reason';
          };

          const getStopFlagPlaceholder = () => {
            return currentApiType === 'claude-chat' ? 'message_stop' : 'stop';
          };

          // Don't show response fields for embed types
          if (isEmbedType) {
            return null;
          }

          return streamMode ? (
            // Streaming mode configuration
            <>
              {/* Stream Data Configuration */}
              <div
                style={{
                  marginBottom: 24,
                  padding: '16px',
                  backgroundColor: token.colorFillAlter,
                  borderRadius: '8px',
                }}
              >
                <div
                  style={{
                    marginBottom: 16,
                    fontWeight: 'bold',
                    fontSize: '14px',
                    color: token.colorText,
                  }}
                >
                  {t('components.createJobForm.streamingResponseConfiguration')}
                </div>

                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={12}>
                    <Form.Item
                      name={['field_mapping', 'stream_prefix']}
                      label={
                        <span>
                          {t('components.createJobForm.streamLinePrefix')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.streamLinePrefixTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                    >
                      <Input placeholder='data:' />
                    </Form.Item>
                  </Col>

                  <Col span={12}>
                    <Form.Item
                      name={['field_mapping', 'data_format']}
                      label={
                        <span>
                          {t('components.createJobForm.dataFormat')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.dataFormatTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                      rules={[
                        {
                          required: true,
                          message: t(
                            'components.createJobForm.pleaseSelectDataFormat'
                          ),
                        },
                      ]}
                    >
                      <Select
                        placeholder={t('components.createJobForm.dataFormat')}
                      >
                        <Select.Option value='json'>
                          {t('components.createJobForm.jsonFormat')}
                        </Select.Option>
                        <Select.Option value='non-json'>
                          {t('components.createJobForm.plainText')}
                        </Select.Option>
                      </Select>
                    </Form.Item>
                  </Col>
                </Row>

                {/* Content Field Configuration - only show when data format is JSON */}
                <Form.Item noStyle shouldUpdate>
                  {({ getFieldValue }) => {
                    const dataFormat =
                      getFieldValue(['field_mapping', 'data_format']) || 'json';
                    return (
                      dataFormat === 'json' && (
                        <>
                          <Row gutter={24}>
                            <Col span={12}>
                              <Form.Item
                                name={['field_mapping', 'content']}
                                label={
                                  <span>
                                    {t(
                                      'components.createJobForm.contentFieldPath'
                                    )}
                                    <Tooltip
                                      title={t(
                                        'components.createJobForm.contentFieldPathTooltip'
                                      )}
                                    >
                                      <InfoCircleOutlined
                                        style={{ marginLeft: 5 }}
                                      />
                                    </Tooltip>
                                  </span>
                                }
                              >
                                <Input placeholder={getContentPlaceholder()} />
                              </Form.Item>
                            </Col>

                            <Col span={12}>
                              <Form.Item
                                name={['field_mapping', 'reasoning_content']}
                                label={
                                  <span>
                                    {t(
                                      'components.createJobForm.reasoningFieldPath'
                                    )}
                                    <Tooltip
                                      title={t(
                                        'components.createJobForm.reasoningFieldPathTooltip'
                                      )}
                                    >
                                      <InfoCircleOutlined
                                        style={{ marginLeft: 5 }}
                                      />
                                    </Tooltip>
                                  </span>
                                }
                              >
                                <Input
                                  placeholder={getReasoningPlaceholder()}
                                />
                              </Form.Item>
                            </Col>
                          </Row>

                          <Row gutter={16} style={{ marginTop: 16 }}>
                            <Col span={8}>
                              <Form.Item
                                name={['field_mapping', 'prompt_tokens']}
                                label={
                                  <span>
                                    {t(
                                      'components.createJobForm.promptTokensFieldPath'
                                    )}
                                    <Tooltip
                                      title={t(
                                        'components.createJobForm.promptTokensFieldPathTooltip'
                                      )}
                                    >
                                      <InfoCircleOutlined
                                        style={{ marginLeft: 5 }}
                                      />
                                    </Tooltip>
                                  </span>
                                }
                              >
                                <Input
                                  placeholder={getPromptTokensPlaceholder()}
                                />
                              </Form.Item>
                            </Col>

                            <Col span={8}>
                              <Form.Item
                                name={['field_mapping', 'completion_tokens']}
                                label={
                                  <span>
                                    {t(
                                      'components.createJobForm.completionTokensFieldPath'
                                    )}
                                    <Tooltip
                                      title={t(
                                        'components.createJobForm.completionTokensFieldPathTooltip'
                                      )}
                                    >
                                      <InfoCircleOutlined
                                        style={{ marginLeft: 5 }}
                                      />
                                    </Tooltip>
                                  </span>
                                }
                              >
                                <Input
                                  placeholder={getCompletionTokensPlaceholder()}
                                />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item
                                name={['field_mapping', 'total_tokens']}
                                label={
                                  <span>
                                    {t(
                                      'components.createJobForm.totalTokensFieldPath'
                                    )}
                                    <Tooltip
                                      title={t(
                                        'components.createJobForm.totalTokensFieldPathTooltip'
                                      )}
                                    >
                                      <InfoCircleOutlined
                                        style={{ marginLeft: 5 }}
                                      />
                                    </Tooltip>
                                  </span>
                                }
                              >
                                <Input placeholder='usage.total_tokens' />
                              </Form.Item>
                            </Col>
                          </Row>
                        </>
                      )
                    );
                  }}
                </Form.Item>
              </div>

              {/* End Condition Configuration */}
              <div
                style={{
                  marginBottom: 24,
                  padding: '16px',
                  backgroundColor: token.colorFillAlter,
                  borderRadius: '8px',
                }}
              >
                <div
                  style={{
                    marginBottom: 16,
                    fontWeight: 'bold',
                    fontSize: '14px',
                    color: token.colorText,
                  }}
                >
                  {t('components.createJobForm.streamTerminationConfiguration')}
                </div>

                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item
                      name={['field_mapping', 'end_prefix']}
                      label={
                        <span>
                          {t('components.createJobForm.endLinePrefix')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.endLinePrefixTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                    >
                      <Input placeholder='data:' />
                    </Form.Item>
                  </Col>

                  <Col span={8}>
                    <Form.Item
                      name={['field_mapping', 'end_field']}
                      label={
                        <span>
                          {t('components.createJobForm.endFieldPath')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.endFieldPathTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                    >
                      <Input placeholder={getEndFieldPlaceholder()} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item
                      name={['field_mapping', 'stop_flag']}
                      label={
                        <span>
                          {t('components.createJobForm.stopSignal')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.stopSignalTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                      rules={[
                        {
                          required: true,
                          message: t(
                            'components.createJobForm.pleaseSpecifyStopSignal'
                          ),
                        },
                      ]}
                      required
                    >
                      <Input placeholder={getStopFlagPlaceholder()} />
                    </Form.Item>
                  </Col>
                </Row>
              </div>
            </>
          ) : (
            // Non-streaming mode configuration
            <div
              style={{
                padding: '16px',
                backgroundColor: token.colorFillAlter,
                borderRadius: '8px',
              }}
            >
              <div
                style={{
                  marginBottom: 16,
                  fontWeight: 'bold',
                  fontSize: '14px',
                  color: token.colorText,
                }}
              >
                {t(
                  'components.createJobForm.nonStreamingResponseConfiguration'
                )}
              </div>
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name={['field_mapping', 'content']}
                    label={
                      <span>
                        {t('components.createJobForm.contentFieldPath')}
                        <Tooltip
                          title={t(
                            'components.createJobForm.nonStreamingContentFieldPathTooltip'
                          )}
                        >
                          <InfoCircleOutlined style={{ marginLeft: 5 }} />
                        </Tooltip>
                      </span>
                    }
                  >
                    <Input placeholder={getContentPlaceholder()} />
                  </Form.Item>
                </Col>

                <Col span={12}>
                  <Form.Item
                    name={['field_mapping', 'reasoning_content']}
                    label={
                      <span>
                        {t('components.createJobForm.reasoningFieldPath')}
                        <Tooltip
                          title={t(
                            'components.createJobForm.nonStreamingReasoningFieldPathTooltip'
                          )}
                        >
                          <InfoCircleOutlined style={{ marginLeft: 5 }} />
                        </Tooltip>
                      </span>
                    }
                  >
                    <Input placeholder={getReasoningPlaceholder()} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16} style={{ marginTop: 16 }}>
                <Col span={8}>
                  <Form.Item
                    name={['field_mapping', 'prompt_tokens']}
                    label={
                      <span>
                        {t('components.createJobForm.promptTokensFieldPath')}
                        <Tooltip
                          title={t(
                            'components.createJobForm.promptTokensFieldPathTooltip'
                          )}
                        >
                          <InfoCircleOutlined style={{ marginLeft: 5 }} />
                        </Tooltip>
                      </span>
                    }
                  >
                    <Input placeholder={getPromptTokensPlaceholder()} />
                  </Form.Item>
                </Col>

                <Col span={8}>
                  <Form.Item
                    name={['field_mapping', 'completion_tokens']}
                    label={
                      <span>
                        {t(
                          'components.createJobForm.completionTokensFieldPath'
                        )}
                        <Tooltip
                          title={t(
                            'components.createJobForm.completionTokensFieldPathTooltip'
                          )}
                        >
                          <InfoCircleOutlined style={{ marginLeft: 5 }} />
                        </Tooltip>
                      </span>
                    }
                  >
                    <Input placeholder={getCompletionTokensPlaceholder()} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    name={['field_mapping', 'total_tokens']}
                    label={
                      <span>
                        {t('components.createJobForm.totalTokensFieldPath')}
                        <Tooltip
                          title={t(
                            'components.createJobForm.totalTokensFieldPathTooltip'
                          )}
                        >
                          <InfoCircleOutlined style={{ marginLeft: 5 }} />
                        </Tooltip>
                      </span>
                    }
                  >
                    <Input placeholder='usage.total_tokens' />
                  </Form.Item>
                </Col>
              </Row>
              {/* <Row gutter={24} style={{ marginTop: 16 }}>
            <Col span={12}>
              <Form.Item
                name={['field_mapping', 'usage']}
                label={
                  <span>
                    {t('components.createJobForm.usageFieldPath')}
                    <Tooltip
                      title={t(
                        'components.createJobForm.usageFieldPathTooltip'
                      )}
                    >
                      <InfoCircleOutlined style={{ marginLeft: 5 }} />
                    </Tooltip>
                  </span>
                }
              >
                <Input placeholder='usage' />
              </Form.Item>
            </Col>
          </Row> */}
            </div>
          );
        }}
      </Form.Item>
    </div>
  );

  const renderTab3Content = () => (
    <div>
      {/* Section 5: API Field Mapping */}
      <div
        style={{
          margin: '32px 0 16px',
          fontWeight: 'bold',
          fontSize: '18px',
          paddingBottom: '8px',
        }}
      >
        <Space>
          <ApiOutlined />
          <span>{t('components.createJobForm.apiFieldMapping')}</span>
        </Space>
      </div>

      {fieldMappingSection}
    </div>
  );

  // Render tab action buttons
  const renderTabActions = () => {
    const isStandardChatApi =
      watchedApiType === 'openai-chat' || watchedApiType === 'claude-chat';

    if (activeTabKey === '1') {
      return (
        <Space>
          <Button
            type='primary'
            icon={<BugOutlined />}
            onClick={handleTestAPI}
            loading={testing}
            disabled={!isFormValidForTest()}
          >
            {t('components.createJobForm.testIt')}
          </Button>
          <Button onClick={onCancel}>{t('common.cancel')}</Button>
          <Button
            type='primary'
            htmlType='button'
            icon={<RightOutlined />}
            onClick={handleNextTab}
          >
            {t('components.createJobForm.nextStep')}
          </Button>
        </Space>
      );
    }
    if (activeTabKey === '2') {
      // Tab 2 can be either Field Mapping or Data/Load depending on API type
      if (isStandardChatApi) {
        // This is the final tab for standard chat APIs
        return (
          <Space>
            <Button icon={<LeftOutlined />} onClick={goToPreviousTab}>
              {t('components.createJobForm.previousStep')}
            </Button>
            <Button onClick={onCancel}>{t('common.cancel')}</Button>
            <Button
              type='primary'
              loading={submitting || uploading}
              onClick={handleSubmit}
            >
              {submitting || uploading
                ? uploading
                  ? t('components.createJobForm.uploading')
                  : t('components.createJobForm.submitting')
                : t('components.createJobForm.create')}
            </Button>
          </Space>
        );
      }
      // This is the Field Mapping tab, not the final tab
      return (
        <Space>
          <Button icon={<LeftOutlined />} onClick={goToPreviousTab}>
            {t('components.createJobForm.previousStep')}
          </Button>
          <Button onClick={onCancel}>{t('common.cancel')}</Button>
          <Button
            type='primary'
            htmlType='button'
            icon={<RightOutlined />}
            onClick={handleNextTab}
          >
            {t('components.createJobForm.nextStep')}
          </Button>
        </Space>
      );
    }
    if (activeTabKey === '3') {
      // Tab 3 is always the final Data/Load tab for custom-chat and embeddings
      return (
        <Space>
          <Button icon={<LeftOutlined />} onClick={goToPreviousTab}>
            {t('components.createJobForm.previousStep')}
          </Button>
          <Button onClick={onCancel}>{t('common.cancel')}</Button>
          <Button
            type='primary'
            loading={submitting || uploading}
            onClick={handleSubmit}
          >
            {submitting || uploading
              ? uploading
                ? t('components.createJobForm.uploading')
                : t('components.createJobForm.submitting')
              : t('components.createJobForm.create')}
          </Button>
        </Space>
      );
    }
  };

  return (
    <Card
      className='form-card'
      styles={{
        body: { padding: '24px', boxShadow: token.boxShadowTertiary },
      }}
    >
      <Form
        form={form}
        layout='vertical'
        initialValues={{
          api_type: 'openai-chat',
          headers: [
            { key: 'Content-Type', value: 'application/json', fixed: true },
            { key: 'Authorization', value: '', fixed: false },
          ],
          cookies: [],
          stream_mode: true,
          spawn_rate: 1,
          concurrent_users: 1,
          chat_type: 0,
          test_data_input_type: 'default',
          temp_task_id: tempTaskId,
          target_host: '',
          api_path: '/v1/chat/completions',
          duration: '',
          model: '',
          request_payload: generateDefaultPayload('openai-chat', '', true),
          field_mapping: getDefaultFieldMapping('openai-chat'),
          warmup_enabled: true,
          warmup_duration: 120,
          load_mode: 'fixed',
          step_start_users: 10,
          step_increment: 10,
          step_duration: 30,
          step_max_users: 100,
          step_sustain_duration: 60,
        }}
        onFinish={handleSubmit}
        onValuesChange={changedValues => {
          // Skip sync logic when we are already syncing internally
          if (isSyncingRef.current) {
            // Still handle non-payload related changes even during sync
            if ('warmup_enabled' in changedValues) {
              const warmupEnabled = changedValues.warmup_enabled;
              const currentWarmupDuration =
                form.getFieldValue('warmup_duration');
              if (warmupEnabled === false) {
                form.setFieldsValue({
                  warmup_duration: currentWarmupDuration ?? 120,
                });
              } else if (warmupEnabled === true) {
                if (
                  currentWarmupDuration === undefined ||
                  currentWarmupDuration === null
                ) {
                  form.setFieldsValue({ warmup_duration: 120 });
                }
              }
            }
            if ('concurrent_users' in changedValues) {
              setConcurrentUsers(changedValues.concurrent_users);
            }
            if ('stream_mode' in changedValues) {
              setStreamMode(changedValues.stream_mode);
            }
          } else {
            // Handle API type changes — regenerate entire payload since structure differs
            if ('api_type' in changedValues && !isCopyMode) {
              const newApiType = changedValues.api_type;

              // Update api_path based on API type
              const newApiPath = getDefaultApiPath(newApiType);
              form.setFieldsValue({ api_path: newApiPath });

              // Update stream_mode for embed types
              const isEmbedType = newApiType === 'embeddings';
              if (isEmbedType) {
                form.setFieldsValue({ stream_mode: false });
                setStreamMode(false);
              }

              // Update field_mapping based on API type
              const newFieldMapping = getDefaultFieldMapping(newApiType);
              form.setFieldsValue({ field_mapping: newFieldMapping });

              // Regenerate entire payload for new API type
              isSyncingRef.current = true;
              const currentStreamMode = isEmbedType
                ? false
                : form.getFieldValue('stream_mode');
              const currentModel = form.getFieldValue('model') || '';
              const newPayload = generateDefaultPayload(
                newApiType,
                currentModel,
                currentStreamMode
              );
              form.setFieldsValue({ request_payload: newPayload });
              isSyncingRef.current = false;

              // Reset to tab 1 when API type changes to ensure proper tab navigation
              setActiveTabKey('1');
            }

            // Handle stream_mode changes — update only `stream` field in payload JSON
            if ('stream_mode' in changedValues) {
              setStreamMode(changedValues.stream_mode);
              // Update field_mapping default values when stream mode changes (but not in copy mode)
              if (!isCopyMode) {
                const currentApiType =
                  form.getFieldValue('api_type') || 'openai-chat';
                const newFieldMapping = getDefaultFieldMapping(currentApiType);
                form.setFieldsValue({ field_mapping: newFieldMapping });
              }

              // Update `stream` field in the existing payload JSON
              isSyncingRef.current = true;
              const updatedPayload = updatePayloadFields({
                stream: changedValues.stream_mode,
              });
              if (updatedPayload) {
                form.setFieldsValue({ request_payload: updatedPayload });
              }
              isSyncingRef.current = false;
            }

            // Handle model changes — update only `model` field in payload JSON
            if ('model' in changedValues) {
              isSyncingRef.current = true;
              const modelValue = changedValues.model?.trim() || 'none';
              const updatedPayload = updatePayloadFields({
                model: modelValue,
              });
              if (updatedPayload) {
                form.setFieldsValue({ request_payload: updatedPayload });
              }
              isSyncingRef.current = false;
            }

            // Handle request_payload changes — reverse sync model and stream_mode back to form fields
            if ('request_payload' in changedValues) {
              const payloadStr = changedValues.request_payload;
              if (payloadStr) {
                const extracted = extractFieldsFromPayload(payloadStr);
                const updates: Record<string, any> = {};
                if (
                  extracted.model !== undefined &&
                  extracted.model !== form.getFieldValue('model')
                ) {
                  updates.model = extracted.model;
                }
                if (
                  extracted.stream !== undefined &&
                  extracted.stream !== form.getFieldValue('stream_mode')
                ) {
                  updates.stream_mode = extracted.stream;
                  setStreamMode(extracted.stream);
                }
                if (Object.keys(updates).length > 0) {
                  isSyncingRef.current = true;
                  form.setFieldsValue(updates);
                  isSyncingRef.current = false;
                }
              }
            }

            if ('warmup_enabled' in changedValues) {
              const warmupEnabled = changedValues.warmup_enabled;
              const currentWarmupDuration =
                form.getFieldValue('warmup_duration');
              if (warmupEnabled === false) {
                form.setFieldsValue({
                  warmup_duration: currentWarmupDuration ?? 120,
                });
              } else if (warmupEnabled === true) {
                if (
                  currentWarmupDuration === undefined ||
                  currentWarmupDuration === null
                ) {
                  form.setFieldsValue({ warmup_duration: 120 });
                }
              }
            }
            if ('concurrent_users' in changedValues) {
              setConcurrentUsers(changedValues.concurrent_users);
            }
          }

          // Clear related fields when dataset source type changes
          if ('test_data_input_type' in changedValues) {
            const newInputType = changedValues.test_data_input_type;
            setDatasetFile(null);
            if (newInputType === 'input') {
              // Clear test_data_file and test_data when switching to custom input
              form.setFieldsValue({
                test_data_file: undefined,
                test_data: undefined,
                chat_type: undefined,
              });
            } else if (newInputType === 'upload') {
              // Clear test_data when switching to file upload
              form.setFieldsValue({
                test_data: undefined,
                chat_type: undefined,
              });
            } else if (newInputType === 'default') {
              // Reset dataset-related fields when switching back to built-in dataset
              form.setFieldsValue({
                test_data: undefined,
                test_data_file: undefined,
              });
              if (form.getFieldValue('chat_type') === undefined) {
                form.setFieldsValue({ chat_type: 0 });
              }
            } else {
              // Clear dataset-related fields when no dataset is selected
              form.setFieldsValue({
                test_data: undefined,
                test_data_file: undefined,
                chat_type: undefined,
              });
            }
          }

          // Check form validity for test button whenever any field changes
          setTimeout(() => {
            const isValid = checkFormValidForTest();
            setIsTestButtonEnabled(isValid);
          }, 0);
        }}
      >
        {/* Hidden field for storing file and temporary task ID */}
        <Form.Item name='temp_task_id' hidden>
          <Input />
        </Form.Item>
        <Form.Item name='cert_file' hidden>
          <Input />
        </Form.Item>
        <Form.Item name='key_file' hidden>
          <Input />
        </Form.Item>
        <Form.Item name='test_data_file' hidden>
          <Input />
        </Form.Item>

        {/* Tabs for organized form sections */}
        <Form.Item noStyle shouldUpdate>
          {({ getFieldValue }) => {
            const currentApiType = getFieldValue('api_type') || 'openai-chat';
            const isStandardChatApi =
              currentApiType === 'openai-chat' ||
              currentApiType === 'claude-chat';

            // Build tabs array based on API type
            const tabItems = [
              {
                key: '1',
                label: (
                  <span className='tab-label'>
                    <span className='tab-icon'>
                      <SettingOutlined />
                    </span>
                    {t('components.createJobForm.basicRequest')}
                  </span>
                ),
                children: renderTab1Content(),
              },
            ];

            // Only show field mapping tab for custom-chat and embeddings
            if (!isStandardChatApi) {
              tabItems.push({
                key: '2',
                label: (
                  <span className='tab-label'>
                    <span className='tab-icon'>
                      <ApiOutlined />
                    </span>
                    {t('components.createJobForm.fieldMapping')}
                  </span>
                ),
                children: renderTab3Content(),
              });
            }

            // Data/Load tab - always show
            tabItems.push({
              key: isStandardChatApi ? '2' : '3',
              label: (
                <span className='tab-label'>
                  <span className='tab-icon'>
                    <DatabaseOutlined />
                  </span>
                  {t('components.createJobForm.dataLoad')}
                </span>
              ),
              children: renderTab2Content(),
            });

            return (
              <Tabs
                activeKey={activeTabKey}
                onChange={setActiveTabKey}
                tabPosition='top'
                size='large'
                items={tabItems}
                className='unified-tabs'
                style={{
                  minHeight: '500px',
                }}
              />
            );
          }}
        </Form.Item>
      </Form>

      {/* Action buttons outside of Form to prevent accidental submission */}
      <div
        className='form-actions'
        style={{ marginTop: '24px', textAlign: 'right' }}
      >
        <Space>{renderTabActions()}</Space>
      </div>

      {/* Test Result Drawer */}
      <Drawer
        title={
          <Space>
            <BugOutlined />
            <span>{t('components.createJobForm.apiTestTitle')}</span>
          </Space>
        }
        open={testModalVisible}
        onClose={() => setTestModalVisible(false)}
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
            {/* Status Section */}
            <Descriptions column={1} bordered size='small'>
              {testResult.response?.status_code !== undefined && (
                <Descriptions.Item
                  label={t('components.createJobForm.testStatusCode')}
                >
                  <Tag
                    color={
                      testResult.response.status_code === 200 ? 'green' : 'red'
                    }
                    style={{ fontSize: 14, padding: '2px 12px' }}
                  >
                    {testResult.response.status_code}
                  </Tag>
                </Descriptions.Item>
              )}
              {testResult.response?.is_stream !== undefined && (
                <Descriptions.Item
                  label={t('components.createJobForm.responseMode')}
                >
                  <Tag
                    color={testResult.response.is_stream ? 'blue' : 'default'}
                  >
                    {testResult.response.is_stream
                      ? `${t('components.createJobForm.stream')}${Array.isArray(testResult.response.data) ? ` (${testResult.response.data.length} ${t('components.createJobForm.chunks')})` : ''}`
                      : t('components.createJobForm.nonStreaming')}
                  </Tag>
                </Descriptions.Item>
              )}
            </Descriptions>

            {/* Error Message — only show when no response data */}
            {testResult.status === 'error' &&
              testResult.error &&
              testResult.response?.data === undefined && (
                <Alert
                  type='error'
                  message={testResult.error}
                  style={{ marginTop: 12 }}
                />
              )}

            {/* Response Data Section */}
            {testResult.response?.data !== undefined && (
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
                    {t('components.createJobForm.testResponse')}
                  </Text>
                  <Button
                    type='text'
                    size='small'
                    icon={<CopyOutlined />}
                    onClick={() => {
                      let textToCopy = '';
                      if (
                        testResult.response.is_stream &&
                        Array.isArray(testResult.response.data)
                      ) {
                        textToCopy = testResult.response.data.join('\n');
                      } else if (typeof testResult.response.data === 'string') {
                        textToCopy = testResult.response.data;
                      } else {
                        textToCopy = JSON.stringify(
                          testResult.response.data,
                          null,
                          2
                        );
                      }
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

                {testResult.response.is_stream &&
                Array.isArray(testResult.response.data) ? (
                  // Stream response display
                  <div
                    style={{
                      flex: 1,
                      overflow: 'auto',
                      maxHeight: 'calc(100vh - 340px)',
                    }}
                    className='custom-scrollbar'
                  >
                    {testResult.response.data.map(
                      (chunk: string, index: number) => (
                        <div
                          key={index}
                          style={{
                            padding: '8px 12px',
                            backgroundColor:
                              index % 2 === 0 ? '#ffffff' : '#f8f9fa',
                            borderRadius: '4px',
                            border: '1px solid #e8e8e8',
                            marginBottom: 4,
                            fontSize: '12px',
                            fontFamily:
                              "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
                            wordBreak: 'break-all',
                            whiteSpace: 'pre-wrap',
                            lineHeight: '1.4',
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'flex-start',
                            }}
                          >
                            <span
                              style={{
                                color: '#666',
                                marginRight: 12,
                                fontSize: '11px',
                                fontWeight: 'bold',
                                minWidth: '40px',
                                opacity: 0.7,
                              }}
                            >
                              [{String(index + 1).padStart(3, '0')}]
                            </span>
                            <div style={{ flex: 1 }}>{chunk}</div>
                          </div>
                        </div>
                      )
                    )}
                  </div>
                ) : (
                  // Non-stream response display
                  <TextArea
                    readOnly
                    value={
                      typeof testResult.response.data === 'string'
                        ? testResult.response.data
                        : JSON.stringify(testResult.response.data, null, 2)
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
                )}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </Card>
  );
};

const CreateLlmTaskForm: React.FC<CreateLlmTaskFormProps> = props => (
  <CreateLlmTaskFormContent {...props} />
);

export default CreateLlmTaskForm;
