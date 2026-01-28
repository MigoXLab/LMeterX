import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { authApi } from '../api/services';
import { LoginResponse } from '../types/auth';
import { clearAuth, saveAuth } from '../utils/auth';
import { getLdapEnabled } from '../utils/runtimeConfig';

const { Title, Paragraph } = Typography;

const cardStyle: React.CSSProperties = {
  maxWidth: 420,
  width: '100%',
  boxShadow: '0 12px 40px rgba(0,0,0,0.08)',
  borderRadius: 16,
};

const wrapperStyle: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background:
    'radial-gradient(circle at 20% 20%, #eef2ff 0, transparent 25%), radial-gradient(circle at 80% 0, #f3e8ff 0, transparent 25%), #f8fafc',
  padding: '24px',
};

const LDAP_ENABLED = getLdapEnabled();

const Login: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(false);
  const redirectTo =
    (location.state as { from?: { pathname?: string } })?.from?.pathname ||
    '/jobs';

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    clearAuth();
    try {
      const res = await authApi.login(values.username.trim(), values.password);
      const payload: LoginResponse = res.data;
      saveAuth(payload.access_token, payload.user);
      message.success('Login successful');
      navigate(redirectTo, { replace: true });
    } catch (error: any) {
      const msg =
        error?.data?.message ||
        error?.data?.error ||
        error?.statusText ||
        'Login failed: Please check your username or password';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={wrapperStyle}>
      <Card style={cardStyle} variant='borderless'>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 8 }}>
            欢迎登录 LMeterX
          </Title>
          <Paragraph style={{ margin: 0, color: '#666' }}>
            使用AD账号完成身份验证
          </Paragraph>
          {LDAP_ENABLED && (
            <Paragraph style={{ margin: '8px 0 0', color: '#999' }}>
              如无法登录，请联系管理员配置LDAP参数
            </Paragraph>
          )}
        </div>
        <Form
          layout='vertical'
          onFinish={onFinish}
          requiredMark={false}
          autoComplete='off'
        >
          <Form.Item
            name='username'
            label='用户名'
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder='AD用户名'
              size='large'
              autoFocus
            />
          </Form.Item>
          <Form.Item
            name='password'
            label='密码'
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder='密码'
              size='large'
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type='primary'
              htmlType='submit'
              block
              size='large'
              loading={loading}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default Login;
