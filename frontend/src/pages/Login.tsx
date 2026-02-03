import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { authApi } from '../api/services';
import LanguageSwitcher from '../components/LanguageSwitcher';
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
  position: 'relative',
  background:
    'radial-gradient(circle at 20% 20%, #eef2ff 0, transparent 25%), radial-gradient(circle at 80% 0, #f3e8ff 0, transparent 25%), #f8fafc',
  padding: '24px',
};

const LDAP_ENABLED = getLdapEnabled();

const Login: React.FC = () => {
  const { t } = useTranslation();
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
      message.success(t('pages.login.loginSuccess'));
      navigate(redirectTo, { replace: true });
    } catch (error: any) {
      const msg =
        error?.data?.message ||
        error?.data?.error ||
        error?.statusText ||
        t('pages.login.loginFailedDefault');
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={wrapperStyle}>
      <div style={{ position: 'absolute', top: 20, right: 20 }}>
        <LanguageSwitcher />
      </div>
      <Card style={cardStyle} variant='borderless'>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 8 }}>
            {t('pages.login.title')}
          </Title>
          <Paragraph style={{ margin: 0, color: '#666' }}>
            {t('pages.login.subtitle')}
          </Paragraph>
        </div>
        <Form
          layout='vertical'
          onFinish={onFinish}
          requiredMark={false}
          autoComplete='off'
        >
          <Form.Item
            name='username'
            label={t('pages.login.usernameLabel')}
            rules={[
              { required: true, message: t('pages.login.usernameRequired') },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('pages.login.usernamePlaceholder')}
              size='large'
              autoFocus
            />
          </Form.Item>
          <Form.Item
            name='password'
            label={t('pages.login.passwordLabel')}
            rules={[
              { required: true, message: t('pages.login.passwordRequired') },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('pages.login.passwordPlaceholder')}
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
              {t('pages.login.loginButton')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default Login;
