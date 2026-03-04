/**
 * @file EngineResources.tsx
 * @description Engine instance resource monitoring component.
 *   Displays historical trend line charts for CPU, Memory and Network
 *   Bandwidth pulled from VictoriaMetrics via the monitoring API.
 * @author Charm
 * @copyright 2025
 */

import { ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Col, Row, Select, Space, Statistic, theme } from 'antd';
import ReactECharts from 'echarts-for-react';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { monitoringApi } from '../api/services';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface EngineInfo {
  engine_id: string;
  last_seen: number;
  cpu_percent: number;
}

interface SeriesPoint {
  metric: Record<string, string>;
  values: Array<[number, number]>;
}

interface ResourceData {
  cpu_percent: SeriesPoint[];
  cpu_limit_cores: SeriesPoint[];
  memory_used_bytes: SeriesPoint[];
  memory_total_bytes: SeriesPoint[];
  memory_percent: SeriesPoint[];
  network_sent_bytes_per_sec: SeriesPoint[];
  network_recv_bytes_per_sec: SeriesPoint[];
  [key: string]: SeriesPoint[];
}

interface EngineResourcesProps {
  /** Whether this tab is currently visible (controls polling). */
  isActive: boolean;
  /** Optional initial engine ID to pre-select (e.g. from URL query param). */
  initialEngineId?: string;
}

/* ------------------------------------------------------------------ */
/*  Time range presets                                                 */
/* ------------------------------------------------------------------ */

const TIME_RANGES = [
  { label: '5m', value: 300 },
  { label: '15m', value: 900 },
  { label: '30m', value: 1800 },
  { label: '1h', value: 3600 },
  { label: '3h', value: 10800 },
  { label: '6h', value: 21600 },
  { label: '24h', value: 86400 },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const formatChartTime = (ts: number): string => {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
};

const formatTooltipTime = (ts: number): string => {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
};

/** Format bytes into a human-friendly string. */
const formatBytes = (bytes: number, decimals = 1): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(
    Math.floor(Math.log(Math.abs(bytes)) / Math.log(k)),
    sizes.length - 1
  );
  const val = bytes / k ** i;
  // When decimals=0 and the converted value < 10, use 1 decimal place
  // to avoid two distinct tick values (e.g. 1.9 GB vs 2.4 GB)
  // both rounding to the same "2 GB" label.
  const d = decimals === 0 && val >= 1 && val < 10 ? 1 : decimals;
  return `${val.toFixed(d)} ${sizes[i]}`;
};

/** Format bytes/s into a human-friendly throughput string. */
const formatBytesPerSec = (bps: number, decimals = 1): string => {
  if (bps === 0) return '0 B/s';
  const k = 1024;
  const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
  const i = Math.min(
    Math.floor(Math.log(Math.abs(bps)) / Math.log(k)),
    sizes.length - 1
  );
  const val = bps / k ** i;
  // When decimals=0 and the converted value < 10, use 1 decimal place
  // to avoid two distinct tick values (e.g. 1.1 MB/s vs 1.4 MB/s)
  // both rounding to the same "1 MB/s" label.
  const d = decimals === 0 && val >= 1 && val < 10 ? 1 : decimals;
  return `${val.toFixed(d)} ${sizes[i]}`;
};

/**
 * Compute nice Y-axis { max, interval } so that tick labels display as
 * round, human-readable values (e.g. 0, 500 KB, 1 MB, 1.5 MB, 2 MB).
 * Works for both byte and byte/s axes.
 */
const niceByteAxis = (
  maxVal: number,
  targetSplits = 5
): { max: number; interval: number } => {
  if (maxVal <= 0) return { max: 1024, interval: 1024 };
  const k = 1024;
  // Determine the appropriate unit size
  let unitSize = 1;
  if (maxVal >= k ** 3)
    unitSize = k ** 3; // GB
  else if (maxVal >= k ** 2)
    unitSize = k ** 2; // MB
  else if (maxVal >= k) unitSize = k; // KB

  const maxInUnit = maxVal / unitSize;
  const rawStep = maxInUnit / targetSplits;

  // Choose the smallest "nice" step that is >= rawStep
  const niceSteps = [
    0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000,
  ];
  const step =
    niceSteps.find(s => s >= rawStep) ?? niceSteps[niceSteps.length - 1];

  const niceMax = Math.ceil(maxInUnit / step) * step;
  return { max: niceMax * unitSize, interval: step * unitSize };
};

/** Extract the first series' values from a SeriesPoint array. */
const firstSeries = (sp: SeriesPoint[] | undefined): [number, number][] => {
  if (!sp || sp.length === 0) return [];
  return sp[0].values ?? [];
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const EngineResources: React.FC<EngineResourcesProps> = ({
  isActive,
  initialEngineId,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  // State
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [selectedEngine, setSelectedEngine] = useState<string | undefined>(
    undefined
  );
  const [timeRange, setTimeRange] = useState(300); // 5 min default
  const [resourceData, setResourceData] = useState<ResourceData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Polling
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ------ Fetch engine list ---------------------------------------- */
  const fetchEngines = useCallback(async () => {
    try {
      const resp = await monitoringApi.getEngines();
      const data = (resp.data as any)?.data ?? [];
      setEngines(data);
      // Auto-select: prefer initialEngineId if present, otherwise first engine
      if (!selectedEngine && data.length > 0) {
        if (
          initialEngineId &&
          data.some((e: EngineInfo) => e.engine_id === initialEngineId)
        ) {
          setSelectedEngine(initialEngineId);
        } else {
          setSelectedEngine(data[0].engine_id);
        }
      }
    } catch {
      // Silently ignore – we'll show empty state
    }
  }, [selectedEngine, initialEngineId]);

  /* ------ Fetch resource metrics ----------------------------------- */
  const fetchResources = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const start = now - timeRange;
    try {
      setError(null);
      const resp = await monitoringApi.getEngineResources({
        engine_id: selectedEngine,
        start,
        end: now,
        max_points: 1200,
      });
      const data = (resp.data as any)?.data;
      if (data) {
        setResourceData(data as ResourceData);
      }
    } catch (e: any) {
      setError(
        e?.statusText ||
          t('pages.systemMonitor.fetchFailed', 'Failed to fetch metrics')
      );
    } finally {
      setLoading(false);
    }
  }, [selectedEngine, timeRange, t]);

  /* ------ Initial load + polling ----------------------------------- */
  useEffect(() => {
    if (!isActive) return;
    fetchEngines();
  }, [isActive, fetchEngines]);

  useEffect(() => {
    if (!isActive) return;
    setLoading(true);
    fetchResources();

    // Poll every 5 s
    pollingRef.current = setInterval(fetchResources, 5000);
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [isActive, fetchResources]);

  /* ------ Chart tooltip -------------------------------------------- */
  const chartTooltip = useMemo(
    () => ({
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const, snap: true },
      formatter: (params: any) => {
        if (!params || params.length === 0) return '';
        const ts = params[0]?.axisValue;
        const header = `<div style="font-weight:600;margin-bottom:4px">${formatTooltipTime(ts)}</div>`;
        const rows = params
          .map((p: any) => {
            const marker = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>`;
            return `<div>${marker}${p.seriesName}: <strong>${p.value ?? '–'}</strong></div>`;
          })
          .join('');
        return header + rows;
      },
    }),
    []
  );

  /* ================================================================ */
  /*  Chart options                                                    */
  /* ================================================================ */

  const cpuData = firstSeries(resourceData?.cpu_percent);
  const memPercentData = firstSeries(resourceData?.memory_percent);
  const memUsedData = firstSeries(resourceData?.memory_used_bytes);
  const memTotalData = firstSeries(resourceData?.memory_total_bytes);
  const netSentData = firstSeries(resourceData?.network_sent_bytes_per_sec);
  const netRecvData = firstSeries(resourceData?.network_recv_bytes_per_sec);

  // Latest snapshot values
  const latestCpu = cpuData.length > 0 ? cpuData[cpuData.length - 1][1] : 0;
  const latestMemPercent =
    memPercentData.length > 0
      ? memPercentData[memPercentData.length - 1][1]
      : 0;
  const latestMemUsed =
    memUsedData.length > 0 ? memUsedData[memUsedData.length - 1][1] : 0;
  const latestMemTotal =
    memTotalData.length > 0 ? memTotalData[memTotalData.length - 1][1] : 0;
  const latestNetSent =
    netSentData.length > 0 ? netSentData[netSentData.length - 1][1] : 0;
  const latestNetRecv =
    netRecvData.length > 0 ? netRecvData[netRecvData.length - 1][1] : 0;

  /** Shared style for the four summary cards. */
  const summaryCardStyle: React.CSSProperties = {
    padding: '16px 20px',
    height: '100%',
  };

  /* ----- CPU chart ------------------------------------------------- */
  const cpuOption = useMemo(() => {
    if (cpuData.length === 0) return {};
    const timestamps = cpuData.map(p => p[0]);
    return {
      tooltip: {
        ...chartTooltip,
        formatter: (params: any) => {
          if (!params || params.length === 0) return '';
          const ts = params[0]?.axisValue;
          const header = `<div style="font-weight:600;margin-bottom:4px">${formatTooltipTime(ts)}</div>`;
          const rows = params
            .map((p: any) => {
              const marker = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>`;
              return `<div>${marker}${p.seriesName}: <strong>${Number(p.value).toFixed(1)}%</strong></div>`;
            })
            .join('');
          return header + rows;
        },
      },
      grid: { top: 40, right: 30, bottom: 50, left: 60 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: { formatter: (val: number) => formatChartTime(val) },
      },
      yAxis: {
        type: 'value' as const,
        name: '%',
        max: 100,
        splitLine: { lineStyle: { type: 'dashed' as const, opacity: 0.4 } },
      },
      series: [
        {
          name: t('pages.systemMonitor.cpuUsage', 'CPU Usage'),
          type: 'line',
          data: cpuData.map(p => Number(p[1].toFixed(1))),
          smooth: true,
          symbol: 'none',
          itemStyle: { color: '#667eea' },
          lineStyle: { color: '#667eea', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(102,126,234,0.25)' },
                { offset: 1, color: 'rgba(102,126,234,0.02)' },
              ],
            },
          },
        },
      ],
    };
  }, [cpuData, chartTooltip, t]);

  /* ----- Memory chart ---------------------------------------------- */
  const memoryOption = useMemo(() => {
    if (memPercentData.length === 0) return {};
    const timestamps = memPercentData.map(p => p[0]);
    // Compute nice Y-axis range from both used & total memory series
    const allMemValues = [
      ...memUsedData.map(p => p[1]),
      ...memTotalData.map(p => p[1]),
    ];
    const memMax = allMemValues.length > 0 ? Math.max(...allMemValues) : 0;
    const memAxis = niceByteAxis(memMax);
    return {
      tooltip: {
        ...chartTooltip,
        formatter: (params: any) => {
          if (!params || params.length === 0) return '';
          const ts = params[0]?.axisValue;
          const header = `<div style="font-weight:600;margin-bottom:4px">${formatTooltipTime(ts)}</div>`;
          const rows = params
            .map((p: any) => {
              const marker = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>`;
              if (
                p.seriesName.includes('%') ||
                p.seriesName.includes('使用率')
              ) {
                return `<div>${marker}${p.seriesName}: <strong>${Number(p.value).toFixed(1)}%</strong></div>`;
              }
              return `<div>${marker}${p.seriesName}: <strong>${formatBytes(Number(p.value))}</strong></div>`;
            })
            .join('');
          return header + rows;
        },
      },
      legend: {
        data: [
          t('pages.systemMonitor.memUsed', 'Used'),
          t('pages.systemMonitor.memTotal', 'Total'),
        ],
        bottom: 0,
      },
      grid: { top: 40, right: 30, bottom: 50, left: 80 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: { formatter: (val: number) => formatChartTime(val) },
      },
      yAxis: [
        {
          type: 'value' as const,
          name: 'Bytes',
          min: 0,
          max: memAxis.max,
          interval: memAxis.interval,
          axisLabel: {
            formatter: (val: number) => formatBytes(val, 0),
          },
          splitLine: { lineStyle: { type: 'dashed' as const, opacity: 0.4 } },
        },
      ],
      series: [
        {
          name: t('pages.systemMonitor.memUsed', 'Used'),
          type: 'line',
          data: memUsedData.map(p => p[1]),
          smooth: true,
          symbol: 'none',
          itemStyle: { color: '#764ba2' },
          lineStyle: { color: '#764ba2', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(118,75,162,0.25)' },
                { offset: 1, color: 'rgba(118,75,162,0.02)' },
              ],
            },
          },
        },
        {
          name: t('pages.systemMonitor.memTotal', 'Total'),
          type: 'line',
          data: memTotalData.map(p => p[1]),
          smooth: false,
          symbol: 'none',
          lineStyle: {
            color: '#d9d9d9',
            width: 1.5,
            type: 'dashed' as const,
          },
          itemStyle: { color: '#d9d9d9' },
        },
      ],
    };
  }, [memPercentData, memUsedData, memTotalData, chartTooltip, t]);

  /* ----- Network chart --------------------------------------------- */
  const networkOption = useMemo(() => {
    if (netSentData.length === 0 && netRecvData.length === 0) return {};
    const timestamps =
      netSentData.length > 0
        ? netSentData.map(p => p[0])
        : netRecvData.map(p => p[0]);
    // Compute nice Y-axis range from both sent & recv series
    const allNetValues = [
      ...netSentData.map(p => p[1]),
      ...netRecvData.map(p => p[1]),
    ];
    const netMax = allNetValues.length > 0 ? Math.max(...allNetValues) : 0;
    const netAxis = niceByteAxis(netMax);
    return {
      tooltip: {
        ...chartTooltip,
        formatter: (params: any) => {
          if (!params || params.length === 0) return '';
          const ts = params[0]?.axisValue;
          const header = `<div style="font-weight:600;margin-bottom:4px">${formatTooltipTime(ts)}</div>`;
          const rows = params
            .map((p: any) => {
              const marker = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>`;
              return `<div>${marker}${p.seriesName}: <strong>${formatBytesPerSec(Number(p.value))}</strong></div>`;
            })
            .join('');
          return header + rows;
        },
      },
      legend: {
        data: [
          t('pages.systemMonitor.netSent', 'Sent'),
          t('pages.systemMonitor.netRecv', 'Received'),
        ],
        bottom: 0,
      },
      grid: { top: 40, right: 30, bottom: 50, left: 80 },
      xAxis: {
        type: 'category' as const,
        data: timestamps,
        axisLabel: { formatter: (val: number) => formatChartTime(val) },
      },
      yAxis: {
        type: 'value' as const,
        name: 'Bytes/s',
        min: 0,
        max: netAxis.max,
        interval: netAxis.interval,
        axisLabel: {
          formatter: (val: number) => formatBytesPerSec(val, 0),
        },
        splitLine: { lineStyle: { type: 'dashed' as const, opacity: 0.4 } },
      },
      series: [
        {
          name: t('pages.systemMonitor.netSent', 'Sent'),
          type: 'line',
          data: netSentData.map(p => Number(p[1].toFixed(2))),
          smooth: true,
          symbol: 'none',
          itemStyle: { color: '#52c41a' },
          lineStyle: { color: '#52c41a', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(82,196,26,0.2)' },
                { offset: 1, color: 'rgba(82,196,26,0.01)' },
              ],
            },
          },
        },
        {
          name: t('pages.systemMonitor.netRecv', 'Received'),
          type: 'line',
          data: netRecvData.map(p => Number(p[1].toFixed(2))),
          smooth: true,
          symbol: 'none',
          itemStyle: { color: '#faad14' },
          lineStyle: { color: '#faad14', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(250,173,20,0.2)' },
                { offset: 1, color: 'rgba(250,173,20,0.01)' },
              ],
            },
          },
        },
      ],
    };
  }, [netSentData, netRecvData, chartTooltip, t]);

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */

  const hasData = resourceData && cpuData.length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* ---- Toolbar: engine selector + time range + refresh -------- */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 20,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <Space wrap>
          <Select
            style={{ minWidth: 200 }}
            placeholder={t('pages.systemMonitor.selectEngine', 'Select Engine')}
            value={selectedEngine}
            onChange={v => setSelectedEngine(v)}
            options={engines.map(e => ({
              label: e.engine_id,
              value: e.engine_id,
            }))}
            allowClear
            showSearch
          />
          <Select
            style={{ minWidth: 100 }}
            value={timeRange}
            onChange={v => setTimeRange(v)}
            options={TIME_RANGES.map(r => ({
              label: r.label,
              value: r.value,
            }))}
          />
        </Space>

        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            setLoading(true);
            fetchResources();
          }}
          loading={loading}
        >
          {t('pages.jobs.refresh', 'Refresh')}
        </Button>
      </div>

      {/* ---- Error state -------------------------------------------- */}
      {error && (
        <Alert
          type='warning'
          message={error}
          showIcon
          closable
          style={{ marginBottom: 16 }}
          onClose={() => setError(null)}
        />
      )}

      {/* ---- Empty state -------------------------------------------- */}
      {!hasData && !loading && !error && (
        <div
          className='flex justify-center align-center'
          style={{ minHeight: '30vh' }}
        >
          <Alert
            description={t(
              'pages.systemMonitor.noEngineData',
              'No engine metrics data available'
            )}
            type='info'
            showIcon
            style={{ background: 'transparent', border: 'none' }}
          />
        </div>
      )}

      {/* ---- Realtime summary cards --------------------------------- */}
      {hasData && (
        <Row gutter={[16, 16]} align='stretch' style={{ marginBottom: 24 }}>
          <Col xs={12} sm={8} md={6}>
            <div className='content-card' style={summaryCardStyle}>
              <Statistic
                title={t('pages.systemMonitor.cpuUsage', 'CPU Usage')}
                value={latestCpu.toFixed(1)}
                suffix='%'
                valueStyle={{
                  color:
                    latestCpu > 80
                      ? '#ff4d4f'
                      : latestCpu > 60
                        ? '#faad14'
                        : '#667eea',
                  fontSize: 22,
                }}
              />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className='content-card' style={summaryCardStyle}>
              <Statistic
                title={t('pages.systemMonitor.memoryUsage', 'Memory Usage')}
                value={latestMemPercent.toFixed(1)}
                suffix='%'
                valueStyle={{
                  color:
                    latestMemPercent > 85
                      ? '#ff4d4f'
                      : latestMemPercent > 70
                        ? '#faad14'
                        : '#764ba2',
                  fontSize: 22,
                }}
              />
              <div
                style={{
                  fontSize: 13,
                  color: token.colorTextSecondary,
                  marginTop: 4,
                }}
              >
                {formatBytes(latestMemUsed)} / {formatBytes(latestMemTotal)}
              </div>
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className='content-card' style={summaryCardStyle}>
              <Statistic
                title={t('pages.systemMonitor.netSent', 'Net Sent')}
                value={formatBytesPerSec(latestNetSent)}
                valueStyle={{ color: '#52c41a', fontSize: 22 }}
              />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className='content-card' style={summaryCardStyle}>
              <Statistic
                title={t('pages.systemMonitor.netRecv', 'Net Received')}
                value={formatBytesPerSec(latestNetRecv)}
                valueStyle={{ color: '#faad14', fontSize: 22 }}
              />
            </div>
          </Col>
        </Row>
      )}

      {/* ---- CPU chart ---------------------------------------------- */}
      {hasData && (
        <div className='results-section unified-section'>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.systemMonitor.cpuUsage', 'CPU Usage')}
            </span>
          </div>
          <div className='section-content'>
            <ReactECharts
              option={cpuOption}
              style={{ height: 280 }}
              notMerge
              lazyUpdate
            />
          </div>
        </div>
      )}

      {/* ---- Memory chart ------------------------------------------- */}
      {hasData && (
        <div className='results-section unified-section'>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.systemMonitor.memoryUsage', 'Memory Usage')}
            </span>
          </div>
          <div className='section-content'>
            <ReactECharts
              option={memoryOption}
              style={{ height: 280 }}
              notMerge
              lazyUpdate
            />
          </div>
        </div>
      )}

      {/* ---- Network chart ------------------------------------------ */}
      {hasData && (
        <div className='results-section unified-section'>
          <div className='section-header'>
            <span className='section-title'>
              {t('pages.systemMonitor.networkTraffic', 'Network Bandwidth')}
            </span>
          </div>
          <div className='section-content'>
            <ReactECharts
              option={networkOption}
              style={{ height: 280 }}
              notMerge
              lazyUpdate
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default EngineResources;
