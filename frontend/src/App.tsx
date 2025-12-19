/**
 * @file App.tsx
 * @description: Application main component.
 * @author: Charm
 * @copyright: 2025 Charm
 */
import { App as AntApp, Layout } from 'antd';
import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import { LanguageProvider } from './contexts/LanguageContext';
import { NavigationProvider } from './contexts/NavigationContext';
import JobsPage from './pages/Jobs';
import CommonResults from './pages/CommonResults';
import NotFound from './pages/NotFound';
import ResultComparison from './pages/ResultComparison';
import TaskResults from './pages/Results';
import SystemConfiguration from './pages/SystemConfiguration';
import SystemMonitor from './pages/SystemMonitor';
import TaskLog from './pages/TaskLog';

const { Content } = Layout;

const App: React.FC = () => {
  return (
    <AntApp>
      <LanguageProvider>
        <NavigationProvider>
          <Layout className='app-layout'>
            <Header />
            <Layout className='app-layout-content'>
              <Sidebar />
              <Content className='page-content'>
                <Routes>
                  <Route path='/' element={<Navigate to='/jobs' replace />} />
                  <Route path='/jobs' element={<JobsPage />} />
                  <Route path='/results/:id' element={<TaskResults />} />
                  <Route
                    path='/common-results/:id'
                    element={<CommonResults />}
                  />
                  <Route path='/logs/task/:id' element={<TaskLog />} />
                  <Route
                    path='/result-comparison'
                    element={<ResultComparison />}
                  />
                  <Route path='/system-monitor' element={<SystemMonitor />} />
                  <Route
                    path='/system-config'
                    element={<SystemConfiguration />}
                  />
                  <Route path='*' element={<NotFound />} />
                </Routes>
              </Content>
            </Layout>
          </Layout>
        </NavigationProvider>
      </LanguageProvider>
    </AntApp>
  );
};

export default App;
