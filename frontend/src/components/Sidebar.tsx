/**
 * @file Sidebar.tsx
 * @description Sidebar component
 * @author Charm
 * @copyright 2025
 * */

import {
  BarChartOutlined,
  ExperimentOutlined,
  MonitorOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { ConfigProvider, Layout, Menu } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';

const { Sider } = Layout;

const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const menuItems = [
    {
      key: '/jobs',
      icon: <ExperimentOutlined style={{ color: '#667eea' }} />,
      label: (
        <span className='text-bold text-xl'>{t('sidebar.testTasks')}</span>
      ),
    },
    {
      key: '/result-comparison',
      icon: <BarChartOutlined style={{ color: '#764ba2' }} />,
      label: (
        <span className='text-bold text-xl'>{t('sidebar.perfCompare')}</span>
      ),
    },
    {
      key: '/system-monitor',
      icon: <MonitorOutlined style={{ color: '#8b5cf6' }} />,
      label: (
        <span className='text-bold text-xl'>{t('sidebar.monitorHub')}</span>
      ),
    },
    {
      key: '/system-config',
      icon: <SettingOutlined style={{ color: '#a78bfa' }} />,
      label: (
        <span className='text-bold text-xl'>{t('sidebar.systemConfig')}</span>
      ),
    },
  ];

  return (
    <Sider width={210} className='custom-sider'>
      <ConfigProvider
        theme={{
          components: {
            Menu: {
              itemSelectedBg: 'rgba(102, 126, 234, 0.08)',
              itemSelectedColor: '#667eea',
            },
          },
        }}
      >
        <Menu
          mode='inline'
          selectedKeys={[location.pathname]}
          className='custom-menu'
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </ConfigProvider>
    </Sider>
  );
};

export default Sidebar;
