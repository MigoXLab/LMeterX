/**
 * @file Header.tsx
 * @description Header component with top navigation menu
 * @author Charm
 * @copyright 2025
 * */
import { GithubOutlined, LogoutOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { Avatar, Button, Dropdown, Layout, Menu, Space } from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { UserInfo } from '../types/auth';
import { clearAuth, getStoredUser } from '../utils/auth';
import { getLdapEnabled } from '../utils/runtimeConfig';
import LanguageSwitcher from './LanguageSwitcher';

const { Header: AntdHeader } = Layout;

const LDAP_ENABLED = getLdapEnabled();

const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [user, setUser] = useState<UserInfo | null>(() => getStoredUser());

  const headerStyle: React.CSSProperties = {
    background: '#ffffff',
    padding: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '64px',
    position: 'sticky',
    top: 0,
    zIndex: 1000,
  };

  const headerContainerStyle: React.CSSProperties = {
    width: '100%',
    maxWidth: '100%',
    margin: '0 auto',
    display: 'flex',
    alignItems: 'center',
    gap: 24,
  };

  const logoStyle: React.CSSProperties = {
    fontSize: '22px',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '0.04em',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
    position: 'relative',
    transition: 'all 0.3s ease',
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
    color: 'var(--color-text-secondary)',
    display: 'flex',
    alignItems: 'center',
  };

  const githubStarStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    borderRadius: '8px',
    border: 'none',
    background: 'transparent',
    color: 'var(--color-text-secondary)',
    transition: 'all 0.25s ease',
    height: '32px',
    padding: '0 10px',
    fontWeight: 500,
    fontSize: '13px',
    cursor: 'pointer',
    textDecoration: 'none',
    whiteSpace: 'nowrap',
  };

  const rightActionsStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  };

  const userButtonStyle: React.CSSProperties = {
    borderRadius: 8,
    background: 'transparent',
    border: 'none',
    padding: '0 12px 0 4px',
    height: 36,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    fontWeight: 500,
    letterSpacing: '0.01em',
    lineHeight: 1,
    transition: 'all 0.25s ease',
    color: 'var(--color-text)',
  };

  useEffect(() => {
    setUser(getStoredUser());
    const syncUser = () => setUser(getStoredUser());
    window.addEventListener('storage', syncUser);
    return () => window.removeEventListener('storage', syncUser);
  }, [location.pathname]);

  const handleLogout = () => {
    clearAuth();
    navigate('/login', { replace: true });
  };

  const userLabel = useMemo(
    () => user?.display_name || user?.username || t('sidebar.systemConfig'),
    [t, user]
  );

  const userMenuItems: MenuProps['items'] = useMemo(
    () => [
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: t('header.logout') ?? '退出登录',
      },
    ],
    [t]
  );

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      handleLogout();
    }
  };

  return (
    <AntdHeader className='header-shell' style={headerStyle}>
      <div className='header-inner' style={headerContainerStyle}>
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
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
          <Menu
            mode='horizontal'
            selectedKeys={[location.pathname]}
            items={menuItems}
            style={menuStyle}
            onClick={({ key }) => navigate(key)}
            className='header-nav-menu'
          />
        </div>
        <div className='header-actions' style={rightActionsStyle}>
          <a
            className='github-star-button'
            style={githubStarStyle}
            href='https://github.com/MigoXLab/LMeterX'
            target='_blank'
            rel='noopener noreferrer'
          >
            <GithubOutlined style={{ fontSize: 15 }} />
            <span>Star</span>
          </a>
          <LanguageSwitcher />
          {LDAP_ENABLED && (
            <Dropdown
              menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
              trigger={['click']}
              placement='bottomRight'
              arrow
            >
              <Button
                type='text'
                className='user-menu-trigger'
                style={userButtonStyle}
              >
                <Space size={6} align='center'>
                  <Avatar
                    size={26}
                    style={{
                      background:
                        'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      fontSize: 13,
                      fontWeight: 600,
                      lineHeight: '26px',
                    }}
                  >
                    {(user?.display_name || user?.username || '?')
                      .charAt(0)
                      .toUpperCase()}
                  </Avatar>
                  <span>{userLabel}</span>
                </Space>
              </Button>
            </Dropdown>
          )}
        </div>
      </div>
    </AntdHeader>
  );
};

export default Header;
