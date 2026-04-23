/**
 * @file SystemMonitor.tsx
 * @description System monitor page component
 * @author Charm
 * @copyright 2025
 * */
import { DashboardOutlined, MonitorOutlined } from '@ant-design/icons';
import { Tabs } from 'antd';
import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import EngineResources from '../components/EngineResources';
import SystemLogs from '../components/SystemLogs';
import { PageHeader } from '../components/ui/PageHeader';
import { getStoredUser } from '../utils/auth';
import { getLdapEnabled } from '../utils/runtimeConfig';

const SYSTEM_MONITOR_TAB_STORAGE_KEY = 'system-monitor-active-tab';
const VALID_TABS = new Set(['engine-resources', 'engine-logs', 'backend-logs']);

const SystemMonitor: React.FC = () => {
  const [searchParams] = useSearchParams();
  const canViewLogs = !getLdapEnabled() || getStoredUser()?.is_admin;
  // Read engine_id from URL query params (e.g. /system-monitor?engine_id=xxx)
  const urlEngineId = useMemo(
    () => searchParams.get('engine_id') || undefined,
    [searchParams]
  );
  const [activeTab, setActiveTab] = useState(() => {
    // If engine_id is in URL, default to engine-resources tab
    if (urlEngineId) return 'engine-resources';
    if (typeof window === 'undefined') return 'engine-resources';
    const saved = window.localStorage.getItem(SYSTEM_MONITOR_TAB_STORAGE_KEY);
    if (saved && VALID_TABS.has(saved)) {
      if (
        !canViewLogs &&
        (saved === 'engine-logs' || saved === 'backend-logs')
      ) {
        return 'engine-resources';
      }
      return saved;
    }
    return 'engine-resources';
  });
  const { t } = useTranslation();

  // Define tabs using the items attribute
  const tabItems = [
    {
      key: 'engine-resources',
      label: (
        <span className='tab-label'>
          <DashboardOutlined className='tab-icon' />
          {t('pages.systemMonitor.engineResources', {
            defaultValue: 'Engine Resources',
          })}
        </span>
      ),
      children: (
        <EngineResources
          isActive={activeTab === 'engine-resources'}
          initialEngineId={urlEngineId}
        />
      ),
    },
    ...(canViewLogs
      ? [
          {
            key: 'engine-logs',
            label: (
              <span className='tab-label'>
                {t('components.systemLogs.engineLogs', {
                  defaultValue: 'Engine Logs',
                })}
              </span>
            ),
            children: (
              <SystemLogs
                serviceName='engine'
                displayName={t('components.systemLogs.engineLogs', {
                  defaultValue: 'Engine Logs',
                })}
                isActive={activeTab === 'engine-logs'}
              />
            ),
          },
          {
            key: 'backend-logs',
            label: (
              <span className='tab-label'>
                {t('components.systemLogs.backendLogs', {
                  defaultValue: 'Backend Service Logs',
                })}
              </span>
            ),
            children: (
              <SystemLogs
                serviceName='backend'
                displayName={t('components.systemLogs.backendLogs', {
                  defaultValue: 'Backend Service Logs',
                })}
                isActive={activeTab === 'backend-logs'}
              />
            ),
          },
        ]
      : []),
  ];

  return (
    <div className='page-container'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('sidebar.monitorHub')}
          description={t('pages.systemMonitor.description')}
          icon={<MonitorOutlined />}
          level={3}
        />
      </div>
      <div className='jobs-content-wrapper'>
        <Tabs
          activeKey={activeTab}
          onChange={key => {
            setActiveTab(key);
            if (typeof window !== 'undefined') {
              window.localStorage.setItem(SYSTEM_MONITOR_TAB_STORAGE_KEY, key);
            }
          }}
          items={tabItems}
          className='unified-tabs'
        />
      </div>
    </div>
  );
};

export default SystemMonitor;
