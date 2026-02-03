/**
 * @file App.tsx
 * @description: Application main component.
 * @author: Charm
 * @copyright: 2025 Charm
 */
import { App as AntApp, Layout } from 'antd';
import React from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Header from './components/Header';
import { LanguageProvider } from './contexts/LanguageContext';
import { NavigationProvider } from './contexts/NavigationContext';
import CommonResults from './pages/CommonResults';
import JobsPage from './pages/Jobs';
import Login from './pages/Login';
import NotFound from './pages/NotFound';
import ResultComparison from './pages/ResultComparison';
import TaskResults from './pages/Results';
import SystemConfiguration from './pages/SystemConfiguration';
import SystemMonitor from './pages/SystemMonitor';
import TaskLog from './pages/TaskLog';
import { isAuthenticated } from './utils/auth';
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

const App: React.FC = () => {
  const location = useLocation();
  const isAuthPage = location.pathname === '/login';

  return (
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
                      <JobsPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path='/results/:id'
                  element={
                    <RequireAuth>
                      <TaskResults />
                    </RequireAuth>
                  }
                />
                <Route
                  path='/common-results/:id'
                  element={
                    <RequireAuth>
                      <CommonResults />
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
                    <RequireAuth>
                      <SystemConfiguration />
                    </RequireAuth>
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
  );
};

export default App;
