/**
 * @file TaskLog.tsx
 * @description Task log page
 * @author Charm
 * @copyright 2025
 */

import {
  DownloadOutlined,
  DownOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  MonitorOutlined,
  SearchOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Input,
  message,
  Select,
  Space,
  Switch,
  theme,
  Tooltip,
  Typography,
} from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { jobApi, logApi } from '../api/services';
import { LoadingSpinner } from '../components/ui/LoadingState';
import { PageHeader } from '../components/ui/PageHeader';
import { Job } from '../types/job';

const { Search } = Input;
const { Text } = Typography;

const FINAL_TASK_STATUSES = [
  'COMPLETED',
  'FAILED',
  'STOPPED',
  'CANCELLED',
  'ERROR',
  'FAILED_REQUESTS',
];

const isTaskInFinalState = (status: string | null | undefined): boolean => {
  if (!status) return false;
  return FINAL_TASK_STATUSES.includes(status.toUpperCase());
};

const TaskLogs: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string>('');
  const [filteredLogs, setFilteredLogs] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [logUrl, setLogUrl] = useState<string>('');
  const [fullscreen, setFullscreen] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tailLines, setTailLines] = useState<number>(100);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [task, setTask] = useState<Job | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [isStatusRefreshing, setIsStatusRefreshing] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const autoRefreshTimerRef = useRef<number | null>(null);
  const errorRetryTimerRef = useRef<number | null>(null);
  const { token } = theme.useToken();
  const shouldScrollToBottom = useRef(true);

  const getLogContainerHeight = () => {
    if (fullscreen) {
      return 'calc(100vh - 170px)';
    }
    return 'calc(100vh - 250px)';
  };

  const scrollToBottom = () => {
    if (shouldScrollToBottom.current && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    const container = logContainerRef.current;
    if (!container || loading) {
      return;
    }

    let lastScrollTop = container.scrollTop;

    const handleScroll = () => {
      const currentScrollTop = container.scrollTop;
      const scrollDirection = currentScrollTop > lastScrollTop ? 'down' : 'up';
      lastScrollTop = currentScrollTop <= 0 ? 0 : currentScrollTop;

      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;

      if (scrollDirection === 'up' && distanceFromBottom > 50) {
        shouldScrollToBottom.current = false;
        setShowScrollToBottom(prev => (!prev ? true : prev));
        setAutoRefresh(prev => {
          if (prev) {
            return false;
          }
          return prev;
        });
      }

      if (distanceFromBottom < 10) {
        shouldScrollToBottom.current = true;
        setShowScrollToBottom(prev => (prev ? false : prev));
      }
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [id, loading]);

  const fetchLogs = async () => {
    if (!id) return;

    try {
      if (fetchError) setFetchError(null);

      const contentResponse = await logApi.getTaskLogContent(id, 0, tailLines);

      if (contentResponse.data) {
        const newLogs = contentResponse.data.content || '';
        setLogs(newLogs);

        if (searchTerm.trim()) {
          const lines = newLogs.split('\n');
          const filtered = lines
            .filter(line =>
              line.toLowerCase().includes(searchTerm.toLowerCase())
            )
            .join('\n');
          setFilteredLogs(filtered);
        } else {
          setFilteredLogs(newLogs);
        }
        setLogUrl(contentResponse.data.log_url || '');
      } else {
        setLogs('');
        setFilteredLogs('');
      }
      if (error) setError(null);
    } catch (err: any) {
      const errorMsg =
        err.response?.data?.error || err.message || 'Failed to fetch task logs';
      if (loading) {
        setError(errorMsg);
      } else {
        setFetchError(errorMsg);
      }
    } finally {
      if (shouldScrollToBottom.current) {
        setTimeout(scrollToBottom, 100);
      }
    }
  };

  const fetchTaskStatus = async (isInitialLoad = false) => {
    if (!id) return;

    if (!isInitialLoad) {
      setIsStatusRefreshing(true);
    }

    try {
      if (isInitialLoad) {
        const taskResponse = await jobApi.getJob(id);
        if (taskResponse.data) {
          const currentTask = taskResponse.data;
          setTask(currentTask);
          if (isTaskInFinalState(currentTask.status)) {
            setAutoRefresh(false);
          }
          return currentTask;
        }
      } else {
        const taskResponse = await jobApi.getJobStatus(id);
        if (taskResponse.data) {
          const currentTaskStatus = taskResponse.data;
          const updatedTask = {
            ...task,
            id: currentTaskStatus.id,
            name: currentTaskStatus.name,
            status: currentTaskStatus.status,
            error_message: currentTaskStatus.error_message,
            updated_at: currentTaskStatus.updated_at,
          } as Job;

          setTask(updatedTask);

          if (isTaskInFinalState(currentTaskStatus.status)) {
            setAutoRefresh(false);
          }
          return updatedTask;
        }
      }
    } catch (err) {
      try {
        const taskResponse = await jobApi.getJob(id);
        if (taskResponse.data) {
          const currentTask = taskResponse.data;
          setTask(currentTask);
          if (isTaskInFinalState(currentTask.status)) {
            setAutoRefresh(false);
          }
          return currentTask;
        }
      } catch (fallbackErr) {
        // Failed to fetch task info as fallback
      }
    } finally {
      if (!isInitialLoad) {
        setIsStatusRefreshing(false);
      }
    }
    return null;
  };

  useEffect(() => {
    if (!id) {
      setError('Task ID not provided.');
      setLoading(false);
      return;
    }

    shouldScrollToBottom.current = true;
    setSearchTerm('');

    const load = async () => {
      setLoading(true);
      setError(null);
      setFetchError(null);
      setLogs('');
      setFilteredLogs('');
      setLogUrl('');

      await fetchTaskStatus(true);
      await fetchLogs();

      setLoading(false);
    };

    load();
  }, [id, tailLines]);

  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
    }

    const isFinal = isTaskInFinalState(task?.status);

    if (autoRefresh && !loading && !isFinal) {
      autoRefreshTimerRef.current = window.setInterval(async () => {
        if (!fetchError) {
          const updatedTask = await fetchTaskStatus();
          if (updatedTask && isTaskInFinalState(updatedTask.status)) {
            return;
          }
          await fetchLogs();
        }
      }, 3000);
    }

    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [autoRefresh, loading, fetchError, task, id, tailLines]);

  useEffect(() => {
    const handleResize = () => {
      if (logContainerRef.current) {
        const currentHeight = logContainerRef.current.style.height;
        logContainerRef.current.style.height = '0px';
        setTimeout(() => {
          if (logContainerRef.current) {
            logContainerRef.current.style.height = currentHeight;
          }
        }, 0);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    if (!value.trim()) {
      setFilteredLogs(logs);
      return;
    }

    const lines = logs.split('\n');
    const filtered = lines
      .filter(line => line.toLowerCase().includes(value.toLowerCase()))
      .join('\n');

    setFilteredLogs(filtered);
  };

  const handleDownload = () => {
    if (logUrl) {
      window.open(logUrl, '_blank');
      return;
    }

    if (logs) {
      const blob = new Blob([logs], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `task_${id}_log.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } else {
      message.warning(t('pages.taskLog.logEmpty'));
    }
  };

  const toggleFullscreen = () => {
    setFullscreen(!fullscreen);
  };

  const formatLogLine = (line: string) => {
    // Handle empty lines - ensure they have proper height
    if (line.trim() === '') {
      return (
        <div
          className='log-line'
          style={{
            minHeight: '1.8em',
            lineHeight: '1.8',
            padding: '2px 0',
          }}
        >
          &nbsp;
        </div>
      );
    }

    const levelRegex =
      /(^|\s)(INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)(\s|:)/i;
    const levelMatch = line.match(levelRegex);

    if (!levelMatch) {
      return (
        <div
          className='log-line'
          style={{
            minHeight: '1.8em',
            lineHeight: '1.8',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            padding: '2px 0',
          }}
        >
          {line}
        </div>
      );
    }

    const level = levelMatch[2].toUpperCase();
    let levelColor = '';

    switch (level) {
      case 'ERROR':
      case 'FATAL':
      case 'CRITICAL':
        levelColor = token.colorError;
        break;
      case 'WARN':
      case 'WARNING':
        levelColor = token.colorWarning;
        break;
      case 'INFO':
        levelColor = token.colorInfo;
        break;
      case 'DEBUG':
        levelColor = token.colorSuccess;
        break;
      default:
        levelColor = token.colorText;
    }

    const fullMatchIndex = line.indexOf(levelMatch[0]);
    const levelIndex = fullMatchIndex + levelMatch[1].length;
    const levelEnd = levelIndex + levelMatch[2].length;

    const beforeLevel = line.substring(0, levelIndex);
    const levelPart = line.substring(levelIndex, levelEnd);
    const afterLevel = line.substring(levelEnd);

    return (
      <div
        className='log-line'
        style={{
          minHeight: '1.8em',
          lineHeight: '1.8',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          padding: '2px 0',
        }}
      >
        <span>{beforeLevel}</span>
        <span className='log-level-text' style={{ color: levelColor }}>
          {levelPart}
        </span>
        <span>{afterLevel}</span>
      </div>
    );
  };

  const handleScrollToBottomClick = () => {
    scrollToBottom();
    setShowScrollToBottom(false);
  };

  const handleManualRefresh = async () => {
    if (!id) return;

    const refresh = async () => {
      setLoading(true);
      setError(null);
      setFetchError(null);
      await fetchTaskStatus();
      await fetchLogs();
      setLoading(false);
      message.success(t('pages.taskLog.refreshLogs'));
    };

    try {
      await refresh();
    } catch (error) {
      setLoading(false);
    }
  };

  useEffect(() => {
    return () => {
      if (errorRetryTimerRef.current) {
        clearTimeout(errorRetryTimerRef.current);
      }
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, []);

  if (loading) {
    return (
      <div style={{ height: '80vh' }}>
        <LoadingSpinner
          text='Loading task and log data...'
          size='large'
          className='flex justify-center align-center'
        />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={fullscreen ? '' : 'page-container'}
        style={{
          padding: fullscreen ? '0' : undefined,
          height: fullscreen ? '100vh' : 'auto',
          width: fullscreen ? '100vw' : 'auto',
          position: fullscreen ? 'fixed' : 'relative',
          top: fullscreen ? 0 : 'auto',
          left: fullscreen ? 0 : 'auto',
          zIndex: fullscreen ? 1000 : 'auto',
          backgroundColor: fullscreen ? token.colorBgContainer : 'transparent',
        }}
      >
        {!fullscreen && (
          <div className='page-header-wrapper'>
            <PageHeader
              title={t('pages.taskLog.title', '任务日志')}
              icon={<MonitorOutlined />}
              level={3}
            />
          </div>
        )}
        <div className={fullscreen ? '' : 'jobs-content-wrapper'}>
          <div
            className='flex justify-center align-center'
            style={{ height: '60vh' }}
          >
            <Alert
              description={error}
              type='error'
              showIcon
              style={{ background: 'transparent', border: 'none' }}
            />
          </div>
        </div>
      </div>
    );
  }

  if (task && !logs && !loading && !error && !fetchError) {
    return (
      <div
        className={fullscreen ? '' : 'page-container'}
        style={{
          padding: fullscreen ? '0' : undefined,
          height: fullscreen ? '100vh' : 'auto',
          width: fullscreen ? '100vw' : 'auto',
          position: fullscreen ? 'fixed' : 'relative',
          top: fullscreen ? 0 : 'auto',
          left: fullscreen ? 0 : 'auto',
          zIndex: fullscreen ? 1000 : 'auto',
          backgroundColor: fullscreen ? token.colorBgContainer : 'transparent',
        }}
      >
        {!fullscreen && (
          <div className='page-header-wrapper mb-24'>
            <PageHeader
              title={t('pages.taskLog.title', '任务日志')}
              icon={<MonitorOutlined />}
              level={3}
            />
          </div>
        )}
        <div className={fullscreen ? '' : 'jobs-content-wrapper'}>
          <div
            className='flex justify-center align-center flex-column'
            style={{ minHeight: '200px' }}
          >
            <Alert
              description={
                isTaskInFinalState(task.status)
                  ? t('pages.taskLog.logEmpty')
                  : t('pages.taskLog.logEmpty')
              }
              type='info'
              showIcon
              style={{ background: 'transparent', border: 'none' }}
            />
            <Space className='mt-16'>
              <Button icon={<SyncOutlined />} onClick={handleManualRefresh}>
                {t('pages.taskLog.refreshLogs')}
              </Button>
              <Switch
                checkedChildren={t('pages.taskLog.autoRefresh')}
                unCheckedChildren={t('pages.taskLog.autoRefresh')}
                checked={autoRefresh}
                onChange={checked => {
                  setAutoRefresh(checked);
                  if (checked) {
                    setFetchError(null);
                  }
                }}
                disabled={isTaskInFinalState(task?.status)}
              />
            </Space>
          </div>
        </div>
      </div>
    );
  }

  if (fullscreen) {
    return (
      <div
        style={{
          padding: '0',
          height: '100vh',
          width: '100vw',
          position: 'fixed',
          top: 0,
          left: 0,
          zIndex: 1000,
          backgroundColor: token.colorBgContainer,
        }}
      >
        {/* Toolbar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 0',
            marginBottom: '16px',
            borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Text type='secondary' style={{ fontSize: '14px' }}>
              {t('pages.taskLog.taskId', '任务ID')}:{' '}
            </Text>
            <Text style={{ fontSize: '14px' }}>{id}</Text>
          </div>
          <Space wrap size='middle'>
            <Select
              value={tailLines}
              onChange={value => setTailLines(value)}
              className='w-140'
              style={{ minWidth: '140px' }}
            >
              <Select.Option value={100}>
                {t('pages.taskLog.last100Lines')}
              </Select.Option>
              <Select.Option value={500}>
                {t('pages.taskLog.last500Lines')}
              </Select.Option>
              <Select.Option value={1000}>
                {t('pages.taskLog.last1000Lines')}
              </Select.Option>
              <Select.Option value={0}>
                {t('pages.taskLog.allLogs')}
              </Select.Option>
            </Select>
            <Switch
              checkedChildren={t('pages.taskLog.autoRefresh')}
              unCheckedChildren={t('pages.taskLog.stopRefresh')}
              checked={autoRefresh}
              onChange={checked => {
                setAutoRefresh(checked);
                if (checked) {
                  setFetchError(null);
                }
              }}
              disabled={isTaskInFinalState(task?.status)}
            />
            <Button icon={<SyncOutlined />} onClick={handleManualRefresh}>
              {t('pages.taskLog.refreshLogs')}
            </Button>
            <Search
              placeholder={t('pages.taskLog.searchLogContent')}
              allowClear
              enterButton={<SearchOutlined />}
              onSearch={handleSearch}
              className='w-250'
              style={{ minWidth: '250px' }}
            />
            <Button
              type='primary'
              icon={<DownloadOutlined />}
              onClick={handleDownload}
            >
              {t('pages.taskLog.downloadLogs')}
            </Button>
            <Button
              icon={
                fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />
              }
              onClick={toggleFullscreen}
            >
              {fullscreen
                ? t('pages.taskLog.exitFullscreen')
                : t('pages.taskLog.fullscreen')}
            </Button>
          </Space>
        </div>

        {/* Log Container */}
        <div style={{ position: 'relative' }}>
          <div
            ref={logContainerRef}
            className='custom-scrollbar'
            style={{
              backgroundColor: 'transparent',
              padding: '20px',
              borderRadius: '0',
              height: getLogContainerHeight(),
              overflowY: 'auto',
              fontFamily:
                '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace',
              fontSize: '14px',
              lineHeight: '1.8',
              border: 'none',
              boxShadow: 'none',
            }}
          >
            {searchTerm && (
              <Alert
                message={t('pages.taskLog.searchResults', { searchTerm })}
                type='info'
                showIcon
                closable
                onClose={() => {
                  setSearchTerm('');
                  setFilteredLogs(logs);
                }}
                className='mb-16'
              />
            )}

            {fetchError && (
              <Alert
                message={t('pages.taskLog.autoRefreshError')}
                description={
                  <div>
                    <p>{fetchError}</p>
                    <p>{t('pages.taskLog.autoRefreshPaused')}</p>
                  </div>
                }
                type='warning'
                showIcon
                icon={<WarningOutlined />}
                closable
                action={
                  <Button
                    size='small'
                    type='primary'
                    onClick={handleManualRefresh}
                  >
                    {t('pages.taskLog.refreshNow')}
                  </Button>
                }
                onClose={() => setFetchError(null)}
                className='mb-16'
              />
            )}

            {filteredLogs.split('\n').map((line, index) => (
              <React.Fragment key={index}>{formatLogLine(line)}</React.Fragment>
            ))}
          </div>
          {showScrollToBottom && (
            <Button
              type='text'
              onClick={handleScrollToBottomClick}
              style={{
                position: 'absolute',
                bottom: '24px',
                right: '24px',
                zIndex: 10,
                borderRadius: '50%',
                width: '40px',
                height: '40px',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
              }}
              icon={
                <DownOutlined
                  style={{ fontSize: '20px', color: token.colorPrimary }}
                />
              }
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className='page-container'>
      <div className='page-header-wrapper mb-24'>
        <PageHeader
          title={t('pages.taskLog.title', '任务日志')}
          icon={<MonitorOutlined />}
          level={3}
          extra={
            isStatusRefreshing && (
              <Tooltip title='refreshing...'>
                <span className='ml-8'>
                  <LoadingSpinner size='small' showText={false} />
                </span>
              </Tooltip>
            )
          }
        />
      </div>
      <div className='jobs-content-wrapper'>
        {/* Toolbar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 0',
            marginBottom: '16px',
            borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Text type='secondary' style={{ fontSize: '14px' }}>
              {t('pages.taskLog.taskId', '任务ID')}:{' '}
            </Text>
            <Text style={{ fontSize: '14px' }}>{id}</Text>
          </div>
          <Space wrap size='middle'>
            <Select
              value={tailLines}
              onChange={value => setTailLines(value)}
              className='w-140'
              style={{ minWidth: '140px' }}
            >
              <Select.Option value={100}>
                {t('pages.taskLog.last100Lines')}
              </Select.Option>
              <Select.Option value={500}>
                {t('pages.taskLog.last500Lines')}
              </Select.Option>
              <Select.Option value={1000}>
                {t('pages.taskLog.last1000Lines')}
              </Select.Option>
              <Select.Option value={0}>
                {t('pages.taskLog.allLogs')}
              </Select.Option>
            </Select>
            <Switch
              checkedChildren={t('pages.taskLog.autoRefresh')}
              unCheckedChildren={t('pages.taskLog.stopRefresh')}
              checked={autoRefresh}
              onChange={checked => {
                setAutoRefresh(checked);
                if (checked) {
                  setFetchError(null);
                }
              }}
              disabled={isTaskInFinalState(task?.status)}
            />
            <Button icon={<SyncOutlined />} onClick={handleManualRefresh}>
              {t('pages.taskLog.refreshLogs')}
            </Button>
            <Search
              placeholder={t('pages.taskLog.searchLogContent')}
              allowClear
              enterButton={<SearchOutlined />}
              onSearch={handleSearch}
              className='w-250'
              style={{ minWidth: '250px' }}
            />
            <Button
              type='primary'
              icon={<DownloadOutlined />}
              onClick={handleDownload}
            >
              {t('pages.taskLog.downloadLogs')}
            </Button>
            <Button
              icon={
                fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />
              }
              onClick={toggleFullscreen}
            >
              {fullscreen
                ? t('pages.taskLog.exitFullscreen')
                : t('pages.taskLog.fullscreen')}
            </Button>
          </Space>
        </div>

        {/* Log Container */}
        <div style={{ position: 'relative' }}>
          <div
            ref={logContainerRef}
            className='custom-scrollbar'
            style={{
              backgroundColor: 'transparent',
              padding: '20px',
              borderRadius: '0',
              height: getLogContainerHeight(),
              overflowY: 'auto',
              fontFamily:
                '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace',
              fontSize: '14px',
              lineHeight: '1.8',
              border: 'none',
              boxShadow: 'none',
            }}
          >
            {searchTerm && (
              <Alert
                message={t('pages.taskLog.searchResults', { searchTerm })}
                type='info'
                showIcon
                closable
                onClose={() => {
                  setSearchTerm('');
                  setFilteredLogs(logs);
                }}
                className='mb-16'
              />
            )}

            {fetchError && (
              <Alert
                message={t('pages.taskLog.autoRefreshError')}
                description={
                  <div>
                    <p>{fetchError}</p>
                    <p>{t('pages.taskLog.autoRefreshPaused')}</p>
                  </div>
                }
                type='warning'
                showIcon
                icon={<WarningOutlined />}
                closable
                action={
                  <Button
                    size='small'
                    type='primary'
                    onClick={handleManualRefresh}
                  >
                    {t('pages.taskLog.refreshNow')}
                  </Button>
                }
                onClose={() => setFetchError(null)}
                className='mb-16'
              />
            )}

            {filteredLogs.split('\n').map((line, index) => (
              <React.Fragment key={index}>{formatLogLine(line)}</React.Fragment>
            ))}
          </div>
          {showScrollToBottom && (
            <Button
              type='text'
              onClick={handleScrollToBottomClick}
              style={{
                position: 'absolute',
                bottom: fullscreen ? '24px' : '24px',
                right: '24px',
                zIndex: 10,
                borderRadius: '50%',
                width: '40px',
                height: '40px',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
              }}
              icon={
                <DownOutlined
                  style={{ fontSize: '20px', color: token.colorPrimary }}
                />
              }
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default TaskLogs;
