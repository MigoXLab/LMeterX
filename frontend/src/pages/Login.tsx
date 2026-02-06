import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { authApi } from '../api/services';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { LoginResponse } from '../types/auth';
import { clearAuth, saveAuth } from '../utils/auth';

const { Title, Paragraph } = Typography;

const cardStyle: React.CSSProperties = {
  maxWidth: 420,
  width: '100%',
  boxShadow:
    '0 16px 48px rgba(102, 126, 234, 0.12), 0 4px 16px rgba(118, 75, 162, 0.06)',
  borderRadius: 16,
  border: '1px solid rgba(102, 126, 234, 0.08)',
};

const wrapperStyle: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  position: 'relative',
  background:
    'radial-gradient(ellipse at 20% 20%, rgba(102, 126, 234, 0.12) 0, transparent 50%), radial-gradient(ellipse at 80% 10%, rgba(118, 75, 162, 0.08) 0, transparent 50%), radial-gradient(ellipse at 50% 80%, rgba(102, 126, 234, 0.05) 0, transparent 50%), #f8f9ff',
  padding: '24px',
};

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
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div
            style={{
              fontSize: '28px',
              fontWeight: 800,
              letterSpacing: '0.06em',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              marginBottom: 12,
              textTransform: 'uppercase' as const,
              fontFamily:
                "'Exo 2', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            }}
          >
            LMeterX
          </div>
          <Title level={4} style={{ marginBottom: 8, color: '#282e58' }}>
            {t('pages.login.title')}
          </Title>
          <Paragraph style={{ margin: 0, color: '#545983' }}>
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
