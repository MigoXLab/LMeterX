/**
 * @file Layout.tsx
 * @description Layout component
 * @author Charm
 * @copyright 2025
 * */

import {
  DatabaseOutlined,
  GithubOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { Layout as AntdLayout, Menu, Typography, theme } from 'antd';
import React, { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

const { Header, Content, Footer, Sider } = AntdLayout;
const { Title } = Typography;

const Layout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  // Navigation items
  const navItems = [
    {
      key: 'datasets',
      icon: <DatabaseOutlined />,
      label: 'Datasets',
      onClick: () => navigate('/datasets'),
    },
    {
      key: 'jobs',
      icon: <RocketOutlined />,
      label: 'Jobs',
      onClick: () => navigate('/jobs'),
    },
  ];

  // Determine active menu item
  const getSelectedKey = () => {
    const path = location.pathname.split('/')[1];
    return path || 'jobs';
  };

  return (
    <AntdLayout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={value => setCollapsed(value)}
        theme='light'
        width={220}
      >
        <div
          style={{
            height: 32,
            margin: 16,
            textAlign: 'center',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          <Title level={4} style={{ margin: 0, color: '#667eea' }}>
            {collapsed ? 'LLM' : 'LMeterX'}
          </Title>
        </div>
        <Menu
          mode='inline'
          selectedKeys={[getSelectedKey()]}
          items={navItems}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <AntdLayout>
        <Header style={{ padding: 0, background: colorBgContainer }} />
        <Content style={{ margin: '0 16px' }}>
          <div
            style={{
              padding: 24,
              minHeight: 360,
              background: colorBgContainer,
              borderRadius: borderRadiusLG,
              marginTop: 16,
              marginBottom: 16,
            }}
          >
            <Outlet />
          </div>
        </Content>
        <Footer style={{ textAlign: 'center' }}>
          LMeterX ©{new Date().getFullYear()} Created with
          <GithubOutlined style={{ marginLeft: 8 }} />
        </Footer>
      </AntdLayout>
    </AntdLayout>
  );
};

export default Layout;
