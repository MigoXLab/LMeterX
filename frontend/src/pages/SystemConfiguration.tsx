/**
 * @file SystemConfiguration.tsx
 * @description System Configuration page component
 * @author Charm
 * @copyright 2025
 * */

import { InfoCircleOutlined, SettingOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Space,
  Tooltip,
  Typography,
} from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { systemApi } from '../api/services';
import { PageHeader } from '../components/ui/PageHeader';

const { Text } = Typography;

const SystemConfiguration: React.FC = () => {
  const { t } = useTranslation();
  const [configs, setConfigs] = useState<any[]>([]);
  const [aiConfigModalVisible, setAiConfigModalVisible] = useState(false);
  const [aiForm] = Form.useForm();
  const { message } = App.useApp();
  const isInitializedRef = useRef(false);

  const fetchConfigs = async (forceRefresh: boolean = false) => {
    // prevent duplicate calls unless force refresh is requested
    if (isInitializedRef.current && !forceRefresh) {
      return;
    }

    try {
      if (!isInitializedRef.current) {
        isInitializedRef.current = true;
      }
      const response = await systemApi.getSystemConfigs();
      if (response.data?.status === 'success') {
        setConfigs(response.data.data || []);
      } else {
        message.error(t('pages.systemConfig.loadConfigFailed'));
      }
    } catch (err: any) {
      message.error(
        `${t('pages.systemConfig.loadConfigFailed')}: ${err.message}`
      );
    }
  };

  const handleAiConfigSubmit = async (values: any) => {
    try {
      // batch create or update AI service configurations
      const configsToUpdate = [
        {
          config_key: 'ai_service_host',
          config_value: values.host,
          description: 'The host URL for the AI service',
        },
        {
          config_key: 'ai_service_model',
          config_value: values.model,
          description: 'The AI model to use for analysis',
        },
        {
          config_key: 'ai_service_api_key',
          config_value: values.api_key,
          description: 'The API key for authentication',
        },
      ];

      // Use batch operation instead of multiple individual API calls
      await systemApi.batchUpsertSystemConfigs(configsToUpdate);

      message.success(t('pages.systemConfig.configSaved'));
      setAiConfigModalVisible(false);

      // Update configs with force refresh
      await fetchConfigs(true);
    } catch (err: any) {
      message.error(
        `${t('pages.systemConfig.configSaveFailed')}: ${err.message}`
      );
    }
  };

  const handleConfigureAI = async () => {
    try {
      // update the latest configs
      const response = await systemApi.getSystemConfigs();
      if (response.data?.status === 'success') {
        const latestConfigs = response.data.data || [];

        const hostConfig = latestConfigs.find(
          c => c.config_key === 'ai_service_host'
        );
        const modelConfig = latestConfigs.find(
          c => c.config_key === 'ai_service_model'
        );
        const apiKeyConfig = latestConfigs.find(
          c => c.config_key === 'ai_service_api_key'
        );

        // Reset form to current values
        aiForm.resetFields();
        aiForm.setFieldsValue({
          host: hostConfig?.config_value || '',
          model: modelConfig?.config_value || '',
          api_key: apiKeyConfig?.config_value || '',
        });
        setAiConfigModalVisible(true);
      } else {
        message.error(t('pages.systemConfig.loadConfigFailed'));
      }
    } catch (err: any) {
      message.error(
        `${t('pages.systemConfig.loadConfigFailed')}: ${err.message}`
      );
    }
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  const aiServiceConfigs = [
    {
      key: 'ai_service_host',
      label: t('pages.systemConfig.baseUrl'),
      placeholder: 'https://api.openai.com',
      description: t('pages.systemConfig.baseUrlDescription'),
    },
    {
      key: 'ai_service_model',
      label: t('pages.systemConfig.model'),
      placeholder: 'gpt-3.5-turbo',
      description: t('pages.systemConfig.modelDescription'),
    },
    {
      key: 'ai_service_api_key',
      label: t('pages.systemConfig.apiKey'),
      placeholder: t('pages.systemConfig.enterApiKey'),
      description: t('pages.systemConfig.apiKeyDescription'),
      isPassword: true,
    },
  ];

  return (
    <div className='page-container'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.systemConfig.title')}
          description={t('pages.systemConfig.description')}
          icon={<SettingOutlined />}
          level={3}
        />
      </div>

      <div className='jobs-content-wrapper'>
        <div
          style={{
            padding: '24px',
            paddingLeft: 0,
            backgroundColor: '#ffffff',
            borderRadius: '8px',
          }}
        >
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.systemConfig.aiConfig')}
            </span>
            <Button
              type='primary'
              icon={<SettingOutlined />}
              onClick={handleConfigureAI}
            >
              {t('pages.systemConfig.configure')}
            </Button>
          </div>
          <div className='section-content'>
            <p style={{ color: '#666', marginBottom: 16, marginTop: 0 }}>
              {t('pages.systemConfig.aiConfigDescription')}
            </p>

            <Form layout='vertical' style={{ maxWidth: 600 }}>
              {aiServiceConfigs.map(config => {
                const existingConfig = configs.find(
                  c => c.config_key === config.key
                );
                return (
                  <Form.Item
                    key={config.key}
                    label={
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                        }}
                      >
                        <span>{config.label}</span>
                        <Tooltip title={config.description}>
                          <InfoCircleOutlined
                            style={{ color: '#999', fontSize: '14px' }}
                          />
                        </Tooltip>
                      </div>
                    }
                  >
                    <div
                      style={{ display: 'flex', alignItems: 'center', gap: 12 }}
                    >
                      <div style={{ flex: 1 }}>
                        {existingConfig ? (
                          config.isPassword ? (
                            <Text style={{ color: '#999' }}>
                              ••••••••••••••••
                            </Text>
                          ) : config.key === 'ai_service_host' ? (
                            <Text>
                              {existingConfig.config_value}/chat/completions
                            </Text>
                          ) : (
                            <Text>{existingConfig.config_value}</Text>
                          )
                        ) : (
                          <Text style={{ color: '#999' }}>
                            {t('common.notConfigured', {
                              defaultValue: 'Not configured',
                            })}
                          </Text>
                        )}
                      </div>
                    </div>
                  </Form.Item>
                );
              })}
            </Form>
          </div>
        </div>
      </div>

      {/* AI Service Configuration Modal */}
      <Modal
        title={t('pages.systemConfig.aiConfig')}
        open={aiConfigModalVisible}
        onCancel={() => {
          aiForm.resetFields();
          setAiConfigModalVisible(false);
        }}
        footer={null}
        width={600}
      >
        <Form form={aiForm} layout='vertical' onFinish={handleAiConfigSubmit}>
          <Form.Item
            label={t('pages.systemConfig.baseUrl')}
            name='host'
            rules={[
              {
                required: true,
                message: t('pages.systemConfig.pleaseEnterHostUrl'),
              },
            ]}
            extra={t('pages.systemConfig.enterBaseUrlDescription')}
          >
            <Input
              placeholder='https://your-api-domain.com'
              addonAfter={
                <Input
                  value='/chat/completions'
                  disabled
                  style={{
                    width: '180px',
                    backgroundColor: '#f5f5f5',
                    border: 'none',
                  }}
                />
              }
            />
          </Form.Item>

          <Form.Item
            label={t('pages.systemConfig.model')}
            name='model'
            rules={[
              {
                required: true,
                message: t('pages.systemConfig.pleaseEnterModelName'),
              },
            ]}
            extra={t('pages.systemConfig.enterModelDescription')}
          >
            <Input placeholder='gpt-3.5-turbo' />
          </Form.Item>

          <Form.Item
            label={t('pages.systemConfig.apiKey')}
            name='api_key'
            rules={[
              {
                required: true,
                message: t('pages.systemConfig.pleaseEnterApiKey'),
              },
            ]}
            extra={t('pages.systemConfig.enterApiKeyDescription')}
          >
            {/* <Input.Password placeholder='Enter your API key' visibilityToggle /> */}
            <Input.Password
              placeholder={t('pages.systemConfig.enterApiKeyWithoutBearer')}
              visibilityToggle={false}
              onCopy={e => e.preventDefault()}
              onCut={e => e.preventDefault()}
            />
          </Form.Item>

          <Form.Item>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Space>
                <Button
                  onClick={() => {
                    aiForm.resetFields();
                    setAiConfigModalVisible(false);
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button type='primary' htmlType='submit'>
                  {t('common.save')}
                </Button>
              </Space>
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SystemConfiguration;
