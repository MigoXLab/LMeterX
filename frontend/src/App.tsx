/**
 * @file App.tsx
 * @description: Application main component.
 * @author: Charm
 * @copyright: 2025 Charm
 */
import { App as AntApp, ConfigProvider, Layout } from 'antd';
import React from 'react';
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
} from 'react-router-dom';
import Header from './components/Header';
import { LanguageProvider } from './contexts/LanguageContext';
import { NavigationProvider } from './contexts/NavigationContext';
import HttpResults from './pages/HttpResults';
import LlmResults from './pages/LlmResults';
import Login from './pages/Login';
import NotFound from './pages/NotFound';
import ResultComparison from './pages/ResultComparison';
import SystemConfiguration from './pages/SystemConfiguration';
import SystemMonitor from './pages/SystemMonitor';
import TaskLog from './pages/TaskLog';
import TasksPage from './pages/Tasks';
import Collections from './pages/Collections';
import CollectionDetail from './pages/CollectionDetail';
import { isAuthenticated, getStoredUser } from './utils/auth';
import { getLdapEnabled } from './utils/runtimeConfig';

const { Content } = Layout;

const LDAP_ENABLED = getLdapEnabled();

const RequireAuth: React.FC<{ children: React.ReactElement }> = ({
  children,
}) => {
  const location = useLocation();
  if (!LDAP_ENABLED) {
    return children;
  }
  if (!isAuthenticated()) {
    return <Navigate to='/login' state={{ from: location }} replace />;
  }
  return children;
};

const RequireAdmin: React.FC<{ children: React.ReactElement }> = ({
  children,
}) => {
  const location = useLocation();
  if (!LDAP_ENABLED) {
    return children;
  }
  if (!isAuthenticated()) {
    return <Navigate to='/login' state={{ from: location }} replace />;
  }
  const user = getStoredUser();
  if (!user?.is_admin) {
    return <Navigate to='/jobs' replace />;
  }
  return children;
};

const LegacyResultsRedirect: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  if (!id) {
    return <Navigate to='/jobs' replace />;
  }
  return (
    <Navigate
      to={`/llm-results/${id}${location.search}${location.hash}`}
      replace
    />
  );
};

const App: React.FC = () => {
  const location = useLocation();
  const isAuthPage = location.pathname === '/login';

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#667eea',
          colorInfo: '#667eea',
          colorLink: '#667eea',
          colorLinkHover: '#764ba2',
          borderRadius: 8,
          colorBgContainer: '#ffffff',
          colorText: '#282e58',
          colorTextSecondary: '#545983',
          colorBorder: 'rgba(102, 126, 234, 0.15)',
          colorBorderSecondary: 'rgba(102, 126, 234, 0.08)',
          fontFamily:
            "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif",
          controlHeight: 36,
        },
        components: {
          Button: {
            borderRadius: 8,
            controlHeight: 36,
            primaryShadow: '0 2px 8px rgba(102, 126, 234, 0.35)',
          },
          Table: {
            headerBg: '#fafbff',
            headerColor: '#8c8ea6',
            rowHoverBg: 'rgba(102, 126, 234, 0.04)',
            borderColor: 'rgba(102, 126, 234, 0.08)',
          },
          Card: {
            borderRadiusLG: 12,
          },
          Modal: {
            borderRadiusLG: 12,
          },
          Input: {
            activeBorderColor: '#667eea',
            hoverBorderColor: 'rgba(102, 126, 234, 0.5)',
            activeShadow: '0 0 0 2px rgba(102, 126, 234, 0.12)',
          },
          Select: {
            optionSelectedBg: 'rgba(102, 126, 234, 0.1)',
          },
          Tabs: {
            inkBarColor: '#667eea',
            itemSelectedColor: '#667eea',
            itemHoverColor: '#764ba2',
          },
          Menu: {
            itemSelectedBg: 'rgba(102, 126, 234, 0.1)',
            itemSelectedColor: '#667eea',
            itemHoverColor: '#764ba2',
            horizontalItemSelectedColor: '#667eea',
          },
        },
      }}
    >
      <AntApp>
        <LanguageProvider>
          <NavigationProvider>
            <Layout className='app-layout'>
              {!isAuthPage && <Header />}
              <Content className={isAuthPage ? 'auth-content' : 'page-content'}>
                <Routes>
                  <Route
                    path='/login'
                    element={
                      LDAP_ENABLED ? <Login /> : <Navigate to='/jobs' replace />
                    }
                  />
                  <Route
                    path='/'
                    element={
                      <RequireAuth>
                        <Navigate to='/jobs' replace />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/jobs'
                    element={
                      <RequireAuth>
                        <TasksPage />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/llm-results/:id'
                    element={
                      <RequireAuth>
                        <LlmResults />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/results/:id'
                    element={
                      <RequireAuth>
                        <LegacyResultsRedirect />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/http-results/:id'
                    element={
                      <RequireAuth>
                        <HttpResults />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/logs/task/:id'
                    element={
                      <RequireAuth>
                        <TaskLog />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/result-comparison'
                    element={
                      <RequireAuth>
                        <ResultComparison />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/collections'
                    element={
                      <RequireAuth>
                        <Collections />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/collections/:id'
                    element={
                      <RequireAuth>
                        <CollectionDetail />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/system-monitor'
                    element={
                      <RequireAuth>
                        <SystemMonitor />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path='/system-config'
                    element={
                      <RequireAdmin>
                        <SystemConfiguration />
                      </RequireAdmin>
                    }
                  />
                  <Route
                    path='*'
                    element={
                      <RequireAuth>
                        <NotFound />
                      </RequireAuth>
                    }
                  />
                </Routes>
              </Content>
            </Layout>
          </NavigationProvider>
        </LanguageProvider>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;
