/**
 * @file SystemMonitor.tsx
 * @description System monitor page component
 * @author Charm
 * @copyright 2025
 * */
import { MonitorOutlined } from '@ant-design/icons';
import { Tabs } from 'antd';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import SystemLogs from '../components/SystemLogs';
import { PageHeader } from '../components/ui/PageHeader';

const SystemMonitor: React.FC = () => {
  const [activeTab, setActiveTab] = useState('engine-logs');
  const { t } = useTranslation();

  // Define tabs using the items attribute
  const tabItems = [
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

    // More monitoring tabs can be added here, such as CPU usage, memory usage, etc.
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
          onChange={setActiveTab}
          items={tabItems}
          className='unified-tabs'
        />
      </div>
    </div>
  );
};

export default SystemMonitor;
