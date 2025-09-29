/**
 * @file CreateJobForm.tsx
 * @description Create job form component
 * @author Charm
 * @copyright 2025
 * */
import {
  ApiOutlined,
  BugOutlined,
  CloudOutlined,
  DatabaseOutlined,
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
  App,
  Button,
  Card,
  Col,
  Collapse,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Tabs,
  theme,
  Tooltip,
  Typography,
  Upload,
} from 'antd';
import React, { useCallback, useEffect, useState } from 'react';

import {
  benchmarkJobApi,
  uploadCertificateFiles,
  uploadDatasetFile,
} from '@/api/services';
import { useI18n } from '@/hooks/useI18n';
import { BenchmarkJob } from '@/types/benchmark';
import { CHAT_COMPLETIONS_FIELD_MAPPING } from '@/utils/constants';

const { TextArea } = Input;
const { Text } = Typography;

interface CreateJobFormProps {
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  initialData?: Partial<BenchmarkJob> | null;
}

const CreateJobFormContent: React.FC<CreateJobFormProps> = ({
  onSubmit,
  onCancel,
  loading,
  initialData,
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
  const [isCopyMode, setIsCopyMode] = useState(false);
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  // Add state for tab management
  const [activeTabKey, setActiveTabKey] = useState('1');
  // Add state to track upload loading
  const [uploading, setUploading] = useState(false);
  // Add state to track if user manually modified request_payload
  const [userModifiedPayload, setUserModifiedPayload] = useState(false);

  // Get default field_mapping based on API path and stream mode
  const getDefaultFieldMapping = (apiPath: string, streamMode?: boolean) => {
    if (apiPath === '/chat/completions') {
      const isStreamMode = streamMode !== false; // Default to streaming if not specified
      return {
        ...(isStreamMode
          ? CHAT_COMPLETIONS_FIELD_MAPPING.STREAMING
          : CHAT_COMPLETIONS_FIELD_MAPPING.NON_STREAMING),
      };
    }
    // For non-chat/completions APIs, return empty values (only show placeholders)
    return {
      prompt: '',
      stream_prefix: 'data:',
      data_format: 'json',
      content: '',
      reasoning_content: '',
      prompt_tokens: 'usage.prompt_tokens',
      completion_tokens: 'usage.completion_tokens',
      total_tokens: 'usage.total_tokens',
      end_prefix: '',
      stop_flag: '',
      end_field: '',
    };
  };

  // Generate default request payload based on model and stream mode
  const generateDefaultPayload = (model: string, streamMode: boolean) => {
    const payload = {
      model: model || 'your-model-name',
      stream: streamMode,
      messages: [
        {
          role: 'user',
          content: 'Hi',
        },
      ],
    };
    return JSON.stringify(payload, null, 2);
  };

  // Tab navigation functions
  const goToNextTab = () => {
    if (activeTabKey === '1') setActiveTabKey('2');
    else if (activeTabKey === '2') setActiveTabKey('3');
  };

  const goToPreviousTab = () => {
    if (activeTabKey === '3') setActiveTabKey('2');
    else if (activeTabKey === '2') setActiveTabKey('1');
  };

  // Check if current tab is valid for navigation
  const isCurrentTabValid = useCallback(async () => {
    try {
      if (activeTabKey === '1') {
        // Tab 1: Basic Configuration and Request Configuration
        const requiredFields = [
          'name',
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
        // Tab 2: Test Data and Load Configuration
        const requiredFields = [
          'test_data_input_type',
          'duration',
          'concurrent_users',
          'spawn_rate',
        ];

        // Add chat_type validation when using default dataset and chat/completions API
        const currentTestDataInputType =
          form.getFieldValue('test_data_input_type') || 'default';
        const currentApiPath =
          form.getFieldValue('api_path') || '/chat/completions';
        if (
          currentTestDataInputType === 'default' &&
          currentApiPath === '/chat/completions'
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

  // Handle modal open/close body class management
  useEffect(() => {
    if (testModalVisible) {
      document.body.classList.add('api-test-modal-open');
    } else {
      document.body.classList.remove('api-test-modal-open');
    }

    return () => {
      document.body.classList.remove('api-test-modal-open');
    };
  }, [testModalVisible]);

  // Form values states to replace Form.useWatch
  const [concurrentUsers, setConcurrentUsers] = useState<number>();
  const [streamMode, setStreamMode] = useState<boolean>(true);
  const [isFormReady, setIsFormReady] = useState(false);

  // Initialize form ready state
  useEffect(() => {
    setIsFormReady(true);
  }, []);

  // Initialize field_mapping based on current API path when not in copy mode
  useEffect(() => {
    if (isFormReady && !isCopyMode && !initialData) {
      const currentApiPath =
        form.getFieldValue('api_path') || '/chat/completions';
      const currentStreamMode = form.getFieldValue('stream_mode');
      const defaultFieldMapping = getDefaultFieldMapping(
        currentApiPath,
        currentStreamMode
      );
      form.setFieldsValue({ field_mapping: defaultFieldMapping });
    }
  }, [isFormReady, isCopyMode, initialData, form]);

  // when concurrent_users changes and autoSyncSpawnRate is true, auto update spawn_rate
  useEffect(() => {
    if (autoSyncSpawnRate && isFormReady) {
      if (concurrentUsers && typeof concurrentUsers === 'number') {
        const spawnRateValue = Math.min(concurrentUsers, 100);
        form.setFieldsValue({ spawn_rate: spawnRateValue });
      }
    }
  }, [concurrentUsers, autoSyncSpawnRate, form, isFormReady]);

  // listen to concurrent_users field changes
  const handleConcurrentUsersChange = (value: number) => {
    setConcurrentUsers(value);
    if (autoSyncSpawnRate && value) {
      const spawnRateValue = Math.min(value, 100);
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
      // In copy mode, consider payload as manually modified to prevent auto-filling
      setUserModifiedPayload(true);

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
      dataToFill.request_payload = originalRequestPayload;

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
        message.warning(t('components.createJobForm.taskTemplateCopied'), 5);
      }
    } else if (!isCopyMode) {
      setIsCopyMode(false);
      // Reset user modification tracking for new tasks
      setUserModifiedPayload(false);
      // reset form fields
      const currentTempTaskId = form.getFieldValue('temp_task_id');
      if (currentTempTaskId !== tempTaskId) {
        form.resetFields();
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
            size: (file.size / (1024 * 1024)).toFixed(2),
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
            size: (file.size / (1024 * 1024)).toFixed(2),
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
            size: (file.size / (1024 * 1024)).toFixed(2),
          })
        );
        onError();
        return;
      }

      form.setFieldsValue({
        temp_task_id: tempTaskId,
        test_data_file: file,
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

  // Test API endpoint
  const handleTestAPI = async () => {
    try {
      setTesting(true);

      // Only validate required fields for testing from the first tab
      const requiredFields = [
        'target_host',
        'api_path',
        'model',
        'stream_mode',
        // Remove request_payload from required fields for testing
      ];

      // Validate only the required fields for testing
      await form.validateFields(requiredFields);

      // Get all form values after validation
      const values = form.getFieldsValue();

      // Ensure request_payload is available - auto-generate if empty
      if (!values.request_payload || !values.request_payload.trim()) {
        const currentModel = values.model || '';
        const currentStreamMode =
          values.stream_mode !== undefined ? values.stream_mode : true;
        values.request_payload = generateDefaultPayload(
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

      // Prepare test data - provide default values for missing fields
      const testData = {
        ...values,
        // Provide default values for testing
        duration: 10, // Default 10 seconds for testing
        concurrent_users: 1, // Default 1 user for testing
        spawn_rate: 1, // Default spawn rate for testing
        test_data_input_type: 'none', // No dataset for testing
      };

      // Remove field_mapping as it's not needed for testing
      delete testData.field_mapping;
      delete testData.cert_type;

      // Call test API
      const apiResponse = await benchmarkJobApi.testApiEndpoint(testData);
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

      // Ensure request_payload is available - auto-generate if empty
      if (!values.request_payload || !values.request_payload.trim()) {
        const currentModel = values.model || '';
        const currentStreamMode =
          values.stream_mode !== undefined ? values.stream_mode : true;
        values.request_payload = generateDefaultPayload(
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

      if (values.test_data_file) {
        try {
          setUploading(true);
          const result = await uploadDatasetFile(
            values.test_data_file,
            tempTaskId
          );
          values.test_data = result.test_data;
          delete values.test_data_file;
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

      // Handle test data input type
      const inputType = values.test_data_input_type || 'default';
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
      if (!values.target_host || !values.api_path || !values.model) {
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
              {
                validator: (_, value) => {
                  if (!value || !value.trim()) {
                    return Promise.reject(
                      new Error(
                        t('components.createJobForm.taskNameCannotBeEmpty')
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
              placeholder={t('components.createJobForm.taskNamePlaceholder')}
              maxLength={100}
              showCount
            />
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

      <Row gutter={24}>
        <Col span={24}>
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
                required: true,
                message: t('components.createJobForm.pleaseEnterModelName'),
              },
              {
                max: 255,
                message: t('components.createJobForm.modelNameLengthLimit'),
              },
              {
                validator: (_, value) => {
                  if (!value || !value.trim()) {
                    return Promise.reject(
                      new Error(
                        t('components.createJobForm.modelNameCannotBeEmpty')
                      )
                    );
                  }
                  return Promise.resolve();
                },
              },
            ]}
            normalize={value => value?.trim() || ''}
            required
          >
            <Input
              placeholder='e.g. gpt-4, claude-3, internlm3-latest'
              maxLength={255}
              showCount
            />
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
          <Form.Item
            name='stream_mode'
            label={
              <span>
                {t('components.createJobForm.responseMode')}
                <Tooltip
                  title={t('components.createJobForm.responseModeTooltip')}
                >
                  <InfoCircleOutlined style={{ marginLeft: 5 }} />
                </Tooltip>
              </span>
            }
            rules={[
              {
                required: true,
                message: t('components.createJobForm.pleaseSelectResponseMode'),
              },
            ]}
          >
            <Select placeholder={t('components.createJobForm.responseMode')}>
              <Select.Option value>
                {t('components.createJobForm.stream')}
              </Select.Option>
              <Select.Option value={false}>
                {t('components.createJobForm.nonStreaming')}
              </Select.Option>
            </Select>
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
              placeholder='{"model":"your-model-name","messages": [{"role": "user","content":"Hi"}],"stream": true}'
              maxLength={50000}
              showCount
              onChange={e => {
                // Track if user manually modified the payload
                if (
                  e.target.value !==
                  generateDefaultPayload(
                    form.getFieldValue('model') || '',
                    form.getFieldValue('stream_mode') !== undefined
                      ? form.getFieldValue('stream_mode')
                      : true
                  )
                ) {
                  setUserModifiedPayload(true);
                }
              }}
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
          const currentApiPath =
            getFieldValue('api_path') || '/chat/completions';
          const isChatCompletionsApi = currentApiPath === '/chat/completions';

          return (
            <div>
              <Row gutter={24}>
                <Col span={8}>
                  <Form.Item
                    name='test_data_input_type'
                    label={
                      <span>
                        {t('components.createJobForm.datasetSource')}
                        <Tooltip
                          title={t(
                            'components.createJobForm.datasetSourceTooltip'
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
                          'components.createJobForm.pleaseSelectDatasetSource'
                        ),
                      },
                    ]}
                  >
                    <Select
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
                </Col>

                {/* Dataset Type - only show when using built-in dataset and chat completions API */}
                {inputType === 'default' && (
                  <Col span={8}>
                    <Form.Item
                      name='chat_type'
                      label={
                        <span>
                          {t('components.createJobForm.datasetType')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.datasetTypeTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                      rules={[
                        {
                          type: 'number',
                          min: 0,
                          max: 1,
                          message: t(
                            'components.createJobForm.chatTypeRangeLimit'
                          ),
                        },
                      ]}
                      style={{
                        display: isChatCompletionsApi ? 'block' : 'none',
                      }}
                    >
                      <Select
                        placeholder={t('components.createJobForm.datasetType')}
                      >
                        <Select.Option value={0}>
                          {t('components.createJobForm.textOnlyConversations')}
                        </Select.Option>
                        <Select.Option value={1}>
                          {t('components.createJobForm.multimodalTextImage')}
                        </Select.Option>
                      </Select>
                    </Form.Item>
                  </Col>
                )}

                {/* Dataset File - only show when upload is selected */}
                {inputType === 'upload' && (
                  <Col span={8}>
                    <Form.Item
                      name='test_data_file'
                      label={
                        <span>
                          {t('components.createJobForm.datasetFile')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.datasetFileTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                      rules={[
                        {
                          required: inputType === 'upload',
                          message: t(
                            'components.createJobForm.pleaseUploadDatasetFile'
                          ),
                        },
                      ]}
                    >
                      <Upload
                        maxCount={1}
                        accept='.jsonl'
                        customRequest={handleDatasetFileUpload}
                        listType='text'
                        style={{ width: '100%' }}
                      >
                        <Button
                          icon={<UploadOutlined />}
                          size='middle'
                          style={{ width: '200px', height: '40px' }}
                        >
                          {t('components.createJobForm.selectJsonlFile')}
                        </Button>
                      </Upload>
                      <div
                        style={{
                          marginTop: 8,
                          color: token.colorTextSecondary,
                          fontSize: '12px',
                        }}
                      >
                        {t('components.createJobForm.jsonlFormatDescription')}
                      </div>
                    </Form.Item>
                  </Col>
                )}
              </Row>

              {/* Custom JSONL Data Input */}
              {inputType === 'input' && (
                <Row gutter={24}>
                  <Col span={24}>
                    <Form.Item
                      name='test_data'
                      label={
                        <span>
                          {t('components.createJobForm.jsonlData')}
                          <Tooltip
                            title={t(
                              'components.createJobForm.jsonlDataTooltip'
                            )}
                          >
                            <InfoCircleOutlined style={{ marginLeft: 5 }} />
                          </Tooltip>
                        </span>
                      }
                      rules={[
                        {
                          required: inputType === 'input',
                          message: t(
                            'components.createJobForm.pleaseEnterJsonlData'
                          ),
                        },
                        {
                          validator: (_, value) => {
                            if (inputType !== 'input' || !value)
                              return Promise.resolve();
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
                                  t(
                                    'components.createJobForm.invalidJsonlFormat'
                                  )
                                )
                              );
                            }
                          },
                        },
                      ]}
                    >
                      <TextArea
                        rows={4}
                        placeholder={`{"id": "1", "prompt": "Hello, how are you?"}\n{"id": "2", "prompt": "What is artificial intelligence?"}\n{"id": "3", "prompt": "Explain machine learning in simple terms"}`}
                        maxLength={50000}
                        showCount
                        style={{
                          fontFamily:
                            'Monaco, Consolas, "Courier New", monospace',
                        }}
                      />
                    </Form.Item>
                  </Col>
                </Row>
              )}
            </div>
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
                required: true,
                message: t('components.createJobForm.pleaseEnterTestDuration'),
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
                required: true,
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
                required: true,
                message: t('components.createJobForm.pleaseEnterSpawnRate'),
              },
              {
                type: 'number',
                min: 1,
                max: 100,
                message: t('components.createJobForm.spawnRateRangeLimit'),
              },
            ]}
          >
            <InputNumber
              min={1}
              max={100}
              style={{ width: '100%' }}
              placeholder='1'
              onChange={handleSpawnRateChange}
            />
          </Form.Item>
        </Col>
      </Row>
    </div>
  );

  // Field mapping section
  const fieldMappingSection = (
    <div style={{ marginBottom: 24, marginLeft: '8px' }}>
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
      <div
        style={{
          marginBottom: 24,
          padding: '16px',
          backgroundColor: token.colorFillAlter,
          borderRadius: '8px',
        }}
      >
        <div style={{ marginBottom: 12, fontWeight: 'bold', fontSize: '14px' }}>
          {t('components.createJobForm.requestFieldMapping')}
        </div>
        <Row gutter={24}>
          <Col span={24}>
            <Form.Item
              name={['field_mapping', 'prompt']}
              label={
                <span>
                  {t('components.createJobForm.promptFieldPath')}
                  <Tooltip
                    title={t('components.createJobForm.promptFieldPathTooltip')}
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
            >
              <Input placeholder='e.g. query, prompt, input, message' />
            </Form.Item>
          </Col>
        </Row>
      </div>

      {streamMode ? (
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
                        title={t('components.createJobForm.dataFormatTooltip')}
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
                                {t('components.createJobForm.contentFieldPath')}
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
                            rules={[
                              {
                                required: dataFormat === 'json',
                                message: t(
                                  'components.createJobForm.pleaseSpecifyContentFieldPath'
                                ),
                              },
                            ]}
                          >
                            <Input placeholder='choices.0.delta.content' />
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
                            <Input placeholder='choices.0.delta.reasoning_content' />
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
                            <Input placeholder='usage.prompt_tokens' />
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
                            <Input placeholder='usage.completion_tokens' />
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
                  <Input placeholder='choices.0.finish_reason' />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name={['field_mapping', 'stop_flag']}
                  label={
                    <span>
                      {t('components.createJobForm.stopSignal')}
                      <Tooltip
                        title={t('components.createJobForm.stopSignalTooltip')}
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
                >
                  <Input placeholder='stop' />
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
            {t('components.createJobForm.nonStreamingResponseConfiguration')}
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
                rules={[
                  {
                    required: true,
                    message: t(
                      'components.createJobForm.pleaseSpecifyContentFieldPath'
                    ),
                  },
                ]}
              >
                <Input placeholder='choices.0.message.content' />
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
                <Input placeholder='choices.0.message.reasoning_content' />
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
                <Input placeholder='usage.prompt_tokens' />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                name={['field_mapping', 'completion_tokens']}
                label={
                  <span>
                    {t('components.createJobForm.completionTokensFieldPath')}
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
                <Input placeholder='usage.completion_tokens' />
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
      )}
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
    if (activeTabKey === '1') {
      return (
        <Space>
          <Button
            icon={<BugOutlined />}
            onClick={handleTestAPI}
            loading={testing}
            disabled={!isFormValidForTest()}
            className={isFormValidForTest() ? 'test-button-active' : ''}
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
          api_path: '/chat/completions',
          duration: '',
          model: '',
          request_payload: generateDefaultPayload(
            form.getFieldValue('model') || '',
            form.getFieldValue('stream_mode') || true
          ),
          field_mapping: getDefaultFieldMapping('/chat/completions', true),
        }}
        onFinish={handleSubmit}
        onValuesChange={changedValues => {
          if ('stream_mode' in changedValues) {
            setStreamMode(changedValues.stream_mode);
            // Update field_mapping default values when stream mode changes (but not in copy mode)
            if (!isCopyMode) {
              const currentApiPath =
                form.getFieldValue('api_path') || '/chat/completions';
              const newFieldMapping = getDefaultFieldMapping(
                currentApiPath,
                changedValues.stream_mode
              );
              form.setFieldsValue({ field_mapping: newFieldMapping });
            }

            // Auto-fill request_payload when stream_mode changes (only if user hasn't manually modified it)
            if (!userModifiedPayload && !isCopyMode) {
              const currentModel = form.getFieldValue('model') || '';
              const newPayload = generateDefaultPayload(
                currentModel,
                changedValues.stream_mode
              );
              form.setFieldsValue({ request_payload: newPayload });
            }
          }
          if ('concurrent_users' in changedValues) {
            setConcurrentUsers(changedValues.concurrent_users);
          }
          if ('api_path' in changedValues) {
            handleApiPathChange(changedValues.api_path);
            // Update field_mapping default values when API path changes (but not in copy mode)
            if (!isCopyMode) {
              const currentStreamMode = form.getFieldValue('stream_mode');
              const newFieldMapping = getDefaultFieldMapping(
                changedValues.api_path,
                currentStreamMode
              );
              form.setFieldsValue({ field_mapping: newFieldMapping });
            }
          }

          // Auto-fill request_payload when model changes (only if user hasn't manually modified it)
          if ('model' in changedValues && !userModifiedPayload && !isCopyMode) {
            const currentStreamMode =
              form.getFieldValue('stream_mode') !== undefined
                ? form.getFieldValue('stream_mode')
                : true;
            const newPayload = generateDefaultPayload(
              changedValues.model || '',
              currentStreamMode
            );
            form.setFieldsValue({ request_payload: newPayload });
          }

          // Clear related fields when dataset source type changes
          if ('test_data_input_type' in changedValues) {
            const newInputType = changedValues.test_data_input_type;
            if (newInputType === 'input') {
              // Clear test_data_file and test_data when switching to custom input
              form.setFieldsValue({
                test_data_file: undefined,
                test_data: undefined,
              });
            } else if (newInputType === 'upload') {
              // Clear test_data when switching to file upload
              form.setFieldsValue({ test_data: undefined });
            } else {
              // Clear both when switching to default or none
              form.setFieldsValue({
                test_data: undefined,
                test_data_file: undefined,
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
        <Tabs
          activeKey={activeTabKey}
          onChange={setActiveTabKey}
          tabPosition='top'
          size='large'
          items={[
            {
              key: '1',
              label: (
                <span style={{ fontSize: '16px', fontWeight: 'bold' }}>
                  <SettingOutlined style={{ marginRight: 8 }} />
                  {t('components.createJobForm.basicRequest')}
                </span>
              ),
              children: renderTab1Content(),
            },
            {
              key: '2',
              label: (
                <span style={{ fontSize: '16px', fontWeight: 'bold' }}>
                  <DatabaseOutlined style={{ marginRight: 8 }} />
                  {t('components.createJobForm.dataLoad')}
                </span>
              ),
              children: renderTab2Content(),
            },
            {
              key: '3',
              label: (
                <span style={{ fontSize: '16px', fontWeight: 'bold' }}>
                  <ApiOutlined style={{ marginRight: 8 }} />
                  {t('components.createJobForm.fieldMapping')}
                </span>
              ),
              children: renderTab3Content(),
            },
          ]}
          style={{
            minHeight: '500px',
          }}
        />
      </Form>

      {/* Action buttons outside of Form to prevent accidental submission */}
      <div
        className='form-actions'
        style={{ marginTop: '24px', textAlign: 'right' }}
      >
        <Space>{renderTabActions()}</Space>
      </div>

      {/* Test Result Modal */}
      <Modal
        title={
          <Space>
            <BugOutlined />
            <span>{t('components.createJobForm.apiTest')}</span>
          </Space>
        }
        open={testModalVisible}
        onCancel={() => setTestModalVisible(false)}
        footer={[
          <Button
            key='close'
            size='large'
            onClick={() => setTestModalVisible(false)}
          >
            {t('components.createJobForm.close')}
          </Button>,
        ]}
        width={800}
        centered={false}
        destroyOnHidden
        mask={false}
        maskClosable={false}
        keyboard={false}
        zIndex={1002}
        getContainer={false}
        style={{
          position: 'fixed',
          right: '20px',
          top: '50%',
          transform: 'translateY(-50%)',
          margin: 0,
          paddingBottom: 0,
        }}
        styles={{
          body: {
            padding: '20px',
            maxHeight: 'calc(100vh - 160px)',
            overflow: 'auto',
          },
          content: {
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1)',
            maxHeight: 'calc(100vh - 120px)',
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
        {testResult && (
          <div
            style={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            {/* Status Section */}
            <div
              style={{
                padding: '16px',
                backgroundColor: token.colorBgContainer,
                borderRadius: '8px',
                border: `1px solid ${token.colorBorder}`,
                boxShadow: token.boxShadowTertiary,
              }}
            >
              <Row gutter={24} align='middle'>
                {/* Status Code */}
                {testResult.response?.status_code !== undefined && (
                  <Col>
                    <Space>
                      <Text strong style={{ fontSize: '16px' }}>
                        {t('components.createJobForm.statusCode')}:
                      </Text>
                      <div
                        style={{
                          padding: '4px 12px',
                          borderRadius: '6px',
                          backgroundColor:
                            testResult.response.status_code === 200
                              ? token.colorSuccessBg
                              : token.colorErrorBg,
                          color:
                            testResult.response.status_code === 200
                              ? token.colorSuccess
                              : token.colorError,
                          fontWeight: 'bold',
                          fontSize: '14px',
                        }}
                      >
                        {testResult.response.status_code}
                      </div>
                    </Space>
                  </Col>
                )}
              </Row>

              {/* Error Message */}
              {testResult.status === 'error' && testResult.error && (
                <div style={{ marginTop: 12 }}>
                  <div
                    style={{
                      padding: '12px',
                      backgroundColor: token.colorErrorBg,
                      borderRadius: '6px',
                      border: `1px solid ${token.colorErrorBorder}`,
                    }}
                  >
                    <Text strong style={{ color: token.colorError }}>
                      {t('common.error')}:
                    </Text>
                    <Text style={{ color: token.colorError, marginLeft: 8 }}>
                      {testResult.error}
                    </Text>
                  </div>
                </div>
              )}
            </div>

            {/* Response Data Section */}
            {testResult.response?.data !== undefined && (
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                  backgroundColor: token.colorBgContainer,
                  borderRadius: '8px',
                  border: `1px solid ${token.colorBorder}`,
                  boxShadow: token.boxShadowTertiary,
                  overflow: 'hidden',
                }}
              >
                {/* Response Header */}
                <div
                  style={{
                    padding: '12px 16px',
                    backgroundColor: token.colorFillQuaternary,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <Space>
                    <Text strong style={{ fontSize: '16px' }}>
                      {t('components.createJobForm.responseData')}
                    </Text>
                    {testResult.response.is_stream &&
                      Array.isArray(testResult.response.data) && (
                        <div
                          style={{
                            padding: '2px 8px',
                            backgroundColor: token.colorPrimaryBg,
                            color: token.colorPrimary,
                            borderRadius: '4px',
                            fontSize: '12px',
                            fontWeight: 'bold',
                          }}
                        >
                          {t('components.createJobForm.stream')} (
                          {testResult.response.data.length}{' '}
                          {t('components.createJobForm.chunks')})
                        </div>
                      )}
                  </Space>
                </div>

                {/* Response Content */}
                <div
                  style={{
                    flex: 1,
                    overflow: 'auto',
                    padding: '16px',
                    backgroundColor: '#fafafa',
                    maxHeight: '400px', // limit max height to ensure scrolling
                    scrollbarWidth: 'thin', // Firefox
                    scrollbarColor: '#bfbfbf #f0f0f0', // Firefox
                  }}
                  className='custom-scrollbar'
                >
                  {testResult.response.is_stream &&
                  Array.isArray(testResult.response.data) ? (
                    // stream response display
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                      }}
                    >
                      {testResult.response.data.map((chunk, index) => (
                        <div
                          key={index}
                          style={{
                            padding: '8px 12px',
                            backgroundColor:
                              index % 2 === 0 ? '#ffffff' : '#f8f9fa',
                            borderRadius: '4px',
                            border: '1px solid #e8e8e8',
                            fontSize: '12px',
                            fontFamily:
                              'Monaco, Consolas, "Courier New", monospace',
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
                      ))}
                    </div>
                  ) : (
                    // non-stream response display
                    <div
                      style={{
                        backgroundColor: '#ffffff',
                        borderRadius: '6px',
                        border: '1px solid #e8e8e8',
                        overflow: 'hidden',
                      }}
                    >
                      <pre
                        className='custom-scrollbar'
                        style={{
                          margin: 0,
                          padding: '16px',
                          whiteSpace: 'pre-wrap',
                          fontSize: '12px',
                          fontFamily:
                            'Monaco, Consolas, "Courier New", monospace',
                          lineHeight: '1.5',
                          maxHeight: '300px',
                          overflow: 'auto',
                          backgroundColor: 'transparent',
                        }}
                      >
                        {typeof testResult.response.data === 'string'
                          ? testResult.response.data
                          : JSON.stringify(testResult.response.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </Card>
  );
};

const CreateJobForm: React.FC<CreateJobFormProps> = props => (
  <CreateJobFormContent {...props} />
);

export default CreateJobForm;
