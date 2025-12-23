/**
 * @file Header.tsx
 * @description Header component with top navigation menu
 * @author Charm
 * @copyright 2025
 * */
import { GithubOutlined } from '@ant-design/icons';
import { Button, Layout, Menu } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import LanguageSwitcher from './LanguageSwitcher';

const { Header: AntdHeader } = Layout;

const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const headerStyle: React.CSSProperties = {
    background: '#ffffff',
    padding: '0 32px',
    borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: '64px',
    position: 'sticky',
    top: 0,
    zIndex: 1000,
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
  };

  const logoStyle: React.CSSProperties = {
    fontSize: '20px',
    fontWeight: 600,
    color: '#333',
    cursor: 'pointer',
    letterSpacing: '-0.01em',
  };

  const menuItems = [
    {
      key: '/jobs',
      label: t('sidebar.testTasks'),
    },
    {
      key: '/result-comparison',
      label: t('sidebar.perfCompare'),
    },
    {
      key: '/system-monitor',
      label: t('sidebar.monitorHub'),
    },
    {
      key: '/system-config',
      label: t('sidebar.systemConfig'),
    },
  ];

  const menuStyle: React.CSSProperties = {
    background: 'transparent',
    border: 'none',
    flex: 1,
    justifyContent: 'center',
    color: '#333',
  };

  const githubButtonStyle: React.CSSProperties = {
    marginRight: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    borderRadius: '8px',
    border: '1px solid rgba(0, 0, 0, 0.12)',
    background: '#ffffff',
    color: '#333',
    transition: 'all 0.2s ease',
    height: '36px',
    padding: '4px 16px',
    fontWeight: 500,
  };

  return (
    <AntdHeader style={headerStyle}>
      <div
        className='logo'
        style={logoStyle}
        onClick={() => navigate('/jobs')}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            navigate('/jobs');
          }
        }}
        role='button'
        tabIndex={0}
      >
        LMeterX
      </div>
      <Menu
        mode='horizontal'
        selectedKeys={[location.pathname]}
        items={menuItems}
        style={menuStyle}
        onClick={({ key }) => navigate(key)}
        className='header-nav-menu'
      />
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <Button
          type='text'
          icon={<GithubOutlined />}
          style={githubButtonStyle}
          href='https://github.com/MigoXLab/LMeterX'
          target='_blank'
          rel='noopener noreferrer'
          onMouseEnter={e => {
            e.currentTarget.style.background = '#f5f5f5';
            e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.2)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = '#ffffff';
            e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.12)';
          }}
        >
          GitHub
        </Button>
        <LanguageSwitcher />
      </div>
    </AntdHeader>
  );
};

export default Header;
