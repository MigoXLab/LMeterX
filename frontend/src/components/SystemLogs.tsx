/**
 * @file SystemLogs.tsx
 * @description System logs component
 * @author Charm
 * @copyright 2025
 * */

import {
  DownloadOutlined,
  DownOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  SearchOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Alert, Button, Input, Select, Space, Switch, theme } from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { logApi } from '../api/services';
import { LoadingSpinner } from './ui/LoadingState';

const { Search } = Input;

interface SystemLogsProps {
  serviceName: string;
  displayName: string;
  isActive: boolean;
}

const SystemLogs: React.FC<SystemLogsProps> = ({
  serviceName,
  displayName,
  isActive,
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string>('');
  const [filteredLogs, setFilteredLogs] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [fullscreen, setFullscreen] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tailLines, setTailLines] = useState<number>(100);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const autoRefreshTimerRef = useRef<number | null>(null);
  const { token } = theme.useToken();

  // Track if it should scroll to the bottom
  const shouldScrollToBottom = useRef(true);

  // Automatically calculate height
  const getLogContainerHeight = () => {
    if (fullscreen) {
      return 'calc(100vh - 170px)';
    }
    return 'calc(100vh - 250px)';
  };

  // Scroll to bottom
  const scrollToBottom = () => {
    if (shouldScrollToBottom.current && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  };

  // Listen for scroll events
  useEffect(() => {
    const container = logContainerRef.current;
    // Make sure to add the event listener after the container is rendered and loaded
    if (!container || loading) {
      return;
    }

    let lastScrollTop = container.scrollTop;

    const handleScroll = () => {
      const currentScrollTop = container.scrollTop;
      const scrollDirection = currentScrollTop > lastScrollTop ? 'down' : 'up';
      // Handle the case where scrollTop may be negative when scrolling to the top
      lastScrollTop = currentScrollTop <= 0 ? 0 : currentScrollTop;

      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;

      // When the user scrolls up, pause auto-refresh and show the button
      if (scrollDirection === 'up' && distanceFromBottom > 50) {
        shouldScrollToBottom.current = false;

        // Use functional updates to avoid making state variables a dependency of the effect
        setShowScrollToBottom(prev => {
          if (prev === false) return true; // Only update the state when necessary
          return prev;
        });

        setAutoRefresh(prev => {
          if (prev === true) {
            return false;
          }
          return prev;
        });
      }

      // When the user manually scrolls back to the bottom, hide the button
      if (distanceFromBottom < 10) {
        shouldScrollToBottom.current = true;
        setShowScrollToBottom(prev => {
          if (prev === true) return false; // Only update the state when necessary
          return prev;
        });
      }
    };

    container.addEventListener('scroll', handleScroll);
    // Remove the event listener during effect cleanup
    return () => container.removeEventListener('scroll', handleScroll);
    // The dependency array includes loading to ensure correct execution after the loading state changes
  }, [serviceName, loading]);

  // Unified log acquisition function
  const fetchLogs = async () => {
    // This function is called by initial load and polling
    // It does not directly manage the `loading` state
    try {
      // A new fetch attempt will clear old polling errors
      if (fetchError) setFetchError(null);

      const contentResponse = await logApi.getServiceLogContent(
        serviceName,
        0,
        tailLines
      );

      if (
        contentResponse.data &&
        typeof contentResponse.data.content === 'string'
      ) {
        const newLogs = contentResponse.data.content;
        setLogs(newLogs);

        // If a search term exists, reapply the filter on the new logs
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
      } else {
        setLogs('');
        setFilteredLogs('');
      }
      // Clear serious errors after successful acquisition
      if (error) setError(null);
    } catch (err: any) {
      const errorMessage =
        err?.response?.data?.error ||
        err?.message ||
        `Failed to fetch ${displayName}`;
      // Show serious errors on initial load, and non-blocking errors on polling
      if (loading) {
        setError(errorMessage);
      } else {
        setFetchError(errorMessage);
      }
    } finally {
      if (shouldScrollToBottom.current) {
        setTimeout(scrollToBottom, 100);
      }
    }
  };

  // Effect for initial load and when service or line count settings change
  useEffect(() => {
    // Reset component state for the new view
    setSearchTerm('');
    shouldScrollToBottom.current = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      setFetchError(null);
      await fetchLogs();
      setLoading(false);
    };

    load();
  }, [serviceName, tailLines]);

  // Effect for auto-refresh polling
  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
    }

    if (isActive && autoRefresh && !loading) {
      autoRefreshTimerRef.current = window.setInterval(() => {
        // If there is an error, pause polling
        if (!fetchError) {
          fetchLogs();
        }
      }, 3000);
    }

    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [isActive, autoRefresh, loading, fetchError, serviceName, tailLines]);

  // Add window size change listener
  useEffect(() => {
    const handleResize = () => {
      // Force re-render to adapt to the new window size
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

    // When a search is triggered, pause auto-refresh
    if (value.trim()) {
      if (autoRefresh) {
        setAutoRefresh(false);
      }
    }

    if (!value.trim()) {
      setFilteredLogs(logs);
      return;
    }

    // Filter lines containing the search term
    const lines = logs.split('\n');
    const filtered = lines
      .filter(line => line.toLowerCase().includes(value.toLowerCase()))
      .join('\n');

    setFilteredLogs(filtered);
  };

  const handleScrollToBottomClick = () => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
    shouldScrollToBottom.current = true;
    setShowScrollToBottom(false);

    // Restart polling after 2 seconds
    setTimeout(() => {
      setAutoRefresh(true);
      // message.success('Log auto-refresh resumed');
    }, 2000);
  };

  const handleDownload = () => {
    // Create a download link using the current log content
    if (logs) {
      const blob = new Blob([logs], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${serviceName}_log_${new Date().toISOString().slice(0, 10)}.txt`; // Update download file name
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  const toggleFullscreen = () => {
    setFullscreen(!fullscreen);
  };

  // Format log line
  const formatLogLine = (line: string) => {
    // Only match log level, ensure there's a space or line start, and there's a space or colon
    const levelRegex =
      /(^|\s)(INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)(\s|:)/i;
    const levelMatch = line.match(levelRegex);

    if (!levelMatch) {
      // Lines without log level use normal style
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

    // Determine color based on log level
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

    // Find full match position (including prefix and suffix)
    const fullMatchIndex = line.indexOf(levelMatch[0]);
    const levelIndex = fullMatchIndex + levelMatch[1].length; // Adjust real log level start position
    const levelEnd = levelIndex + levelMatch[2].length; // Log level end position

    // Split log line
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

  // Manual refresh and clear error state
  const handleManualRefresh = () => {
    const refresh = async () => {
      setLoading(true);
      setError(null);
      setFetchError(null);
      await fetchLogs();
      setLoading(false);
    };
    refresh();
  };

  if (loading) {
    return (
      <div style={{ height: '80vh' }}>
        <LoadingSpinner
          text={t('components.systemLogs.loadingData', { displayName })}
          size='large'
          className='flex justify-center align-center'
        />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className='flex justify-center align-center'
        style={{ height: '80vh' }}
      >
        <Alert
          description={error}
          type='error'
          showIcon
          style={{ background: 'transparent', border: 'none' }}
        />
      </div>
    );
  }

  if (!loading && !logs && !error) {
    return (
      <div
        className='flex justify-center align-center'
        style={{ height: '80vh' }}
      >
        <Alert
          description={t('components.systemLogs.noLogsAvailable', {
            displayName,
          })}
          type='info'
          showIcon
          style={{ background: 'transparent', border: 'none' }}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        padding: fullscreen ? '0' : '0',
        height: fullscreen ? '100vh' : 'auto',
        width: fullscreen ? '100vw' : 'auto',
        position: fullscreen ? 'fixed' : 'relative',
        top: fullscreen ? 0 : 'auto',
        left: fullscreen ? 0 : 'auto',
        zIndex: fullscreen ? 1000 : 'auto',
        backgroundColor: fullscreen ? token.colorBgContainer : 'transparent',
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
        <Space wrap size='middle'>
          <Select
            value={tailLines}
            onChange={value => setTailLines(value)}
            className='w-140'
            style={{ minWidth: '140px' }}
          >
            <Select.Option value={100}>
              {t('components.systemLogs.last100Lines')}
            </Select.Option>
            <Select.Option value={500}>
              {t('components.systemLogs.last500Lines')}
            </Select.Option>
            <Select.Option value={1000}>
              {t('components.systemLogs.last1000Lines')}
            </Select.Option>
            <Select.Option value={0}>
              {t('components.systemLogs.allLogs')}
            </Select.Option>
          </Select>
          <Switch
            checkedChildren={t('components.systemLogs.autoRefresh')}
            unCheckedChildren={t('components.systemLogs.stopRefresh')}
            checked={autoRefresh}
            onChange={setAutoRefresh}
          />
          <Button icon={<SyncOutlined />} onClick={handleManualRefresh}>
            {t('components.systemLogs.refreshLogs')}
          </Button>
          <Search
            placeholder={t('components.systemLogs.searchLogContent')}
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
            {t('components.systemLogs.downloadLogs')}
          </Button>
          <Button
            icon={
              fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />
            }
            onClick={toggleFullscreen}
          >
            {fullscreen
              ? t('components.systemLogs.exitFullscreen')
              : t('components.systemLogs.fullscreen')}
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
              message={t('components.systemLogs.searchResults', { searchTerm })}
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

          {/* Display incremental fetch error */}
          {fetchError && (
            <Alert
              message={t('components.systemLogs.autoRefreshError')}
              description={
                <div>
                  <p>{fetchError}</p>
                  <p>{t('components.systemLogs.autoRefreshPaused')}</p>
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
                  {t('components.systemLogs.refreshNow')}
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
  );
};

export default SystemLogs;
