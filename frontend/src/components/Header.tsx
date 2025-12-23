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
    fontSize: '22px',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '0.05em',
    background:
      'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #667eea 100%)',
    backgroundSize: '200% 200%',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
    position: 'relative',
    transition: 'all 0.3s ease',
    textShadow: '0 0 30px rgba(102, 126, 234, 0.3)',
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
    marginRight: '8px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    borderRadius: '6px',
    border: 'none',
    background: 'transparent',
    color: '#333',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    height: '36px',
    padding: '6px 12px',
    fontWeight: 500,
    position: 'relative',
    overflow: 'hidden',
  };

  return (
    <AntdHeader style={headerStyle}>
      <div
        className='logo logo-gradient'
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
        <span className='logo-text'>LMeterX</span>
        <span className='logo-glow' />
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
          className='github-button-tech'
          style={githubButtonStyle}
          href='https://github.com/MigoXLab/LMeterX'
          target='_blank'
          rel='noopener noreferrer'
        >
          GitHub
        </Button>
        <LanguageSwitcher />
      </div>
    </AntdHeader>
  );
};

export default Header;
