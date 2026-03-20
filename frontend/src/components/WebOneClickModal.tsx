/**
 * @file WebOneClickModal.tsx
 * @description Web One-Click Load Test Modal — analyze a web page URL to discover
 *   business APIs, then test connectivity or launch individual load tests.
 * @author Charm
 * @copyright 2025
 */
import {
  ApiOutlined,
  BugOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  GlobalOutlined,
  InfoCircleOutlined,
  LoadingOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  RocketOutlined,
  SearchOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { commonJobApi, skillApi } from '@/api/services';

const { Text } = Typography;
const { TextArea } = Input;

/* ────────────────────────────── Types ────────────────────────────── */

interface DiscoveredApi {
  name: string;
  target_url: string;
  method: string;
  headers: Array<{ key: string; value: string }>;
  request_body: string | null;
  http_status: number | null;
  source: string;
  confidence: string;
}

interface LoadtestConfig {
  temp_task_id: string;
  name: string;
  method: string;
  target_url: string;
  headers: Array<{ key: string; value: string }>;
  cookies: Array<{ key: string; value: string }>;
  request_body: string;
  concurrent_users: number;
  duration: number;
  spawn_rate: number;
  load_mode: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onTaskCreated?: () => void;
}

/* ───────────────────────── Color maps ───────────────────────── */

const CONFIDENCE_COLOR: Record<string, string> = {
  high: 'volcano',
  medium: 'gold',
  low: 'default',
};

const HTTP_METHODS = [
  'GET',
  'POST',
  'PUT',
  'PATCH',
  'DELETE',
  'HEAD',
  'OPTIONS',
];

/* ────────────────────────── Main component ────────────────────────── */

const WebOneClickModal: React.FC<Props> = ({
  open,
  onClose,
  onTaskCreated,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();

  // ── Step state ──
  const [step, setStep] = useState<'input' | 'result'>('input');

  // ── Step 1 state ──
  const [targetUrl, setTargetUrl] = useState('');
  const [waitSeconds, setWaitSeconds] = useState(5);
  const [scroll, setScroll] = useState(true);
  const [defaultConcurrent, setDefaultConcurrent] = useState(50);
  const [defaultDuration, setDefaultDuration] = useState(300);
  const [defaultSpawnRate, setDefaultSpawnRate] = useState(30);
  const [analyzing, setAnalyzing] = useState(false);

  // ── Step 2 state ──
  const [discoveredApis, setDiscoveredApis] = useState<DiscoveredApi[]>([]);
  const [loadtestConfigs, setLoadtestConfigs] = useState<LoadtestConfig[]>([]);
  const [analysisSummary, setAnalysisSummary] = useState('');
  const [llmUsed, setLlmUsed] = useState(false);

  // Removed (deleted) API URLs
  const [removedApis, setRemovedApis] = useState<Set<string>>(new Set());

  // Per-API action states
  const [apiStates, setApiStates] = useState<Record<string, string>>({});
  // Per-API test HTTP status codes (for displaying on tested-fail)
  const [apiTestStatusCodes, setApiTestStatusCodes] = useState<
    Record<string, number>
  >({});
  // Batch creation state
  const [batchCreating, setBatchCreating] = useState(false);

  // Test result drawer
  const [testResult, setTestResult] = useState<{
    apiUrl: string;
    status?: number;
    body?: string;
    error?: string;
  } | null>(null);

  // Map configs by target_url for easy lookup
  const configMap = useMemo(
    () =>
      loadtestConfigs.reduce<Record<string, LoadtestConfig>>((m, cfg) => {
        m[cfg.target_url] = cfg;
        return m;
      }, {}),
    [loadtestConfigs]
  );

  // Visible (non-removed) APIs
  const visibleApis = useMemo(
    () => discoveredApis.filter(a => !removedApis.has(a.target_url)),
    [discoveredApis, removedApis]
  );

  // Count of APIs that can still be batch-created
  const batchCreatableCount = useMemo(
    () =>
      visibleApis.filter(
        a => apiStates[a.target_url] !== 'created' && configMap[a.target_url]
      ).length,
    [visibleApis, apiStates, configMap]
  );

  /* ─────────── Handlers ─────────── */

  const handleReset = useCallback(() => {
    setStep('input');
    setTargetUrl('');
    setDiscoveredApis([]);
    setLoadtestConfigs([]);
    setAnalysisSummary('');
    setLlmUsed(false);
    setApiStates({});
    setApiTestStatusCodes({});
    setRemovedApis(new Set());
    setTestResult(null);
    setBatchCreating(false);
  }, []);

  const handleClose = useCallback(() => {
    handleReset();
    onClose();
  }, [handleReset, onClose]);

  /** Step 1 → call analyze-url */
  const handleAnalyze = useCallback(async () => {
    if (!targetUrl.trim()) {
      messageApi.warning(
        t('components.webOneClick.urlRequired', 'Please enter a URL')
      );
      return;
    }
    const url = targetUrl.trim();
    if (!/^https?:\/\//i.test(url)) {
      messageApi.warning(
        t(
          'components.webOneClick.urlInvalid',
          'URL must start with http:// or https://'
        )
      );
      return;
    }

    setAnalyzing(true);
    try {
      const resp = await skillApi.analyzeUrl({
        target_url: url,
        wait_seconds: waitSeconds,
        scroll,
        concurrent_users: defaultConcurrent,
        duration: defaultDuration,
        spawn_rate: defaultSpawnRate,
      });

      const { data } = resp;
      if (data.status === 'error') {
        messageApi.error(
          data.message || t('components.webOneClick.analyzeFailed')
        );
        return;
      }

      setDiscoveredApis(data.discovered_apis || []);
      setLoadtestConfigs(data.loadtest_configs || []);
      setAnalysisSummary(data.analysis_summary || '');
      setLlmUsed(data.llm_used || false);
      setApiStates({});
      setRemovedApis(new Set());
      setStep('result');
    } catch (err: any) {
      const errMsg =
        err?.data?.message ||
        err?.data?.detail ||
        err?.statusText ||
        String(err);
      messageApi.error(
        `${t('components.webOneClick.analyzeFailed', 'Analysis failed')}: ${errMsg}`
      );
    } finally {
      setAnalyzing(false);
    }
  }, [
    targetUrl,
    waitSeconds,
    scroll,
    defaultConcurrent,
    defaultDuration,
    defaultSpawnRate,
    messageApi,
    t,
  ]);

  /** Update a single config field */
  const updateConfig = useCallback(
    (targetUrl: string, field: keyof LoadtestConfig, value: any) => {
      setLoadtestConfigs(prev =>
        prev.map(cfg =>
          cfg.target_url === targetUrl ? { ...cfg, [field]: value } : cfg
        )
      );
    },
    []
  );

  /** Update a field on a discovered API */
  const updateApiField = useCallback(
    (apiTargetUrl: string, field: keyof DiscoveredApi, value: any) => {
      setDiscoveredApis(prev =>
        prev.map(api =>
          api.target_url === apiTargetUrl ? { ...api, [field]: value } : api
        )
      );
    },
    []
  );

  /** Remove (hide) an API card */
  const handleRemoveApi = useCallback((apiUrl: string) => {
    setRemovedApis(prev => new Set(prev).add(apiUrl));
  }, []);

  /** Test API connectivity */
  const handleTestApi = useCallback(async (api: DiscoveredApi) => {
    const key = api.target_url;
    setApiStates(prev => ({ ...prev, [key]: 'testing' }));
    try {
      const resp = await commonJobApi.testJob({
        method: api.method,
        target_url: api.target_url,
        headers: api.headers || [],
        cookies: [],
        request_body: api.request_body || undefined,
      });
      const data = resp.data as any;
      const httpStatus = data?.http_status ?? data?.status_code ?? data?.status;
      const isSuccess =
        httpStatus != null && httpStatus >= 200 && httpStatus < 300;
      setApiStates(prev => ({
        ...prev,
        [key]: isSuccess ? 'tested-ok' : 'tested-fail',
      }));
      if (httpStatus != null) {
        setApiTestStatusCodes(prev => ({ ...prev, [key]: httpStatus }));
      }
      setTestResult({
        apiUrl: api.target_url,
        status: httpStatus,
        body:
          typeof data?.response_body === 'string'
            ? data.response_body
            : JSON.stringify(data?.response_body ?? data, null, 2),
      });
    } catch (err: any) {
      setApiStates(prev => ({ ...prev, [key]: 'tested-fail' }));
      setTestResult({
        apiUrl: api.target_url,
        error:
          err?.data?.detail ||
          err?.data?.message ||
          err?.statusText ||
          String(err),
      });
    }
  }, []);

  /** Launch load test for a single API */
  const handleLaunchSingle = useCallback(
    async (apiUrl: string) => {
      const cfg = configMap[apiUrl];
      if (!cfg) return;
      const key = apiUrl;
      setApiStates(prev => ({ ...prev, [key]: 'creating' }));
      try {
        await commonJobApi.createJob({
          temp_task_id: cfg.temp_task_id,
          name: cfg.name,
          method: cfg.method,
          target_url: cfg.target_url,
          headers: cfg.headers || [],
          cookies: cfg.cookies || [],
          request_body: cfg.request_body || '',
          concurrent_users: cfg.concurrent_users,
          duration: cfg.duration,
          spawn_rate: cfg.spawn_rate,
          load_mode: cfg.load_mode || 'fixed',
        });
        setApiStates(prev => ({ ...prev, [key]: 'created' }));
        messageApi.success(`${t('pages.jobs.createSuccess')} — ${cfg.name}`);
        onTaskCreated?.();
      } catch (err: any) {
        setApiStates(prev => ({ ...prev, [key]: 'create-fail' }));
        const errMsg =
          err?.data?.detail ||
          err?.data?.message ||
          err?.statusText ||
          String(err);
        messageApi.error(
          `${t('pages.jobs.createFailed')} — ${cfg.name}: ${errMsg}`
        );
      }
    },
    [configMap, messageApi, onTaskCreated, t]
  );

  /** Batch-create load test tasks for all visible, un-created APIs */
  const handleBatchCreate = useCallback(async () => {
    const targets = visibleApis.filter(
      a => apiStates[a.target_url] !== 'created' && configMap[a.target_url]
    );
    if (targets.length === 0) return;

    setBatchCreating(true);

    // Mark all targets as "creating" first
    setApiStates(prev => {
      const next = { ...prev };
      targets.forEach(api => {
        next[api.target_url] = 'creating';
      });
      return next;
    });

    // Fire all requests in parallel
    const results = await Promise.allSettled(
      targets.map(api => {
        const cfg = configMap[api.target_url]!;
        return commonJobApi.createJob({
          temp_task_id: cfg.temp_task_id,
          name: cfg.name,
          method: cfg.method,
          target_url: cfg.target_url,
          headers: cfg.headers || [],
          cookies: cfg.cookies || [],
          request_body: cfg.request_body || '',
          concurrent_users: cfg.concurrent_users,
          duration: cfg.duration,
          spawn_rate: cfg.spawn_rate,
          load_mode: cfg.load_mode || 'fixed',
        });
      })
    );

    // Update states based on results
    let successCount = 0;
    let failCount = 0;
    setApiStates(prev => {
      const next = { ...prev };
      results.forEach((result, i) => {
        const key = targets[i].target_url;
        if (result.status === 'fulfilled') {
          next[key] = 'created';
          successCount++;
        } else {
          next[key] = 'create-fail';
          failCount++;
        }
      });
      return next;
    });

    setBatchCreating(false);

    if (successCount > 0) {
      onTaskCreated?.();
    }
    if (failCount === 0) {
      messageApi.success(
        t('components.webOneClick.batchCreateSuccess', {
          count: successCount,
          defaultValue: `Successfully created ${successCount} load test tasks`,
        })
      );
    } else {
      messageApi.warning(
        t('components.webOneClick.batchCreatePartial', {
          success: successCount,
          fail: failCount,
          defaultValue: `Created ${successCount} tasks, ${failCount} failed`,
        })
      );
    }
  }, [visibleApis, apiStates, configMap, messageApi, onTaskCreated, t]);

  /* ─────────── Render helpers ─────────── */

  const renderApiStateIcon = (apiUrl: string) => {
    const st = apiStates[apiUrl];
    if (!st) return null;
    switch (st) {
      case 'testing':
      case 'creating':
        return <LoadingOutlined spin style={{ color: '#1890ff' }} />;
      case 'tested-ok':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'tested-fail': {
        const statusCode = apiTestStatusCodes[apiUrl];
        return (
          <Space size={2}>
            <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
            {statusCode != null && (
              <Tag color='error' style={{ marginInlineEnd: 0 }}>
                {statusCode}
              </Tag>
            )}
          </Space>
        );
      }
      case 'created':
        return (
          <Tag color='success'>
            {t('components.webOneClick.taskCreated', 'Created')}
          </Tag>
        );
      case 'create-fail':
        return (
          <Tag color='error'>
            {t('components.webOneClick.createFailed', 'Failed')}
          </Tag>
        );
      default:
        return null;
    }
  };

  /* ─────────── Step 1: URL Input ─────────── */

  const renderStep1 = () => (
    <div style={{ paddingTop: 16 }}>
      <Form layout='vertical'>
        <Form.Item
          label={t('components.webOneClick.targetUrl', 'Web URL')}
          required
        >
          <Input
            size='large'
            placeholder={t(
              'components.webOneClick.urlPlaceholder',
              'https://your-webapp.com'
            )}
            value={targetUrl}
            onChange={e => setTargetUrl(e.target.value)}
            onPressEnter={handleAnalyze}
            disabled={analyzing}
            allowClear
          />
        </Form.Item>
      </Form>

      <Collapse
        ghost
        items={[
          {
            key: 'advanced',
            label: t(
              'components.webOneClick.advancedOptions',
              'Advanced Options'
            ),
            children: (
              <Row gutter={[16, 12]}>
                <Col span={8}>
                  <Form.Item
                    label={
                      <Space size={4}>
                        {t(
                          'components.webOneClick.waitSeconds',
                          'Wait Time (s)'
                        )}
                        <Tooltip
                          title={t(
                            'components.webOneClick.waitSecondsTip',
                            'Time to wait after the page loads before capturing API requests. Increase this value for pages with delayed or lazy-loaded content.'
                          )}
                        >
                          <InfoCircleOutlined
                            style={{ color: '#999', cursor: 'pointer' }}
                          />
                        </Tooltip>
                      </Space>
                    }
                  >
                    <InputNumber
                      min={1}
                      max={30}
                      value={waitSeconds}
                      onChange={v => setWaitSeconds(v ?? 5)}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    label={t(
                      'components.webOneClick.scrollPage',
                      'Scroll Page'
                    )}
                  >
                    <Switch checked={scroll} onChange={setScroll} />
                  </Form.Item>
                </Col>
                <Col span={8} />
                <Col span={8}>
                  <Form.Item
                    label={t(
                      'components.webOneClick.defaultConcurrent',
                      'Default Concurrent Users'
                    )}
                  >
                    <InputNumber
                      min={1}
                      max={5000}
                      value={defaultConcurrent}
                      onChange={v => setDefaultConcurrent(v ?? 50)}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    label={t(
                      'components.webOneClick.defaultDuration',
                      'Default Duration (s)'
                    )}
                  >
                    <InputNumber
                      min={1}
                      max={172800}
                      value={defaultDuration}
                      onChange={v => setDefaultDuration(v ?? 300)}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    label={t(
                      'components.webOneClick.defaultSpawnRate',
                      'Default Spawn Rate'
                    )}
                  >
                    <InputNumber
                      min={1}
                      max={10000}
                      value={defaultSpawnRate}
                      onChange={v => setDefaultSpawnRate(v ?? 30)}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>
              </Row>
            ),
          },
        ]}
        style={{ marginTop: 8 }}
      />

      {analyzing ? (
        <div style={{ textAlign: 'center', marginTop: 32, padding: 24 }}>
          <Spin
            size='large'
            tip={t(
              'components.webOneClick.analyzingTip',
              'Loading the page and capturing business API requests...'
            )}
          >
            <div style={{ padding: 50 }} />
          </Spin>
        </div>
      ) : (
        <div style={{ textAlign: 'center', marginTop: 32 }}>
          <Button
            size='large'
            type='primary'
            icon={<SearchOutlined />}
            onClick={handleAnalyze}
            style={{ minWidth: 200 }}
          >
            {t('components.webOneClick.extractApis', 'Extract APIs')}
          </Button>
        </div>
      )}
    </div>
  );

  /* ─────────── Step 2: Result list ─────────── */

  const renderApiCard = (api: DiscoveredApi, idx: number) => {
    const cfg = configMap[api.target_url];
    const state = apiStates[api.target_url];
    const isCreated = state === 'created';

    /** Consistent label style */
    const labelStyle: React.CSSProperties = {
      minWidth: 80,
      whiteSpace: 'nowrap',
      textAlign: 'right',
      flexShrink: 0,
    };

    return (
      <Card
        key={api.target_url + idx}
        size='small'
        style={{ marginBottom: 12 }}
        title={
          <Space size={4} wrap>
            <Text
              strong
              style={{ maxWidth: 400, fontSize: 13 }}
              ellipsis={{ tooltip: api.name }}
            >
              {api.name}
            </Text>
            {api.http_status != null && (
              <Tag color={api.http_status === 200 ? 'green' : 'red'}>
                {api.http_status}
              </Tag>
            )}
            <Tag color={CONFIDENCE_COLOR[api.confidence] || 'default'}>
              {api.confidence}
            </Tag>
            <Tag>
              {api.source === 'playwright_xhr_fetch'
                ? t('components.webOneClick.sourceRuntime', 'Runtime')
                : t('components.webOneClick.sourceJsScan', 'JS Scan')}
            </Tag>
            {renderApiStateIcon(api.target_url)}
          </Space>
        }
        extra={
          !isCreated && (
            <Tooltip
              title={t('components.webOneClick.removeApi', 'Remove this API')}
            >
              <Button
                type='text'
                size='small'
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleRemoveApi(api.target_url)}
              />
            </Tooltip>
          )
        }
      >
        <Descriptions
          column={1}
          size='small'
          styles={{ label: labelStyle }}
          colon
        >
          <Descriptions.Item
            label={t('components.webOneClick.urlLabel', 'URL')}
          >
            <Text copyable style={{ wordBreak: 'break-all' }}>
              {api.target_url}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item
            label={t('components.webOneClick.method', 'Method')}
          >
            <Select
              size='small'
              value={api.method}
              disabled={isCreated}
              style={{ width: 120 }}
              onChange={v => {
                updateApiField(api.target_url, 'method', v);
                // Sync method to loadtest config as well
                updateConfig(api.target_url, 'method', v);
              }}
            >
              {HTTP_METHODS.map(m => (
                <Select.Option key={m} value={m}>
                  {m}
                </Select.Option>
              ))}
            </Select>
          </Descriptions.Item>
          <Descriptions.Item
            label={t('components.webOneClick.headers', 'Headers')}
          >
            <div style={{ maxHeight: 160, overflow: 'auto' }}>
              {(api.headers || []).map((h, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    gap: 4,
                    marginBottom: 4,
                    alignItems: 'center',
                  }}
                >
                  <Input
                    size='small'
                    placeholder={t(
                      'components.webOneClick.headerKeyPlaceholder',
                      'Key'
                    )}
                    value={h.key}
                    disabled={isCreated}
                    style={{ width: 140 }}
                    onChange={e => {
                      const newHeaders = [...api.headers];
                      newHeaders[i] = { ...newHeaders[i], key: e.target.value };
                      updateApiField(api.target_url, 'headers', newHeaders);
                      updateConfig(api.target_url, 'headers', newHeaders);
                    }}
                  />
                  <Input
                    size='small'
                    placeholder={t(
                      'components.webOneClick.headerValuePlaceholder',
                      'Value'
                    )}
                    value={h.value}
                    disabled={isCreated}
                    style={{ flex: 1 }}
                    onChange={e => {
                      const newHeaders = [...api.headers];
                      newHeaders[i] = {
                        ...newHeaders[i],
                        value: e.target.value,
                      };
                      updateApiField(api.target_url, 'headers', newHeaders);
                      updateConfig(api.target_url, 'headers', newHeaders);
                    }}
                  />
                  {!isCreated && (
                    <MinusCircleOutlined
                      style={{ color: '#ff4d4f', cursor: 'pointer' }}
                      onClick={() => {
                        const newHeaders = api.headers.filter(
                          (_, hi) => hi !== i
                        );
                        updateApiField(api.target_url, 'headers', newHeaders);
                        updateConfig(api.target_url, 'headers', newHeaders);
                      }}
                    />
                  )}
                </div>
              ))}
              {!isCreated && (
                <Button
                  type='dashed'
                  size='small'
                  icon={<PlusOutlined />}
                  onClick={() => {
                    const newHeaders = [
                      ...(api.headers || []),
                      { key: '', value: '' },
                    ];
                    updateApiField(api.target_url, 'headers', newHeaders);
                    updateConfig(api.target_url, 'headers', newHeaders);
                  }}
                  style={{ width: '100%', marginTop: 2 }}
                >
                  {t('components.webOneClick.addHeader', 'Add Header')}
                </Button>
              )}
            </div>
          </Descriptions.Item>
          <Descriptions.Item
            label={t('components.webOneClick.requestBody', 'Body')}
          >
            <TextArea
              size='small'
              autoSize={{ minRows: 1, maxRows: 6 }}
              value={api.request_body || ''}
              disabled={isCreated}
              placeholder={t(
                'components.webOneClick.requestBodyPlaceholder',
                'Request body (optional)'
              )}
              style={{
                fontFamily:
                  "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
                fontSize: 12,
              }}
              onChange={e => {
                updateApiField(api.target_url, 'request_body', e.target.value);
                updateConfig(api.target_url, 'request_body', e.target.value);
              }}
            />
          </Descriptions.Item>
          {cfg && (
            <Descriptions.Item
              label={t(
                'components.webOneClick.loadtestConfig',
                'Load Configuration'
              )}
            >
              <div
                style={{
                  border: '1px solid #eaedff',
                  borderRadius: 10,
                  background:
                    'linear-gradient(180deg, #fafbff 0%, #f7f9ff 100%)',
                  padding: 10,
                }}
              >
                <Space direction='vertical' size={8} style={{ width: '100%' }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      background: '#ffffff',
                      border: '1px solid #eceffd',
                      borderRadius: 8,
                      padding: '8px 10px',
                    }}
                  >
                    <Text
                      type='secondary'
                      style={{ width: 170, fontSize: 12, marginBottom: 0 }}
                    >
                      {t('pages.jobs.concurrentUsers', 'Concurrent Users')}
                    </Text>
                    <InputNumber
                      size='small'
                      min={1}
                      max={5000}
                      value={cfg.concurrent_users}
                      onChange={v =>
                        updateConfig(
                          api.target_url,
                          'concurrent_users',
                          v ?? 50
                        )
                      }
                      style={{ width: 220, maxWidth: '100%' }}
                      disabled={isCreated}
                    />
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      background: '#ffffff',
                      border: '1px solid #eceffd',
                      borderRadius: 8,
                      padding: '8px 10px',
                    }}
                  >
                    <Text
                      type='secondary'
                      style={{ width: 170, fontSize: 12, marginBottom: 0 }}
                    >
                      {t('pages.jobs.duration', 'Duration (s)')}
                    </Text>
                    <InputNumber
                      size='small'
                      min={1}
                      max={172800}
                      value={cfg.duration}
                      onChange={v =>
                        updateConfig(api.target_url, 'duration', v ?? 300)
                      }
                      style={{ width: 220, maxWidth: '100%' }}
                      disabled={isCreated}
                    />
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      background: '#ffffff',
                      border: '1px solid #eceffd',
                      borderRadius: 8,
                      padding: '8px 10px',
                    }}
                  >
                    <Text
                      type='secondary'
                      style={{ width: 170, fontSize: 12, marginBottom: 0 }}
                    >
                      {t(
                        'components.createCommonJobForm.spawnRate',
                        'Spawn Rate'
                      )}
                    </Text>
                    <InputNumber
                      size='small'
                      min={1}
                      max={10000}
                      value={cfg.spawn_rate}
                      onChange={v =>
                        updateConfig(api.target_url, 'spawn_rate', v ?? 30)
                      }
                      style={{ width: 220, maxWidth: '100%' }}
                      disabled={isCreated}
                    />
                  </div>
                </Space>
              </div>
            </Descriptions.Item>
          )}
        </Descriptions>

        <div
          style={{
            marginTop: 12,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
          }}
        >
          <Button
            type='primary'
            icon={<BugOutlined />}
            loading={state === 'testing'}
            onClick={() => handleTestApi(api)}
            disabled={isCreated}
          >
            {t('components.webOneClick.testConnectivity', 'Test')}
          </Button>
          <Button
            type='primary'
            icon={<RocketOutlined />}
            loading={state === 'creating'}
            disabled={isCreated || !cfg}
            onClick={() => handleLaunchSingle(api.target_url)}
          >
            {isCreated
              ? t('components.webOneClick.taskCreated', 'Created')
              : t('components.webOneClick.singleTaskCreate', 'Create')}
          </Button>
        </div>
      </Card>
    );
  };

  const renderStep2 = () => (
    <div>
      {analysisSummary && (
        <Alert
          type='info'
          showIcon
          icon={<ApiOutlined />}
          message={
            <Space>
              <span>{analysisSummary}</span>
              {llmUsed && (
                <Badge count='AI' style={{ backgroundColor: '#722ed1' }} />
              )}
            </Space>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Scrollable API card list */}
      <div
        style={{
          maxHeight: 'calc(70vh - 180px)',
          overflowY: 'auto',
          paddingRight: 4,
        }}
      >
        {visibleApis.length === 0 ? (
          <Empty
            description={t(
              'components.webOneClick.noApisFound',
              'No business APIs found'
            )}
          />
        ) : (
          visibleApis.map((api, idx) => renderApiCard(api, idx))
        )}
      </div>

      {/* Bottom action bar */}
      <div
        style={{
          marginTop: 16,
          paddingTop: 12,
          borderTop: '1px solid #f0f0f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Button onClick={() => setStep('input')}>
          {t('components.webOneClick.backToInput', '← Back')}
        </Button>

        <Space>
          <Button onClick={handleClose} icon={<CloseOutlined />}>
            {t('common.close', 'Close')}
          </Button>
          {visibleApis.length > 0 && (
            <Button
              type='primary'
              icon={<SendOutlined />}
              loading={batchCreating}
              disabled={batchCreatableCount === 0}
              onClick={handleBatchCreate}
            >
              {t('components.webOneClick.batchCreate', 'Batch Create')}
              {batchCreatableCount > 0 && ` (${batchCreatableCount})`}
            </Button>
          )}
        </Space>
      </div>

      {/* Test result drawer */}
      <Drawer
        title={t('components.webOneClick.testResult', 'API Test Result')}
        open={!!testResult}
        onClose={() => setTestResult(null)}
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
                label={t('components.webOneClick.urlLabel', 'URL')}
              >
                <Text copyable style={{ wordBreak: 'break-all' }}>
                  {testResult.apiUrl}
                </Text>
              </Descriptions.Item>
              {testResult.status !== undefined && (
                <Descriptions.Item
                  label={t(
                    'components.createCommonJobForm.testStatusCode',
                    'Status Code'
                  )}
                >
                  <Tag
                    color={testResult.status === 200 ? 'green' : 'red'}
                    style={{ fontSize: 14, padding: '2px 12px' }}
                  >
                    {testResult.status}
                  </Tag>
                </Descriptions.Item>
              )}
            </Descriptions>
            {testResult.error && (
              <Alert
                type='error'
                message={testResult.error}
                style={{ marginTop: 12 }}
              />
            )}
            {testResult.body && (
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
                    {t(
                      'components.createCommonJobForm.testResponse',
                      'Response'
                    )}
                  </Text>
                  <Button
                    type='text'
                    size='small'
                    icon={<CopyOutlined />}
                    onClick={() => {
                      navigator.clipboard.writeText(testResult.body || '');
                      messageApi.success(
                        t('common.copySuccess', 'Copied to clipboard')
                      );
                    }}
                  >
                    {t('common.copy', 'Copy')}
                  </Button>
                </div>
                <TextArea
                  readOnly
                  value={testResult.body}
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
    </div>
  );

  /* ─────────── Main render ─────────── */

  return (
    <Modal
      title={
        <Space>
          <GlobalOutlined />
          {t('components.webOneClick.title', 'Web One-Click Load Test')}
        </Space>
      }
      open={open}
      onCancel={handleClose}
      footer={null}
      width={860}
      centered
      destroyOnHidden
      maskClosable={false}
      styles={{
        body: {
          maxHeight: '75vh',
          overflowY: 'auto',
        },
      }}
    >
      {step === 'input' ? renderStep1() : renderStep2()}
    </Modal>
  );
};

export default WebOneClickModal;
