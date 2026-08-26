/**
 * @file EngineLogViewer.tsx
 * @description Multi-cluster engine log viewer with inline cluster/engine selection.
 * @author Charm
 * @copyright 2025
 */

import { Alert, Select, Space } from 'antd';
import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { monitoringApi } from '../api/services';
import SystemLogs from './SystemLogs';
import { LoadingSpinner } from './ui/LoadingState';

interface ClusterEngines {
  cluster_id: string;
  cluster_name: string;
  engines: Array<{
    engine_id: string;
    status: string;
    last_seen: number;
  }>;
}

interface EngineLogViewerProps {
  isActive: boolean;
}

const EngineLogViewer: React.FC<EngineLogViewerProps> = ({ isActive }) => {
  const { t } = useTranslation();
  const [clusters, setClusters] = useState<ClusterEngines[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCluster, setActiveCluster] = useState<string>('');
  const [selectedEngines, setSelectedEngines] = useState<
    Record<string, string>
  >({});

  const fetchClusters = useCallback(async () => {
    try {
      const resp = await monitoringApi.getEnginesByCluster();
      const data = (resp.data as any)?.data ?? [];
      setClusters(data);

      if (data.length > 0) {
        setActiveCluster(prev => prev || data[0].cluster_id);
      }

      setSelectedEngines(prev => {
        const next = { ...prev };
        let changed = false;
        data.forEach((cluster: ClusterEngines) => {
          if (cluster.engines.length > 0 && !next[cluster.cluster_id]) {
            next[cluster.cluster_id] = cluster.engines[0].engine_id;
            changed = true;
          }
        });
        return changed ? next : prev;
      });

      setError(null);
    } catch (e: any) {
      setError(
        e?.message || t('pages.systemMonitor.fetchFailed', 'Failed to fetch')
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (isActive) {
      fetchClusters();
    }
  }, [isActive, fetchClusters]);

  if (loading) {
    return (
      <div style={{ height: '80vh' }}>
        <LoadingSpinner
          text={t('components.systemLogs.loadingData', {
            displayName: t('components.systemLogs.engineLogs', 'Engine Logs'),
          })}
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

  if (clusters.length === 0) {
    return (
      <div
        className='flex justify-center align-center'
        style={{ height: '80vh' }}
      >
        <Alert
          description={t(
            'components.engineLogViewer.noEngines',
            'No online engines found'
          )}
          type='info'
          showIcon
          style={{ background: 'transparent', border: 'none' }}
        />
      </div>
    );
  }

  const activeClusterData = clusters.find(c => c.cluster_id === activeCluster);
  const currentEngine = selectedEngines[activeCluster];

  return (
    <div>
      <Space style={{ marginBottom: 16 }} size='middle' wrap>
        {clusters.length > 1 && (
          <Select
            style={{ minWidth: 180 }}
            value={activeCluster}
            onChange={(v: string) => setActiveCluster(v)}
            options={clusters.map(c => ({
              label: (
                <span>
                  {c.cluster_name}
                  <span style={{ marginLeft: 6, fontSize: 12, opacity: 0.7 }}>
                    ({c.engines.length})
                  </span>
                </span>
              ),
              value: c.cluster_id,
            }))}
          />
        )}
        <Select
          style={{ minWidth: 220 }}
          placeholder={t(
            'components.engineLogViewer.selectEngine',
            'Select Engine'
          )}
          value={currentEngine}
          onChange={(v: string) =>
            setSelectedEngines(prev => ({ ...prev, [activeCluster]: v }))
          }
          options={
            activeClusterData?.engines.map(e => ({
              label: (
                <span>
                  {e.engine_id}
                  <span
                    style={{
                      marginLeft: 8,
                      fontSize: 12,
                      color:
                        e.status === 'online'
                          ? '#52c41a'
                          : e.status === 'busy'
                            ? '#faad14'
                            : '#999',
                    }}
                  >
                    ({e.status})
                  </span>
                </span>
              ),
              value: e.engine_id,
            })) ?? []
          }
          showSearch
        />
      </Space>

      {currentEngine ? (
        <SystemLogs
          serviceName='engine'
          displayName={`${activeClusterData?.cluster_name ?? ''} / ${currentEngine}`}
          isActive={isActive}
          engineId={currentEngine}
          clusterId={activeCluster}
        />
      ) : (
        <Alert
          description={t(
            'components.engineLogViewer.selectEngineHint',
            'Please select an engine to view logs'
          )}
          type='info'
          showIcon
          style={{ background: 'transparent', border: 'none' }}
        />
      )}
    </div>
  );
};

export default EngineLogViewer;
